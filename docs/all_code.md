


# código inteiro de todas as páginas:

# ai_parsers.py: 


# ─────────────────────────────────────────────────────────────
# Não precisa mexer aqui a menos que adicione um provider novo
# com formato de resposta diferente de Google AI ou OpenAI-style
# ─────────────────────────────────────────────────────────────

import requests, logging
logger = logging.getLogger("ai-router")


# Fallback genérico — percorre o JSON em busca de qualquer texto útil
# Usado quando o formato da resposta não bate com os padrões conhecidos
def _find_text_in_json(obj, max_depth=6):
    if max_depth <= 0:
        return None
    if isinstance(obj, str) and obj.strip():
        return obj.strip()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ["text", "output", "generated_text", "result"] and isinstance(value, str):
                return value.strip()
            res = _find_text_in_json(value, max_depth-1)
            if res:
                return res
    if isinstance(obj, list):
        for item in obj:
            res = _find_text_in_json(item, max_depth-1)
            if res:
                return res
    return None


# Parser para respostas da Google AI (Gemini)
# Se adicionar outro modelo Google com estrutura diferente, ajuste aqui
def parse_google_ai_response(resp: requests.Response) -> str:
    try:
        data = resp.json()

        if "candidates" in data and data["candidates"]:
            cand = data["candidates"][0]
            if "content" in cand:
                parts = cand["content"].get("parts", [])
                for p in parts:
                    if isinstance(p, dict) and "text" in p:
                        return p["text"].strip()

        if "output" in data and isinstance(data["output"], str):
            return data["output"].strip()

        if "generatedText" in data and isinstance(data["generatedText"], str):
            return data["generatedText"].strip()

        if "promptFeedback" in data:
            reason = data['promptFeedback'].get('blockReason','unknown')
            logger.warning(f"Resposta bloqueada pelo provider: {reason}")
            return f"[Blocked: {reason}]"

        # Último recurso: tenta achar qualquer string no JSON
        text = _find_text_in_json(data)
        if text:
            logger.debug("Fallback parser acionado (_find_text_in_json)")
            return text.strip()

        raise RuntimeError("Estrutura inesperada (Google AI).")

    except Exception as e:
        logger.warning(f"Erro parse Google: {e}")
        return resp.text.strip()


def _get_nested_value(obj, keys):
    current = obj
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and isinstance(key, int) and key < len(current):
            current = current[key]
        else:
            return None
    return current if isinstance(current, str) else None


# Parser genérico para APIs estilo OpenAI (e compatíveis como Groq, Together, etc.)
# Se o seu provider retorna um campo diferente, adicione o caminho em `patterns`
def parse_json_text_response(resp: requests.Response) -> str:
    try:
        j = resp.json()

        # ── adicione aqui novos padrões de resposta se necessário ──
        patterns = [
            ("choices", 0, "message", "content"),
            ("choices", 0, "text"),
            ("generated_text",),
            ("output",),
            ("text",),
            ("content",)
        ]
        # ────────────────────────────────────────────────────────────

        for p in patterns:
            result = _get_nested_value(j, p)
            if result and result.strip():
                return result.strip()

        logger.debug("Nenhum padrão conhecido encontrado no parser JSON")
        return str(j).strip()

    except Exception as e:
        logger.warning(f"Erro parse JSON genérico: {e}")
        return resp.text.strip()
        


# ai_core.py: 

# core.py
# ─────────────────────────────────────────────────────────────
# Motor do roteador — não precisa mexer aqui
# Contém a lógica de rate limit, fallback e seleção de providers
# ─────────────────────────────────────────────────────────────

import os
import time
import threading
import requests
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any, List

logger = logging.getLogger("ai-router")


