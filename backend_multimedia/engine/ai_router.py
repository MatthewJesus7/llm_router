"""Router do módulo de vídeo: seleção de provedor e despacho de jobs."""
# ai_router.py
# ─────────────────────────────────────────────────────────────
# Ponto de entrada e configuração unificada dos providers MULTIMÍDIA
#
# Estrutura idêntica ao ai_router de texto:
#   PROVIDERS_CONFIG → _build_provider_instance → make_providers → create_ai_router
#
# Diferença: o "type" resolve, além de headers/builder/parser de submit,
# as funções de status (polling) e webhook — exigidas pela doc para
# imagem/vídeo/áudio assíncronos.
# ─────────────────────────────────────────────────────────────

import os
import logging
from functools import partial
from typing import Callable, Dict, Any, List, Optional

from dotenv import load_dotenv
from engine.ai_core import AIProvider, ProviderManager
from engine.ai_builders import (
    build_openai_images,
    build_openai_audio_speech,
    build_elevenlabs_tts,
    build_replicate_prediction,
    build_runway_task,
)
from engine.ai_parsers import (
    openai_images_submit,
    openai_tts_submit,
    elevenlabs_tts_submit,
    replicate_submit,
    replicate_status,
    replicate_webhook,
    runway_submit,
    runway_status,
    runway_webhook,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("ai-router")

load_dotenv()


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _bearer(api_key: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _elevenlabs_headers(api_key: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }


def _status_url_builder(template: str) -> Callable[[str], str]:
    return lambda job_id: template.format(job_id=job_id)


def _env_int(name: Optional[str], default: int) -> int:
    if not name:
        return default
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


# ─────────────────────────────────────────────────────────────
# REGISTRO ÚNICO DE PROVIDERS
#
# Tipos síncronos:  openai_images | openai_tts | elevenlabs_tts
# Tipos assíncronos: replicate | runway
# ─────────────────────────────────────────────────────────────

PROVIDERS_CONFIG = [
    # ── SÍNCRONO: imagem (DALL-E) ──────────────────────────
    {
        "name": "OpenAI-Images",
        "type": "openai_images",
        "api_key_env": "OPENAI_API_KEY",
        "endpoint": "https://api.openai.com/v1/images/generations",
        "multimodels": True,
        "models": ["dall-e-3"],
        "usage_limit_env": "OPENAI_IMAGES_USAGE_LIMIT",
        "default_usage_limit": 20,
        "window_env": "OPENAI_IMAGES_WINDOW_S",
        "timeout_env": "OPENAI_IMAGES_TIMEOUT",
        "timeout_default": 90,
    },
    # ── SÍNCRONO: áudio (OpenAI TTS) ───────────────────────
    {
        "name": "OpenAI-TTS",
        "type": "openai_tts",
        "api_key_env": "OPENAI_API_KEY",
        "endpoint": "https://api.openai.com/v1/audio/speech",
        "multimodels": True,
        "models": ["tts-1", "tts-1-hd"],
        "usage_limit_env": "OPENAI_TTS_USAGE_LIMIT",
        "default_usage_limit": 30,
        "window_env": "OPENAI_TTS_WINDOW_S",
        "timeout_env": "OPENAI_TTS_TIMEOUT",
        "timeout_default": 60,
    },
    # ── SÍNCRONO: áudio (ElevenLabs REST) ──────────────────
    # voice_id resolve o {voice_id} do endpoint; um bloco por voz.
    {
        "name": "ElevenLabs-Rachel",
        "type": "elevenlabs_tts",
        "api_key_env": "ELEVENLABS_API_KEY",
        "endpoint": "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        "voice_id": "21m00Tcm4TlvDq8ikWAM",
        "multimodels": True,
        "models": ["eleven_multilingual_v2", "eleven_turbo_v2_5"],
        "usage_limit_env": "ELEVENLABS_USAGE_LIMIT",
        "default_usage_limit": 30,
        "window_env": "ELEVENLABS_WINDOW_S",
        "timeout_env": "ELEVENLABS_TIMEOUT",
        "timeout_default": 60,
    },
    # ── ASSÍNCRONO: vídeo (Replicate) ──────────────────────
    # replicate_version é obrigatório por instância — versions são imutáveis.
    {
        "name": "Replicate",
        "type": "replicate",
        "api_key_env": "REPLICATE_API_TOKEN",
        "endpoint": "https://api.replicate.com/v1/predictions",
        "status_url_template": "https://api.replicate.com/v1/predictions/{job_id}",
        "supports_webhook": True,
        "multimodels": True,
        "models": ["stability-ai/stable-video-diffusion"],
        "replicate_version": None,  # preencher ou definir REPLICATE_VERSION no env
        "usage_limit_env": "REPLICATE_USAGE_LIMIT",
        "default_usage_limit": 20,
        "window_env": "REPLICATE_WINDOW_S",
        "timeout_env": "REPLICATE_TIMEOUT",
        "timeout_default": 60,
        "poll_interval_env": "REPLICATE_POLL_INTERVAL",
        "poll_interval_default": 3,
    },
    # ── ASSÍNCRONO: vídeo (Runway) ─────────────────────────
    # image_to_video exige imagem: passar via input_overrides no builder
    # ou trocar para /v1/text_to_video quando o modelo suportar.
    {
        "name": "Runway",
        "type": "runway",
        "api_key_env": "RUNWAY_API_KEY",
        "endpoint": "https://api.dev.runwayml.com/v1/image_to_video",
        "status_url_template": "https://api.dev.runwayml.com/v1/tasks/{job_id}",
        "supports_webhook": True,
        "multimodels": True,
        "models": ["gen3a_turbo"],
        "usage_limit_env": "RUNWAY_USAGE_LIMIT",
        "default_usage_limit": 10,
        "window_env": "RUNWAY_WINDOW_S",
        "timeout_env": "RUNWAY_TIMEOUT",
        "timeout_default": 60,
        "poll_interval_env": "RUNWAY_POLL_INTERVAL",
        "poll_interval_default": 5,
    },
]


# ─────────────────────────────────────────────────────────────
# Adaptador por tipo (headers + builder + parser de submit + status/webhook)
# ─────────────────────────────────────────────────────────────

def _adapter_for_type(
    p_type: str, cfg: Dict[str, Any], model: str, api_key: str
) -> Dict[str, Any]:

    if p_type == "openai_images":
        return {
            "make_headers": lambda _: _bearer(api_key),
            "build_payload": partial(build_openai_images, model=model),
            "parse_submit": openai_images_submit,
            "build_status_url": None,
            "parse_status": None,
            "supports_webhook": False,
            "parse_webhook": None,
        }

    if p_type == "openai_tts":
        return {
            "make_headers": lambda _: _bearer(api_key),
            "build_payload": partial(build_openai_audio_speech, model=model),
            "parse_submit": openai_tts_submit,
            "build_status_url": None,
            "parse_status": None,
            "supports_webhook": False,
            "parse_webhook": None,
        }

    if p_type == "elevenlabs_tts":
        return {
            "make_headers": lambda _: _elevenlabs_headers(api_key),
            "build_payload": partial(build_elevenlabs_tts, model_id=model),
            "parse_submit": elevenlabs_tts_submit,
            "build_status_url": None,
            "parse_status": None,
            "supports_webhook": False,
            "parse_webhook": None,
        }

    if p_type == "replicate":
        version = cfg.get("replicate_version") or os.getenv("REPLICATE_VERSION")
        if not version:
            raise RuntimeError(
                "Replicate: 'replicate_version' ausente na config e REPLICATE_VERSION "
                "não definido no env"
            )
        return {
            "make_headers": lambda _: _bearer(api_key),
            "build_payload": partial(build_replicate_prediction, version=version),
            "parse_submit": replicate_submit,
            "build_status_url": _status_url_builder(cfg["status_url_template"]),
            "parse_status": replicate_status,
            "supports_webhook": cfg.get("supports_webhook", True),
            "parse_webhook": replicate_webhook,
        }

    if p_type == "runway":
        return {
            "make_headers": lambda _: _bearer(api_key),
            "build_payload": partial(build_runway_task, model=model),
            "parse_submit": runway_submit,
            "build_status_url": _status_url_builder(cfg["status_url_template"]),
            "parse_status": runway_status,
            "supports_webhook": cfg.get("supports_webhook", True),
            "parse_webhook": runway_webhook,
        }

    raise ValueError(f"Tipo de provider desconhecido: {p_type}")


def _build_provider_instance(cfg: Dict[str, Any]) -> List[AIProvider]:
    api_key_env = cfg["api_key_env"]
    api_key = os.getenv(api_key_env)

    if not api_key:
        if cfg.get("required", False):
            logger.critical(f"{api_key_env} obrigatório não definido")
            raise RuntimeError(f"{api_key_env} obrigatório não definido")
        logger.info(f"{api_key_env} não encontrada → {cfg['name']} desativado")
        return []

    # Endpoint com placeholders (ex.: ElevenLabs {voice_id})
    endpoint = cfg["endpoint"]
    if "{voice_id}" in endpoint:
        voice_id = cfg.get("voice_id")
        if not voice_id:
            logger.error(f"{cfg['name']}: 'voice_id' obrigatório no config")
            return []
        endpoint = endpoint.format(voice_id=voice_id)

    if cfg.get("multimodels") and "models" in cfg:
        model_list = cfg["models"]
    else:
        model_list = [cfg.get("model")]

    if not model_list or model_list == [None]:
        logger.error(f"{cfg['name']}: nenhum modelo definido")
        return []

    p_type = cfg["type"]
    instances: List[AIProvider] = []

    for model in model_list:
        clean_model_name = str(model).split("/")[-1].replace(":", "-")
        instance_name = f"{cfg['name']}-{clean_model_name}"

        adapter = _adapter_for_type(p_type, cfg, model, api_key)

        usage_limit = _env_int(
            cfg.get("usage_limit_env"),
            cfg.get("default_usage_limit", 60),
        )
        window_seconds = _env_int(cfg.get("window_env"), 60)
        timeout = _env_int(cfg.get("timeout_env"), cfg.get("timeout_default", 60))
        poll_interval = _env_int(
            cfg.get("poll_interval_env"),
            cfg.get("poll_interval_default", 2),
        )

        instances.append(
            AIProvider(
                name=instance_name,
                api_key_env=api_key_env,
                endpoint=endpoint,
                make_headers=adapter["make_headers"],
                build_payload=adapter["build_payload"],
                parse_submit=adapter["parse_submit"],
                build_status_url=adapter["build_status_url"],
                parse_status=adapter["parse_status"],
                supports_webhook=adapter["supports_webhook"],
                parse_webhook=adapter["parse_webhook"],
                poll_interval=poll_interval,
                usage_limit=usage_limit,
                window_seconds=window_seconds,
                timeout=timeout,
                model=str(model),
            )
        )

    return instances


def make_providers() -> List[AIProvider]:
    providers: List[AIProvider] = []
    for cfg in PROVIDERS_CONFIG:
        try:
            built_instances = _build_provider_instance(cfg)
        except Exception:
            logger.exception(f"Falha ao construir provider {cfg.get('name')}")
            continue

        for provider in built_instances:
            providers.append(provider)
            logger.info(
                f"Provider {provider.name} (modelo: {provider.model}) configurado"
            )

    logger.info(f"{len(providers)} provider(s) multimídia configurado(s)")
    return providers


def create_ai_router() -> Optional[ProviderManager]:
    try:
        logger.info("Inicializando AI Media Router")
        providers = make_providers()

        if not providers:
            logger.error("Nenhum provider multimídia configurado")
            return None

        router = ProviderManager(providers)
        logger.info("AI Media Router pronto")
        return router

    except Exception as e:
        logger.exception(f"Falha crítica ao inicializar AI Media Router: {e}")
        return None


ai_router = create_ai_router()