# ai_builders.py
# ─────────────────────────────────────────────────────────────
# Funções que montam o payload de cada provider
# Mexa aqui se quiser ajustar parâmetros de geração (tokens, topP, etc.)
# ou adicionar suporte a um modelo/provider novo
# ─────────────────────────────────────────────────────────────

import os
from typing import Dict, Any
from xmlrpc import client


# Payload para Google AI Studio (Gemini)
# Parâmetros configuráveis via .env: GOOGLE_MAX_OUTPUT_TOKENS
def build_google_ai_studio(prompt: str, temperature: float = 0.7, model: str = "gemini-2.5-flash") -> Dict[str, Any]:
    max_tokens = int(os.getenv("GOOGLE_MAX_OUTPUT_TOKENS", "8192"))
    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "topP": 0.95          # ajuste aqui se quiser controlar diversidade
        }
    }


# Payload para APIs estilo OpenAI (Groq, Together, OpenAI, etc.)
# Parâmetros configuráveis via .env: OPENAI_MAX_TOKENS
# Para adicionar um provider compatível, basta chamar esta função em ai_router.py
# passando o modelo correto como argumento
def build_openai_style(
    prompt: str,
    temperature: float = 0.7,
    model: str = "gpt-4o-mini"
) -> str:
    max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "1024"))

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )

    return response.choices[0].message.content