# Representa um provider de IA com suas configurações e estado de uso
# Instâncias são criadas em ai_router.py — não instancie diretamente aqui
@dataclass
class AIProvider:
    name: str
    api_key_env: str
    endpoint: str
    make_headers: Callable[[str], Dict[str, str]]
    build_payload: Callable[[str, float], Dict[str, Any]]
    parse_response: Callable[[requests.Response], str]
    usage_limit: int = 100
    window_seconds: int = 60
    used_count: int = 0
    window_start: float = field(default_factory=lambda: time.time())
    exhausted_until: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)
    model: str = "default"
    timeout: int = 30

    def has_key(self) -> bool:
        return bool(os.getenv(self.api_key_env))

    def reset_window_if_needed(self):
        now = time.time()
        if now - self.window_start >= self.window_seconds:
            logger.debug(f"[{self.name}] reset de janela de uso")
            self.window_start = now
            self.used_count = 0

    def can_use(self) -> bool:
        try:
            with self.lock:
                self.reset_window_if_needed()
                now = time.time()
                if now < self.exhausted_until:
                    logger.debug(f"[{self.name}] ainda em cooldown")
                    return False
                available = self.used_count < self.usage_limit
                if not available:
                    logger.debug(f"[{self.name}] limite de uso atingido")
                return available
        except Exception as e:
            logger.exception(f"[{self.name}] erro em can_use: {e}")
            return False

    def mark_usage(self, count: int = 1):
        with self.lock:
            self.used_count += count
            logger.debug(f"[{self.name}] uso incrementado: {self.used_count}/{self.usage_limit}")
            if self.used_count >= self.usage_limit:
                self.exhausted_until = self.window_start + self.window_seconds
                logger.warning(f"[{self.name}] entrou em cooldown (rate limit interno)")

    def force_exhaust(self, ttl_seconds: int):
        with self.lock:
            self.exhausted_until = time.time() + ttl_seconds
            logger.warning(f"[{self.name}] forçado para cooldown por {ttl_seconds}s")

    def send(self, prompt: str, temperature: float = 0.7) -> requests.Response:
        key = os.getenv(self.api_key_env)
        if not key:
            raise RuntimeError(f"API key for {self.name} not found")
        headers = self.make_headers(key)
        payload = self.build_payload(prompt, temperature)
        logger.debug(f"[{self.name}] enviando request")
        return requests.post(
            self.endpoint,
            headers=headers,
            json=payload,
            timeout=self.timeout
        )


# Gerencia a lista de providers e implementa o fallback automático entre eles
# O roteamento é round-robin com pulo automático em caso de erro ou rate limit
class ProviderManager:
    def __init__(self, providers: List[AIProvider]):
        self.providers = [p for p in providers if p.has_key()]

        if not self.providers:
            raise RuntimeError("Nenhum provider configurado com chave de API.")

        logger.info(f"{len(self.providers)} provider(s) ativos")

        self.providers_map = {p.name.lower(): p for p in self.providers}

        self.idx = 0
        self.lock = threading.Lock()

    def _next_index(self) -> int:
        with self.lock:
            i = self.idx
            self.idx = (self.idx + 1) % len(self.providers)
            return i

    def get_available_provider(self) -> Optional[AIProvider]:
        n = len(self.providers)
        start = self._next_index()

        for offset in range(n):
            i = (start + offset) % n
            p = self.providers[i]
            if p.can_use():
                logger.debug(f"[{p.name}] selecionado")
                return p

        logger.error("Nenhum provider disponível")
        return None

    def _execute(self, p: AIProvider, prompt: str, temperature: float) -> Optional[str]:
        try:
            resp = p.send(prompt, temperature)

            if 200 <= resp.status_code < 300:
                text = p.parse_response(resp)
                p.mark_usage(1)
                return text.strip()

            if resp.status_code == 429:
                p.force_exhaust(ttl_seconds=int(p.window_seconds / 2))

            elif 400 <= resp.status_code < 600:
                p.force_exhaust(ttl_seconds=4)

        except Exception as e:
            logger.exception(f"[{p.name}] erro na request: {e}")
            p.force_exhaust(ttl_seconds=5)

        return None

    def ask(self, prompt: str, temperature: float = 0.7, provider_name: str = None) -> str:
        # ── override manual ─────────────────────────────
        if provider_name:
            p = self.providers_map.get(provider_name.strip().lower())

            if not p:
                raise ValueError(f"Provider '{provider_name}' não encontrado")

            if not p.can_use():
                raise RuntimeError(f"Provider '{p.name}' indisponível (rate limit/cooldown)")

            result = self._execute(p, prompt, temperature)
            if result:
                return result

            raise RuntimeError(f"Provider '{p.name}' falhou na execução")

        # ── comportamento original ──────────────────────
        for attempt in range(len(self.providers)):
            p = self.get_available_provider()

            if not p:
                break

            result = self._execute(p, prompt, temperature)
            if result:
                logger.info(f"[{p.name}] sucesso")
                return result

        logger.critical("Todos providers falharam")
        raise RuntimeError("Todos providers falharam.")

    def available_providers(self) -> List[str]:
        return list(self.providers_map.keys())
        

