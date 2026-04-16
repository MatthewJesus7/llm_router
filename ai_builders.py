# ai_builders.py
# ─────────────────────────────────────────────────────────────
# Funções que montam o payload de cada provider
# Mexa aqui se quiser ajustar parâmetros de geração (tokens, topP, etc.)
# ou adicionar suporte a um modelo/provider novo
# ─────────────────────────────────────────────────────────────

import os
from typing import Dict, Any
# from openai import OpenAI  # opcional, só para providers estilo OpenAI (Groq, Together, etc.)


# Payload para Google AI Studio (Gemini)
# Parâmetros configuráveis via .env: GOOGLE_MAX_Ofrom openai import OpenAI  # pip install openaiUTPUT_TOKENS


# Payload para APIs estilo OpenAI (Groq, Together, OpenAI, etc.)
# Parâmetros configuráveis via .env: OPENAI_MAX_TOKENS
# Para adicionar um provider compatível, basta chamar esta função em ai_router.py
# passando o modelo correto como argumento

def build_openai_style(prompt: str, temperature: float = 0.7, model: str = "gpt-4o-mini") -> str:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "1024"))
    
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content


def build_google_ai_studio(prompt: str, temperature: float = 0.7, model: str = "gemini-2.5-flash") -> Dict[str, Any]:
    max_tokens = int(os.getenv("GOOGLE_MAX_OUTPUT_TOKENS", "8192"))
    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "topP": 0.95
        }
    }

def build_deepseek_payload(prompt: str, temperature: float = 0.7, model: str = "deepseek-chat") -> Dict[str, Any]:
    """
    Monta payload compatível com a API da DeepSeek.
    Formato OpenAI-compatible (mesmo do Grok, OpenAI, etc).
    Modelos principais:
    - "deepseek-chat": DeepSeek-V3.2 (modo normal, rápido e geral)
    - "deepseek-reasoner": DeepSeek-V3.2 (modo thinking/reasoning, mais poderoso para tarefas complexas)
    """
    max_tokens = int(os.getenv("DEEPSEEK_MAX_TOKENS", "65536"))  # ajuste conforme necessidade
    return {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False
    }

def build_grok_payload(prompt: str, temperature: float = 0.7, model: str = "grok-beta") -> Dict[str, Any]:
    """
    Monta payload compatível com a API da xAI (Grok).
    Formato OpenAI-compatible (mesmo do OpenAI, Anthropic, etc).
    """
    max_tokens = int(os.getenv("GROK_MAX_TOKENS", "10000"))
    return {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False
    }


def build_venice_payload(prompt: str, temperature: float = 0.7, model: str = "venice-uncensored-1-2") -> Dict[str, Any]:
    """
    Monta payload compatível com a API da Venice.ai.
    Formato OpenAI-compatible (igual DeepSeek e Grok).
    Modelos recomendados:
    - "venice-uncensored-1-2"     → uncensored (o mais famoso deles)
    - "zai-org-glm-4.7"           → flagship forte em raciocínio
    - "grok-41-fast"              → rápido e bom
    Troque o default no lambda lá embaixo se quiser outro modelo.
    """
    max_tokens = int(os.getenv("VENICE_MAX_TOKENS", "8192"))
    return {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,          # eles aceitam (max_completion_tokens também funciona, mas max_tokens ainda é ok)
        "stream": False
    }