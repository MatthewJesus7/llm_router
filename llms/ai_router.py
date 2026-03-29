import os, logging
from dotenv import load_dotenv
from typing import Optional
from llms.ai_core import AIProvider, ProviderManager
from llms.ai_builders import build_google_ai_studio, build_openai_style
from llms.ai_parsers import parse_google_ai_response, parse_json_text_response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-router")

load_dotenv()

def make_providers():
    providers = []
    google_key = os.getenv("GOOGLE_API_KEY")
    if not google_key:
        raise RuntimeError("GOOGLE_API_KEY não definido")

    google_endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={google_key}"
    )

    providers.append(AIProvider(
        name="GoogleAIStudio",
        api_key_env="GOOGLE_API_KEY",
        endpoint=google_endpoint,
        make_headers=lambda key: {
            "Content-Type": "application/json"
        },
        build_payload=lambda prompt, temp: build_google_ai_studio(prompt, temp, "gemini-2.5-flash"),
        parse_response=parse_google_ai_response,
        usage_limit=int(os.getenv("GOOGLE_USAGE_LIMIT", "80")),
        window_seconds=int(os.getenv("GOOGLE_WINDOW_S", "60")),
        timeout=int(os.getenv("GOOGLE_TIMEOUT", "60")),
        model="gemini-2.5-flash"
    ))
    return providers

def create_ai_router() -> Optional[ProviderManager]:
    try:
        providers = make_providers()
        if not providers:
            logger.error("Nenhum provider configurado")
            return None
        return ProviderManager(providers)
    except Exception as e:
        logger.exception(f"Falha crítica ao inicializar AI Router: {e}")
        return None

ai_router = create_ai_router()
