import os
from typing import Dict, Any
from xmlrpc import client

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