# ai_builders.py: 

# ai_builders.py
# ─────────────────────────────────────────────────────────────
# Funções que montam o payload de cada provider
# Mexa aqui se quiser ajustar parâmetros de geração (tokens, topP, etc.)
#
# Estrutura:
#   build_openai_compatible  → funciona pra QUALQUER provider OpenAI-style
#                              (DeepSeek, Grok, Venice, Groq, Together, etc.)
#   build_google_ai_studio   → único formato diferente que temos hoje
# ─────────────────────────────────────────────────────────────

import os
from typing import Dict, Any


def build_openai_compatible(
    prompt: str,
    temperature: float,
    model: str,
    max_tokens_env: str,
    default_max_tokens: int = 8192,
) -> Dict[str, Any]:
    """
    Builder genérico para qualquer API OpenAI-compatible.

    Parâmetros
    ----------
    prompt            : texto do usuário
    temperature       : temperatura de geração (repassado pelo router)
    model             : nome do modelo (ex: "deepseek-chat", "grok-3-fast")
    max_tokens_env    : nome da variável de ambiente para max_tokens
                        (ex: "DEEPSEEK_MAX_TOKENS") — mantém config por provider
    default_max_tokens: fallback se a env não estiver definida
    """
    max_tokens = int(os.getenv(max_tokens_env, str(default_max_tokens)))
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }


def build_google_ai_studio(
    prompt: str,
    temperature: float,
    model: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    """
    Builder específico para Google AI Studio (Gemini).
    Formato diverge do padrão OpenAI — mantido separado intencionalmente.
    """
    max_tokens = int(os.getenv("GOOGLE_MAX_OUTPUT_TOKENS", "8192"))
    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "topP": 0.95,
        },
    }


# ai_router.py
# ─────────────────────────────────────────────────────────────
# Ponto de entrada e configuração dos providers
#
# Para adicionar um provider OpenAI-compatible:
#   1. Adicione uma entrada em OPENAI_PROVIDERS (logo abaixo)
#   2. Pronto — não mexe em mais nada
#
# Para um provider com formato diferente (ex: Google):
#   Crie o builder em ai_builders.py e registre manualmente
#   na função make_providers(), seguindo o exemplo do Google.
# ─────────────────────────────────────────────────────────────

import os
import logging
from functools import partial
from typing import Optional

from dotenv import load_dotenv
from app.llm_router.ai_core import AIProvider, ProviderManager
from app.llm_router.ai_builders import build_openai_compatible, build_google_ai_studio
from app.llm_router.ai_parsers import parse_google_ai_response, parse_json_text_response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ai-router")

load_dotenv()


