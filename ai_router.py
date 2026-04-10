# ai_router.py
# ─────────────────────────────────────────────────────────────
# Ponto de entrada e configuração dos providers
# É aqui que você adiciona, remove ou ajusta providers de IA
# ─────────────────────────────────────────────────────────────

import os, logging
from dotenv import load_dotenv
from typing import Optional
from app.llm_router.ai_core import AIProvider, ProviderManager
from app.llm_router.ai_builders import build_google_ai_studio, build_grok_payload, build_deepseek_payload
from app.llm_router.ai_parsers import parse_google_ai_response, parse_json_text_response

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



            # -----------------------------
    # Provider: DeepSeek
    # -----------------------------
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if deepseek_key:
        providers.append(
            AIProvider(
                name="DeepSeek",
                api_key_env="DEEPSEEK_API_KEY",
                endpoint="https://api.deepseek.com/chat/completions",  # ou "https://api.deepseek.com/v1/chat/completions" para compatibilidade total
                make_headers=lambda key: {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}"
                },
                build_payload=lambda prompt, temp: build_deepseek_payload(
                    prompt, temp, model="deepseek-reasoner"  # mude para "deepseek-reasoner" se quiser o modo reasoning
                ),
                parse_response=parse_json_text_response,  # mesmo parser OpenAI-style funciona perfeitamente
                usage_limit=int(os.getenv("DEEPSEEK_USAGE_LIMIT", "100")),  # ajuste conforme seu plano/necessidade
                window_seconds=int(os.getenv("DEEPSEEK_WINDOW_S", "60")),
                timeout=int(os.getenv("DEEPSEEK_TIMEOUT", "120")),  # DeepSeek pode demorar mais no modo reasoner
                model="deepseek-chat",  # ou "deepseek-reasoner"
            )
        )
        logger.info("Provider DeepSeek configurado e ativo")
    else:
        logger.info("DEEPSEEK_API_KEY não encontrada → DeepSeek desativado")

        # -----------------------------
    # Provider: Grok (xAI)
    # -----------------------------
    grok_key = os.getenv("GROK_API_KEY")
    if grok_key:
        providers.append(
            AIProvider(
                name="Grok",
                api_key_env="GROK_API_KEY",
                endpoint="https://api.x.ai/v1/chat/completions",  # endpoint oficial da xAI
                make_headers=lambda key: {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key}"
                },
                build_payload=lambda prompt, temp: build_grok_payload(
                    prompt, temp, model="grok-4-1-fast-reasoning"
                ),
                parse_response=parse_json_text_response,  # reutiliza o parser OpenAI-style (funciona perfeitamente)
                usage_limit=int(os.getenv("GROK_USAGE_LIMIT", "60")),     # ajuste conforme seu plano
                window_seconds=int(os.getenv("GROK_WINDOW_S", "60")),
                timeout=int(os.getenv("GROK_TIMEOUT", "60")),
                model="grok-4-1-fast-reasoning",
            )
        )
        logger.info("Provider Grok (xAI) configurado e ativo")
    else:
        logger.info("GROK_API_KEY não encontrada → Grok desativado")


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