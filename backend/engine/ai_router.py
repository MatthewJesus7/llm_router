# ai_router.py
# ─────────────────────────────────────────────────────────────
# Ponto de entrada e configuração unificada dos providers
# ─────────────────────────────────────────────────────────────

import os
import logging
from functools import partial
from typing import Optional, Dict, Any, List

from dotenv import load_dotenv
from engine.ai_core import AIProvider, ProviderManager
from engine.ai_builders import (
    build_openai_compatible,
    build_grok_with_search,
    build_google_ai_studio,
)
from engine.ai_parsers import (
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
# REGISTRO ÚNICO DE PROVIDERS (Com suporte a multimodels dinâmicos)
# ─────────────────────────────────────────────────────────────

PROVIDERS_CONFIG = [
    {
        "name": "OpenRouter",
        "type": "openai",
        "api_key_env": "OPENROUTER_API_KEY",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "multimodels": True,
        "models": [
            "thinkingmachines/inkling",
            "thinkingmachines/inkling-small",
            "nvidia/nemotron-3-ultra-550b-a55b",
            "nvidia/nemotron-3.5-lightning",
            "nvidia/nemotron-3.5-super-vl",
            "nvidia/nemotron-3-super-120b-a12b",
            "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
            "google/gemma-4-31b-it",
            "google/gemma-4-26b-a4b-it",
            "dots-studio/dots-3-note-preview",
            "poolside/laguna-s-2.1",
            "poolside/laguna-xs-2.1",
            "cohere/north-mini-code",
            "xingchen-agi/xing4.0-29b-a4b",
            "liquid/lfm-2.5-2.6b",
            "google/gemma-4-26b-a4b-it",
            "deepseek/deepseek-chat"
        ],
        "max_tokens_env": "OPENROUTER_MAX_TOKENS",
        "default_max_tokens": 4096,
        "usage_limit_env": "OPENROUTER_USAGE_LIMIT",
        "window_env": "OPENROUTER_WINDOW_S",
        "timeout_env": "OPENROUTER_TIMEOUT",
        "timeout_default": 60,
    }
]

def _build_provider_instance(cfg: Dict[str, Any]) -> List[AIProvider]:
    api_key_env = cfg["api_key_env"]
    api_key = os.getenv(api_key_env)

    if not api_key:
        if cfg.get("required", False):
            logger.critical(f"{api_key_env} obrigatório não definido")
            raise RuntimeError(f"{api_key_env} obrigatório não definido")
        logger.info(f"{api_key_env} não encontrada → {cfg['name']} desativado")
        return []

    p_type = cfg["type"]
    
    # Extrai a lista de modelos se multimodels estiver ativo, senão usa o modelo único
    if cfg.get("multimodels") and "models" in cfg:
        model_list = cfg["models"]
    else:
        model_list = [cfg.get("model")]

    instances = []

    for model in model_list:
        # Nome único baseado no provider + modelo exato para identificação clara no frontend/logs
        clean_model_name = model.split("/")[-1].replace(":", "-")
        instance_name = f"{cfg['name']}-{clean_model_name}"

        # Seleção de Headers, Payload e Parser baseados no tipo
        if p_type == "google":
            headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
            build_payload = partial(build_google_ai_studio, model=model)
            parser = parse_google_ai_response

        elif p_type == "grok_search":
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            build_payload = partial(
                build_grok_with_search,
                model=model,
                max_tokens_env=cfg["max_tokens_env"],
                default_max_tokens=cfg.get("default_max_tokens", 10000),
                search_type=cfg.get("search_type", "web_search"),
                allowed_domains=cfg.get("allowed_domains"),
                excluded_domains=cfg.get("excluded_domains"),
                allowed_x_handles=cfg.get("allowed_x_handles"),
            )
            parser = parse_grok_response

        else:  # padrão "openai"
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
            build_payload = partial(
                build_openai_compatible,
                model=model,
                max_tokens_env=cfg["max_tokens_env"],
                default_max_tokens=cfg.get("default_max_tokens", 8192),
            )
            parser = parse_json_text_response

        usage_limit = int(os.getenv(cfg.get("usage_limit_env", ""), str(cfg.get("default_usage_limit", 60))) or "60")
        window_seconds = int(os.getenv(cfg.get("window_env", ""), "60") or "60")
        timeout = int(os.getenv(cfg.get("timeout_env", ""), str(cfg.get("timeout_default", 300))) or "60")

        instances.append(
            AIProvider(
                name=instance_name,
                api_key_env=api_key_env,
                endpoint=cfg["endpoint"],
                make_headers=lambda _: headers,
                build_payload=build_payload,
                parse_response=parser,
                usage_limit=usage_limit,
                window_seconds=window_seconds,
                timeout=timeout,
                model=model,
            )
        )

    return instances


def make_providers() -> list:
    providers = []
    for cfg in PROVIDERS_CONFIG:
        built_instances = _build_provider_instance(cfg)
        for provider in built_instances:
            providers.append(provider)
            logger.info(f"Provider {provider.name} (Modelo: {provider.model}) configurado e ativo")

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