# ─────────────────────────────────────────────────────────────
# TABELA DE PROVIDERS OPENAI-COMPATIBLE
# Adicionar provider novo = uma entrada aqui, nada mais.
#
# Campos obrigatórios:
#   name             → nome de exibição / log
#   api_key_env      → env var com a chave da API
#   endpoint         → URL do endpoint de completions
#   model            → modelo padrão
#   max_tokens_env   → env var para controlar max_tokens
#   default_max_tokens → fallback se env não estiver definida
#
# Campos opcionais (têm fallback):
#   usage_limit_env  → env var para o rate limit de requisições (padrão: 60)
#   window_env       → env var para a janela em segundos (padrão: 60)
#   timeout_env      → env var para timeout em segundos (padrão: 60)
# ─────────────────────────────────────────────────────────────

OPENAI_PROVIDERS = [
    {
        "name": "grok-4-1-fast-reasoning",
        "api_key_env": "GROK_API_KEY",
        "endpoint": "https://api.x.ai/v1/chat/completions",
        "model": "grok-4-1-fast-reasoning",
        "max_tokens_env": "GROK_MAX_TOKENS",
        "default_max_tokens": 10000,
        "usage_limit_env": "GROK_USAGE_LIMIT",
        "window_env": "GROK_WINDOW_S",
        "timeout_env": "GROK_TIMEOUT",
    },
    {
        "name": "grok-4.20-0309-reasoning",
        "api_key_env": "GROK_API_KEY",
        "endpoint": "https://api.x.ai/v1/chat/completions",
        "model": "grok-4.20-0309-reasoning",
        "max_tokens_env": "GROK_MAX_TOKENS",
        "default_max_tokens": 10000,
        "usage_limit_env": "GROK_USAGE_LIMIT",
        "window_env": "GROK_WINDOW_S",
        "timeout_env": "GROK_TIMEOUT",
    },
    {
        "name": "grok-4.20-multi-agent-0309",
        "api_key_env": "GROK_API_KEY",
        "endpoint": "https://api.x.ai/v1/chat/completions",
        "model": "grok-4.20-multi-agent-0309",
        "max_tokens_env": "GROK_MAX_TOKENS",
        "default_max_tokens": 10000,
        "usage_limit_env": "GROK_USAGE_LIMIT",
        "window_env": "GROK_WINDOW_S",
        "timeout_env": "GROK_TIMEOUT",
    },
    {
        "name": "Venice",
        "api_key_env": "VENICE_API_KEY",
        "endpoint": "https://api.venice.ai/api/v1/chat/completions",
        "model": "venice-uncensored-1-2",
        "max_tokens_env": "VENICE_MAX_TOKENS",
        "default_max_tokens": 8192,
        "usage_limit_env": "VENICE_USAGE_LIMIT",
        "window_env": "VENICE_WINDOW_S",
        "timeout_env": "VENICE_TIMEOUT",
        "timeout_default": 90,
    },
    {
        "name": "glm-4.7-flash-heretic",
        "api_key_env": "VENICE_API_KEY",
        "endpoint": "https://api.venice.ai/api/v1/chat/completions",
        "model": "olafangensan-glm-4.7-flash-heretic",
        "max_tokens_env": "VENICE_MAX_TOKENS",
        "default_max_tokens": 8192,
        "usage_limit_env": "VENICE_USAGE_LIMIT",
        "window_env": "VENICE_WINDOW_S",
        "timeout_env": "VENICE_TIMEOUT",
        "timeout_default": 90,
    },
        {
        "name": "qwen3-coder-instruct-turbo",
        "api_key_env": "VENICE_API_KEY",
        "endpoint": "https://api.venice.ai/api/v1/chat/completions",
        "model": "qwen3-coder-480b-a35b-instruct-turbo",
        "max_tokens_env": "QWEN_CODER_MAX_TOKENS",
        "usage_limit_env": "QWEN_CODER_USAGE_LIMIT",
        "window_env": "QWEN_CODER_WINDOW_S",
        "timeout_env": "QWEN_CODER_TIMEOUT",
    },

    # ── Novo provider? Copie o bloco acima e preencha ──────────
    #
    # {
    #     "name": "Groq",
    #     "api_key_env": "GROQ_API_KEY",
    #     "endpoint": "https://api.groq.com/openai/v1/chat/completions",
    #     "model": "llama3-8b-8192",
    #     "max_tokens_env": "GROQ_MAX_TOKENS",
    #     "default_max_tokens": 8192,
    #     "usage_limit_env": "GROQ_USAGE_LIMIT",
    #     "window_env": "GROQ_WINDOW_S",
    #     "timeout_env": "GROQ_TIMEOUT",
    # },
]


