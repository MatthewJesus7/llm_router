# ai_builders.py
# ─────────────────────────────────────────────────────────────
# Funções que montam o payload de cada provider
# Mexa aqui se quiser ajustar parâmetros de geração (tokens, topP, etc.)
#
# Estrutura:
#   build_openai_compatible   → QUALQUER provider OpenAI chat/completions
#                               (Venice, Groq, Together, etc.)
#   build_grok_with_search    → Grok via Responses API (/v1/responses)
#                               ÚNICO endpoint que suporta web_search/x_search
#                               Usa "input" em vez de "messages"
#   build_google_ai_studio    → Gemini (formato próprio)
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
    Builder genérico para qualquer API OpenAI chat/completions-compatible.
    NÃO usar para Grok com search — use build_grok_with_search.
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
    excluded_domains: list[str] | None = None,
    allowed_x_handles: list[str] | None = None,
) -> Dict[str, Any]:
    """
    Builder para Grok via Responses API (/v1/responses).

    ⚠️  IMPORTANTE — diferenças em relação ao chat/completions:
      - Endpoint : https://api.x.ai/v1/responses   (configurado no router)
      - Chave    : "input"  (não "messages")
      - search   : "web_search" / "x_search" são server-side tools
                   e SÓ funcionam neste endpoint (doc oficial xAI)

    Parâmetros
    ----------
    search_type      : "web_search" (web geral) ou "x_search" (posts do X)
    allowed_domains  : domínios permitidos para web_search
    excluded_domains : domínios bloqueados para web_search
    allowed_x_handles: @handles permitidos para x_search
    """
    max_tokens = int(os.getenv(max_tokens_env, str(default_max_tokens)))

    tool: Dict[str, Any] = {"type": search_type}

    if search_type == "web_search":
        filters: Dict[str, Any] = {}
        if allowed_domains:
            filters["allowed_domains"] = allowed_domains
        if excluded_domains:
            filters["excluded_domains"] = excluded_domains
        if filters:
            tool["filters"] = filters

    if search_type == "x_search" and allowed_x_handles:
        tool["allowed_x_handles"] = allowed_x_handles

    return {
        "model": model,
        # Responses API usa "input", não "messages"
        "input": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_output_tokens": max_tokens,  # Responses API usa max_output_tokens
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