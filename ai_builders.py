# ai_builders.py
# ─────────────────────────────────────────────────────────────
# Funções que montam o payload de cada provider
# Mexa aqui se quiser ajustar parâmetros de geração (tokens, topP, etc.)
#
# Estrutura:
#   build_openai_compatible  → funciona pra QUALQUER provider OpenAI-style
#                              (DeepSeek, Grok, Venice, Groq, Together, etc.)
#   build_grok_with_search   → igual ao OpenAI-compatible, mas injeta o
#                              tool de web_search (ou x_search) do Grok
#   build_google_ai_studio   → único formato diferente que temos hoje
# ─────────────────────────────────────────────────────────────

import os
from typing import Dict, Any, Literal


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


def build_grok_with_search(
    prompt: str,
    temperature: float,
    model: str,
    max_tokens_env: str,
    default_max_tokens: int = 10000,
    search_type: Literal["web_search", "x_search"] = "web_search",
    allowed_domains: list[str] | None = None,
    allowed_x_handles: list[str] | None = None,
) -> Dict[str, Any]:
    """
    Builder para providers Grok com pesquisa em tempo real ativada.

    Idêntico ao build_openai_compatible, mas injeta o tool de busca
    no payload para que o Grok consulte a web (ou o X) antes de responder.

    Parâmetros
    ----------
    prompt             : texto do usuário
    temperature        : temperatura de geração
    model              : nome do modelo Grok
    max_tokens_env     : env var para max_tokens
    default_max_tokens : fallback se a env não estiver definida
    search_type        : "web_search" (web geral) ou "x_search" (só posts do X)
    allowed_domains    : (opcional) lista de domínios permitidos p/ web_search
                         ex: ["reuters.com", "bbc.com"]
    allowed_x_handles  : (opcional) lista de @handles p/ x_search
                         ex: ["elonmusk", "xai"]
    """
    max_tokens = int(os.getenv(max_tokens_env, str(default_max_tokens)))

    tool: Dict[str, Any] = {"type": search_type}

    if search_type == "web_search" and allowed_domains:
        tool["filters"] = {"allowed_domains": allowed_domains}

    if search_type == "x_search" and allowed_x_handles:
        tool["allowed_x_handles"] = allowed_x_handles

    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "tools": [tool],
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