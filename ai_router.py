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
#
# Para providers Grok COM pesquisa em tempo real:
#   Use "builder": "grok_search" na entrada de OPENAI_PROVIDERS.
#   O endpoint DEVE ser /v1/responses (não /v1/chat/completions).
#   web_search e x_search só funcionam no Responses API (doc xAI).
# ─────────────────────────────────────────────────────────────

import os
import logging
from functools import partial
from typing import Optional

from dotenv import load_dotenv
from app.llm_router.ai_core import AIProvider, ProviderManager
from app.llm_router.ai_builders import (
    build_openai_compatible,
    build_grok_with_search,
    build_google_ai_studio,
)
from app.llm_router.ai_parsers import (
    parse_google_ai_response,
    parse_json_text_response,
    parse_grok_response,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ai-router")

load_dotenv()


# ─────────────────────────────────────────────────────────────
# TABELA DE PROVIDERS OPENAI-COMPATIBLE
#
# Campos obrigatórios:
#   name, api_key_env, endpoint, model, max_tokens_env
#
# Campos opcionais:
#   builder          → "openai" (padrão) | "grok_search" | "grok"
#   search_type      → "web_search" | "x_search"          [grok_search]
#   allowed_domains  → lista de domínios permitidos        [web_search]
#   excluded_domains → lista de domínios bloqueados        [web_search]
#   allowed_x_handles→ lista de @handles                  [x_search]
#   default_max_tokens, usage_limit_env, window_env, timeout_env
#
# ⚠️  Grok com search: endpoint OBRIGATÓRIO = /v1/responses
#     (web_search/x_search não existem no /v1/chat/completions)
# ─────────────────────────────────────────────────────────────

OPENAI_PROVIDERS = [
    {
        "name": "grok-4-1-fast-reasoning",
        "api_key_env": "GROK_API_KEY",
        # Responses API — único endpoint que suporta web_search/x_search
        "endpoint": "https://api.x.ai/v1/responses",
        "model": "grok-4-1-fast-reasoning",
        "max_tokens_env": "GROK_MAX_TOKENS",
        "default_max_tokens": 10000,
        "usage_limit_env": "GROK_USAGE_LIMIT",
        "window_env": "GROK_WINDOW_S",
        "timeout_env": "GROK_TIMEOUT",
        "builder": "grok_search",
        "search_type": "web_search",
        # "allowed_domains": ["reuters.com", "bbc.com"],   # opcional
        # "excluded_domains": ["reddit.com"],              # opcional
    },
    {
        "name": "grok-4.20-0309-reasoning",
        "api_key_env": "GROK_API_KEY",
        "endpoint": "https://api.x.ai/v1/responses",
        "model": "grok-4.20-0309-reasoning",
        "max_tokens_env": "GROK_MAX_TOKENS",
        "default_max_tokens": 10000,
        "usage_limit_env": "GROK_USAGE_LIMIT",
        "window_env": "GROK_WINDOW_S",
        "timeout_env": "GROK_TIMEOUT",
        "builder": "grok_search",
        "search_type": "web_search",
    },
    {
        "name": "grok-4.20-multi-agent-0309",
        "api_key_env": "GROK_API_KEY",
        "endpoint": "https://api.x.ai/v1/responses",
        "model": "grok-4.20-multi-agent-0309",
        "max_tokens_env": "GROK_MAX_TOKENS",
        "default_max_tokens": 10000,
        "usage_limit_env": "GROK_USAGE_LIMIT",
        "window_env": "GROK_WINDOW_S",
        "timeout_env": "GROK_TIMEOUT",
        "builder": "grok_search",
        "search_type": "web_search",
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
    # },
]

_GROK_BUILDERS = {"grok_search", "grok"}


def _make_openai_provider(cfg: dict) -> Optional[AIProvider]:
    api_key = os.getenv(cfg["api_key_env"])
    if not api_key:
        logger.info(f"{cfg['api_key_env']} não encontrada → {cfg['name']} desativado")
        return None

    model = cfg["model"]
    max_tokens_env = cfg["max_tokens_env"]
    default_max_tokens = cfg.get("default_max_tokens", 8192)
    builder_type = cfg.get("builder", "openai")

    if builder_type == "grok_search":
        build_payload = partial(
            build_grok_with_search,
            model=model,
            max_tokens_env=max_tokens_env,
            default_max_tokens=default_max_tokens,
            search_type=cfg.get("search_type", "web_search"),
            allowed_domains=cfg.get("allowed_domains"),
            excluded_domains=cfg.get("excluded_domains"),
            allowed_x_handles=cfg.get("allowed_x_handles"),
        )
        logger.info(
            f"{cfg['name']} → Responses API + search_type={cfg.get('search_type', 'web_search')}"
        )
    else:
        build_payload = partial(
            build_openai_compatible,
            model=model,
            max_tokens_env=max_tokens_env,
            default_max_tokens=default_max_tokens,
        )

    parser = (
        parse_grok_response
        if builder_type in _GROK_BUILDERS
        else parse_json_text_response
    )

    return AIProvider(
        name=cfg["name"],
        api_key_env=cfg["api_key_env"],
        endpoint=cfg["endpoint"],
        make_headers=lambda key: {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        build_payload=build_payload,
        parse_response=parser,
        usage_limit=int(os.getenv(cfg.get("usage_limit_env", ""), "60") or "60"),
        window_seconds=int(os.getenv(cfg.get("window_env", ""), "60") or "60"),
        timeout=int(
            os.getenv(cfg.get("timeout_env", ""), str(cfg.get("timeout_default", 60)))
            or "60"
        ),
        model=model,
    )


def make_providers() -> list:
    providers = []

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


ai_router = create_ai_router()