"""Builders para o módulo de vídeo (equivalente ao de texto)."""
# ai_builders.py
# ─────────────────────────────────────────────────────────────
# Funções que montam o payload de cada provider multimídia.
# Mexa aqui para ajustar parâmetros de geração (size, duration, voice, etc.)
#
# Contrato do core: cada builder é (prompt, temperature, **extras) -> dict.
#   - temperature é mantido por simetria com o core; a maioria dos
#     endpoints multimídia ignora (imagem/vídeo) ou rejeita (TTS).
#   - extras são fixados via functools.partial no ai_router.py.
#
# Estrutura (mesma lógica do core de texto):
#   SÍNCRONOS
#     build_openai_images         → DALL-E 3 / gpt-image-1
#     build_openai_audio_speech   → OpenAI TTS (input, voice)
#     build_elevenlabs_tts        → ElevenLabs REST (text, voice_settings)
#   ASSÍNCRONOS (polling + webhook)
#     build_replicate_prediction  → Replicate (version + input)
#     build_runway_task           → Runway (promptText + model + duration)
# ─────────────────────────────────────────────────────────────

import os
from typing import Any, Dict, Optional


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


# ─────────────────────────────────────────────────────────────
# SÍNCRONOS — resposta do submit já traz a mídia
# ─────────────────────────────────────────────────────────────

def build_openai_images(
    prompt: str,
    temperature: float = 0.7,   # ignorado (imagem não usa)
    model: str = "dall-e-3",
    size: str = "1024x1024",
    quality: str = "standard",
    n: int = 1,
    response_format: str = "url",   # "url" | "b64_json"
) -> Dict[str, Any]:
    """
    DALL-E 3 / gpt-image-1. Endpoint: POST /v1/images/generations.
    """
    return {
        "model": model,
        "prompt": prompt,
        "size": size,
        "quality": quality,
        "n": n,
        "response_format": response_format,
    }


def build_openai_audio_speech(
    text: str,
    temperature: float = 0.7,   # ignorado (TTS não usa)
    model: str = "tts-1",
    voice: str = "alloy",
    response_format: str = "mp3",
    speed: float = 1.0,
) -> Dict[str, Any]:
    """
    OpenAI TTS. Endpoint: POST /v1/audio/speech.
    Campo é 'input', não 'prompt' nem 'text'.
    """
    return {
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": response_format,
        "speed": speed,
    }


def build_elevenlabs_tts(
    text: str,
    temperature: float = 0.7,   # ignorado
    model_id: str = "eleven_multilingual_v2",
    stability: float = 0.5,
    similarity_boost: float = 0.75,
    style: float = 0.0,
    use_speaker_boost: bool = True,
) -> Dict[str, Any]:
    """
    ElevenLabs TTS REST binário. WebSocket (streaming full-duplex) fica
    fora do core — incompatível com o contrato HTTP.
    Endpoint: POST /v1/text-to-speech/{voice_id}.
    """
    return {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
            "style": style,
            "use_speaker_boost": use_speaker_boost,
        },
    }


# ─────────────────────────────────────────────────────────────
# ASSÍNCRONOS — submit devolve job_id; mídia vem por polling/webhook
# ─────────────────────────────────────────────────────────────

def build_replicate_prediction(
    prompt: str,
    temperature: float = 0.7,   # ignorado (modelos de imagem/vídeo não expõem)
    version: Optional[str] = None,
    input_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Replicate — cria uma prediction.
    Endpoint: POST /v1/predictions.
    Estrutura: {"version": "...", "input": {...}}.

    `version` pode vir de REPLICATE_VERSION no env se não passado.
    `input_overrides` permite sobrescrever campos específicos do modelo
    (ex.: num_inference_steps, guidance_scale, duration para modelos de vídeo).
    """
    if version is None:
        version = os.getenv("REPLICATE_VERSION", "")
        if not version:
            raise ValueError(
                "Replicate: 'version' não informado e REPLICATE_VERSION ausente no env"
            )

    payload_input: Dict[str, Any] = {"prompt": prompt}
    if input_overrides:
        payload_input.update(input_overrides)

    return {
        "version": version,
        "input": payload_input,
    }


def build_runway_task(
    prompt: str,
    temperature: float = 0.7,   # ignorado (Runway não expõe)
    model: str = "gen3a_turbo",
    duration: int = 5,
    ratio: str = "1280:768",
    seed: Optional[int] = None,
    watermark: bool = False,
) -> Dict[str, Any]:
    """
    Runway — cria uma task de vídeo.
    Endpoint: POST /v1/image_to_video (ou /v1/text_to_video).
    Estrutura: {"promptText": ..., "model": ..., "duration": ...}.

    Limite de duração vem de RUNWAY_MAX_DURATION (default 10s).
    """
    max_duration = _env_int("RUNWAY_MAX_DURATION", 10)
    if duration > max_duration:
        raise ValueError(
            f"Runway: duration={duration}s excede o limite {max_duration}s"
        )

    payload: Dict[str, Any] = {
        "model": model,
        "promptText": prompt,
        "duration": duration,
        "ratio": ratio,
        "watermark": watermark,
    }
    if seed is not None:
        payload["seed"] = seed
    return payload