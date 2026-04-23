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


# ─────────────────────────────────────────────────────────────
# Classificação de falhas — facilita diagnóstico nos logs
# ─────────────────────────────────────────────────────────────

def _classify_http_error(status: int, body: str) -> str:
    """
    Retorna uma string descritiva do erro HTTP para o log.
    Mantido agnóstico: não assume nada sobre o provider.
    """
    if status == 400:
        return f"BAD_REQUEST (400) — payload rejeitado pelo provider: {body[:300]}"
    if status == 401:
        return f"UNAUTHORIZED (401) — chave de API inválida ou expirada"
    if status == 403:
        return f"FORBIDDEN (403) — sem permissão para este modelo/endpoint"
    if status == 404:
        return f"NOT_FOUND (404) — endpoint ou modelo não existe: {body[:200]}"
    if status == 422:
        return f"UNPROCESSABLE (422) — parâmetros inválidos: {body[:300]}"
    if status == 429:
        return f"RATE_LIMIT (429) — provider retornou 429 (quota externa esgotada): {body[:200]}"
    if status == 500:
        return f"SERVER_ERROR (500) — erro interno do provider (problema do lado deles): {body[:200]}"
    if status == 502:
        return f"BAD_GATEWAY (502) — gateway do provider com problema: {body[:200]}"
    if status == 503:
        return f"SERVICE_UNAVAILABLE (503) — provider fora do ar ou sobrecarregado: {body[:200]}"
    if status == 529:
        return f"OVERLOADED (529) — provider com alta demanda (código não-padrão xAI/Anthropic): {body[:200]}"
    return f"HTTP_{status}: {body[:300]}"


def _classify_exception(exc: Exception) -> str:
    """
    Classifica exceções de rede/parse para o log.
    """
    name = type(exc).__name__
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return f"CONNECT_TIMEOUT — não conseguiu conectar ao provider dentro do limite"
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return f"READ_TIMEOUT — provider conectou mas não respondeu a tempo"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return f"CONNECTION_ERROR — falha de rede ao alcançar o provider: {exc}"
    if isinstance(exc, requests.exceptions.Timeout):
        return f"TIMEOUT — timeout genérico: {exc}"
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return f"PARSE_ERROR ({name}) — bug no parser ou estrutura inesperada na resposta: {exc}"
    return f"UNEXPECTED ({name}): {exc}"


# ─────────────────────────────────────────────────────────────

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
            timeout=self.timeout,
        )


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
        """
        Executa a chamada ao provider com diagnóstico detalhado de falhas.

        Distingue claramente entre:
          - Erros do lado do provider (5xx, 429, outage)  → API_SIDE
          - Erros do lado do código (400, 422, parse)     → CODE_SIDE
          - Erros de rede/timeout                         → NETWORK
        """
        try:
            resp = p.send(prompt, temperature)
            status = resp.status_code

            if 200 <= status < 300:
                try:
                    text = p.parse_response(resp)
                    if text and text.strip():
                        p.mark_usage(1)
                        return text.strip()
                    # Parser retornou vazio — provavelmente estrutura inesperada
                    logger.error(
                        f"[{p.name}] PARSE_EMPTY — parser retornou vazio. "
                        f"Body (500 chars): {resp.text[:500]}"
                    )
                    p.force_exhaust(ttl_seconds=4)
                    return None

                except Exception as parse_exc:
                    logger.error(
                        f"[{p.name}] PARSE_ERROR — {_classify_exception(parse_exc)}. "
                        f"Body (500 chars): {resp.text[:500]}"
                    )
                    p.force_exhaust(ttl_seconds=4)
                    return None

            # ── Erros HTTP ────────────────────────────────────────────────
            body = resp.text
            diagnosis = _classify_http_error(status, body)

            if status == 429:
                # Rate limit externo — cooldown mais longo
                cooldown = int(p.window_seconds / 2)
                logger.error(f"[{p.name}] API_SIDE | {diagnosis} → cooldown {cooldown}s")
                p.force_exhaust(ttl_seconds=cooldown)

            elif status in (500, 502, 503, 529):
                # Problema do lado do provider — provável outage
                logger.error(
                    f"[{p.name}] API_SIDE | {diagnosis} "
                    f"→ provável problema de infraestrutura do provider, cooldown 30s"
                )
                p.force_exhaust(ttl_seconds=30)

            elif status in (400, 422):
                # Payload inválido — problema no código (builder/parser)
                logger.error(f"[{p.name}] CODE_SIDE | {diagnosis}")
                p.force_exhaust(ttl_seconds=4)

            elif status in (401, 403):
                # Credencial inválida — cooldown longo, não vai resolver sozinho
                logger.error(f"[{p.name}] CODE_SIDE | {diagnosis} → cooldown 300s")
                p.force_exhaust(ttl_seconds=300)

            else:
                logger.error(f"[{p.name}] UNKNOWN | {diagnosis} → cooldown 4s")
                p.force_exhaust(ttl_seconds=4)

        except Exception as exc:
            diagnosis = _classify_exception(exc)
            is_timeout = isinstance(exc, requests.exceptions.Timeout)
            cooldown = 10 if is_timeout else 5
            logger.error(f"[{p.name}] NETWORK | {diagnosis} → cooldown {cooldown}s")
            p.force_exhaust(ttl_seconds=cooldown)

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