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