def _make_openai_provider(cfg: dict) -> Optional[AIProvider]:
    """
    Factory que transforma uma entrada de OPENAI_PROVIDERS em um AIProvider.
    Retorna None se a API key não estiver definida.
    """
    api_key = os.getenv(cfg["api_key_env"])
    if not api_key:
        logger.info(f"{cfg['api_key_env']} não encontrada → {cfg['name']} desativado")
        return None

    model = cfg["model"]
    max_tokens_env = cfg["max_tokens_env"]
    default_max_tokens = cfg.get("default_max_tokens", 8192)

    return AIProvider(
        name=cfg["name"],
        api_key_env=cfg["api_key_env"],
        endpoint=cfg["endpoint"],
        make_headers=lambda key: {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        build_payload=partial(
            build_openai_compatible,
            model=model,
            max_tokens_env=max_tokens_env,
            default_max_tokens=default_max_tokens,
        ),
        parse_response=parse_json_text_response,
        usage_limit=int(os.getenv(cfg.get("usage_limit_env", ""), "60") or "60"),
        window_seconds=int(os.getenv(cfg.get("window_env", ""), "60") or "60"),
        timeout=int(os.getenv(cfg.get("timeout_env", ""), str(cfg.get("timeout_default", 60))) or "60"),
        model=model,
    )


def make_providers() -> list:
    providers = []

    # ── Google AI Studio (formato próprio — não OpenAI-compatible) ──
    google_key = os.getenv("GOOGLE_API_KEY")
    if not google_key:
        logger.critical("GOOGLE_API_KEY não definido")
        raise RuntimeError("GOOGLE_API_KEY não definido")

    providers.append(AIProvider(
        name="GoogleAIStudio",
        api_key_env="GOOGLE_API_KEY",
        endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        make_headers=lambda key: {
            "Content-Type": "application/json",
            "x-goog-api-key": key,
        },
        build_payload=partial(build_google_ai_studio, model="gemini-2.5-flash"),
        parse_response=parse_google_ai_response,
        usage_limit=int(os.getenv("GOOGLE_USAGE_LIMIT", "80")),
        window_seconds=int(os.getenv("GOOGLE_WINDOW_S", "60")),
        timeout=int(os.getenv("GOOGLE_TIMEOUT", "60")),
        model="gemini-2.5-flash",
    ))
    logger.info("Provider GoogleAIStudio configurado")

    # ── Providers OpenAI-compatible (via tabela declarativa) ───
    for cfg in OPENAI_PROVIDERS:
        provider = _make_openai_provider(cfg)
        if provider:
            providers.append(provider)
            logger.info(f"Provider {cfg['name']} configurado e ativo")

    logger.info(f"{len(providers)} provider(s) configurado(s)")
    return providers


def create_ai_router() -> Optional[ProviderManager]:
    try:
        logger.info("Inicializando AI Router")
        providers = make_providers()

        if not providers:
            logger.error("Nenhum provider configurado")
            return None

        router = ProviderManager(providers)
        logger.info("AI Router pronto")
        return router

    except Exception as e:
        logger.exception(f"Falha crítica ao inicializar AI Router: {e}")
        return None


# Instância global — importe nos outros módulos para usar
# Exemplo: from llms.ai_router import ai_router
#          resposta = ai_router.ask("seu prompt aqui")
ai_router = create_ai_router()