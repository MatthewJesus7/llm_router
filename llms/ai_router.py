# ai_router.py
# ─────────────────────────────────────────────────────────────
# Ponto de entrada e configuração dos providers
# É aqui que você adiciona, remove ou ajusta providers de IA
# ─────────────────────────────────────────────────────────────

import os, logging
from dotenv import load_dotenv
from typing import Optional
from llms.ai_core import AIProvider, ProviderManager
from llms.ai_builders import build_google_ai_studio
from llms.ai_parsers import parse_google_ai_response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger("ai-router")

load_dotenv()


def make_providers():
    providers = []

    # ── adicione novos providers aqui ──────────────────────────
    #
    # Exemplo de estrutura para um provider OpenAI-style:
    #
    # providers.append(AIProvider(
    #     name="Groq",
    #     api_key_env="GROQ_API_KEY",
    #     endpoint="https://api.groq.com/openai/v1/chat/completions",
    #     make_headers=lambda key: {
    #         "Authorization": f"Bearer {key}",
    #         "Content-Type": "application/json"
    #     },
    #     build_payload=lambda prompt, temp: build_openai_style(prompt, temp, "llama3-8b-8192"),
    #     parse_response=parse_json_text_response,
    #     usage_limit=int(os.getenv("GROQ_USAGE_LIMIT", "60")),
    #     window_seconds=int(os.getenv("GROQ_WINDOW_S", "60")),
    #     timeout=30,
    #     model="llama3-8b-8192"
    # ))
    #
    # ──────────────────────────────────────────────────────────

    google_key = os.getenv("GOOGLE_API_KEY")

    if not google_key:
        logger.critical("GOOGLE_API_KEY não definido")
        raise RuntimeError("GOOGLE_API_KEY não definido")

    logger.info("Configurando provider GoogleAIStudio")

    providers.append(AIProvider(
        name="GoogleAIStudio",
        api_key_env="GOOGLE_API_KEY",
        endpoint="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        make_headers=lambda key: {
            "Content-Type": "application/json",
            "x-goog-api-key": key
        },
        build_payload=lambda prompt, temp: build_google_ai_studio(prompt, temp, "gemini-2.5-flash"),
        parse_response=parse_google_ai_response,
        usage_limit=int(os.getenv("GOOGLE_USAGE_LIMIT", "80")),    # requisições por janela
        window_seconds=int(os.getenv("GOOGLE_WINDOW_S", "60")),    # duração da janela em segundos
        timeout=int(os.getenv("GOOGLE_TIMEOUT", "60")),
        model="gemini-2.5-flash"
    ))

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


# Instância global — importe `ai_router` nos outros módulos para usar
# Exemplo: from llms.ai_router import ai_router
#          resposta = ai_router.ask("seu prompt aqui")
ai_router = create_ai_router()