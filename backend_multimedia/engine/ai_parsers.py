"""Parsers de resposta do módulo de vídeo (jobs, status, URLs)."""
# ai_parsers.py
# ─────────────────────────────────────────────────────────────
# Parsers multimídia — implementam os contratos do ai_core:
#
#   SubmitParser  : Response -> str | (str, MediaResult | None)
#   StatusParser  : Response -> (JobStatus, MediaResult | None, str | None)
#   WebhookParser : dict     -> (JobStatus, MediaResult | None, str | None)
#
# Cada parser é puro: só lê a resposta/payload e devolve o contrato.
# Estrutura inesperada levanta ValueError/KeyError → o core trata
# como PARSE_ERROR e força cooldown.
# ─────────────────────────────────────────────────────────────

import base64
import uuid
from typing import Any, Dict, Optional, Tuple

from engine.ai_core import JobStatus, MediaResult


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _sync_job_id(prefix: str) -> str:
    """Job id sintético para respostas síncronas (sem id real do provider).
    Serve para logging/correlação; não é usado em polling nem webhook."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _first_url(output: Any) -> Optional[str]:
    """Extrai a 1ª URL de formatos comuns: str, list[str], dict{'url'}, list[dict]."""
    if output is None:
        return None
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        return output.get("url")
    if isinstance(output, list) and output:
        return _first_url(output[0])
    return None


# ─────────────────────────────────────────────────────────────
# OpenAI Images (DALL-E) — SÍNCRONO
# POST /v1/images/generations
#   → {"created": ..., "data": [{"url": "..."} | {"b64_json": "..."}]}
# ─────────────────────────────────────────────────────────────

def openai_images_submit(resp) -> Tuple[str, MediaResult]:
    data = resp.json().get("data") or []
    if not data:
        raise ValueError("OpenAI images: 'data' vazio")
    item = data[0]

    if item.get("b64_json"):
        # DALL-E devolve PNG por padrão; caller pode ajustar mime_type se souber
        return (
            _sync_job_id("openai-img"),
            MediaResult(
                data=base64.b64decode(item["b64_json"]),
                mime_type="image/png",
            ),
        )

    url = item.get("url")
    if not url:
        raise ValueError("OpenAI images: nem 'url' nem 'b64_json' na resposta")
    return _sync_job_id("openai-img"), MediaResult(url=url)


# ─────────────────────────────────────────────────────────────
# OpenAI TTS — SÍNCRONO (corpo binário)
# POST /v1/audio/speech → bytes (Content-Type: audio/mpeg)
# ─────────────────────────────────────────────────────────────

def openai_tts_submit(resp) -> Tuple[str, MediaResult]:
    if not resp.content:
        raise ValueError("OpenAI TTS: corpo vazio")
    return (
        _sync_job_id("openai-tts"),
        MediaResult(
            data=resp.content,
            mime_type=resp.headers.get("Content-Type", "audio/mpeg"),
        ),
    )


# ─────────────────────────────────────────────────────────────
# ElevenLabs TTS — SÍNCRONO (corpo binário)
# POST /v1/text-to-speech/{voice_id}
#
# Nota: o modo WebSocket (streaming full-duplex) da doc está FORA
# do escopo do core HTTP — não tem análogo síncrono aqui.
# ─────────────────────────────────────────────────────────────

def elevenlabs_tts_submit(resp) -> Tuple[str, MediaResult]:
    if not resp.content:
        raise ValueError("ElevenLabs TTS: corpo vazio")
    return (
        _sync_job_id("eleven-tts"),
        MediaResult(
            data=resp.content,
            mime_type=resp.headers.get("Content-Type", "audio/mpeg"),
        ),
    )


# ─────────────────────────────────────────────────────────────
# Replicate — ASSÍNCRONO (polling + webhook)
# POST /v1/predictions          → {"id": "abc", "status": "starting", ...}
# GET  /v1/predictions/{id}     → mesmo formato
# Webhook (POST do provider)    → mesmo formato
# status ∈ {starting, processing, succeeded, failed, canceled}
# ─────────────────────────────────────────────────────────────

_REPLICATE_STATUS = {
    "starting":   JobStatus.PENDING,
    "processing": JobStatus.RUNNING,
    "succeeded":  JobStatus.SUCCEEDED,
    "failed":     JobStatus.FAILED,
    "canceled":   JobStatus.CANCELLED,
}


def _parse_replicate(data: Dict[str, Any]):
    raw = (data.get("status") or "").lower()
    status = _REPLICATE_STATUS.get(raw)
    if status is None:
        raise ValueError(f"Replicate: status desconhecido '{raw}'")

    result = None
    if status == JobStatus.SUCCEEDED:
        url = _first_url(data.get("output"))
        if url:
            result = MediaResult(url=url)
    return status, result, data.get("error")


def replicate_submit(resp) -> str:
    job_id = resp.json().get("id")
    if not job_id:
        raise ValueError("Replicate submit: resposta sem 'id'")
    return job_id


def replicate_status(resp):
    return _parse_replicate(resp.json())


def replicate_webhook(payload: Dict[str, Any]):
    return _parse_replicate(payload)


# ─────────────────────────────────────────────────────────────
# Runway — ASSÍNCRONO (polling + webhook)
# POST /v1/image_to_video   → {"id": "..."}
# GET  /v1/tasks/{id}       → {"id": "...", "status": "...", "output": ["url"]}
# Webhook (POST do provider)→ mesmo formato
# status ∈ {PENDING, THROTTLED, RUNNING, SUCCEEDED, FAILED}
# ─────────────────────────────────────────────────────────────

_RUNWAY_STATUS = {
    "pending":   JobStatus.PENDING,
    "throttled": JobStatus.PENDING,
    "running":   JobStatus.RUNNING,
    "succeeded": JobStatus.SUCCEEDED,
    "failed":    JobStatus.FAILED,
}


def _parse_runway(data: Dict[str, Any]):
    raw = (data.get("status") or "").lower()
    status = _RUNWAY_STATUS.get(raw)
    if status is None:
        raise ValueError(f"Runway: status desconhecido '{raw}'")

    result = None
    if status == JobStatus.SUCCEEDED:
        url = _first_url(data.get("output"))
        if url:
            result = MediaResult(url=url)
    return status, result, data.get("failure") or data.get("error")


def runway_submit(resp) -> str:
    job_id = resp.json().get("id")
    if not job_id:
        raise ValueError("Runway submit: resposta sem 'id'")
    return job_id


def runway_status(resp):
    return _parse_runway(resp.json())


def runway_webhook(payload: Dict[str, Any]):
    return _parse_runway(payload)