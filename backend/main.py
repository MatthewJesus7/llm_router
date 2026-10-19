# ─────────────────────────────────────────────────────────────
# Ponto de entrada da API FastAPI (Stateless & Privacy-First com Auditoria)
# ─────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# ─── Project root ─────────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from engine.ai_router import ai_router  # noqa: E402

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("main")

# ─── App Initialization & CORS ──────────────────────────────────────────────
app = FastAPI(title="llm_router API", version="2.1.0")

_ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _sse(event: str, data: Any) -> str:
    payload = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
    return f"event: {event}\ndata: {payload}\n\n"


def _ai_msg(msg_id: str, content: str) -> Dict[str, Any]:
    return {
        "id": msg_id,
        "type": "ai",
        "content": content,
        "additional_kwargs": {},
        "response_metadata": {},
        "tool_calls": [],
        "invalid_tool_calls": [],
    }


def _build_prompt(messages: List[Dict]) -> str:
    parts: List[str] = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        role = msg.get("type", "human")
        if role == "system":
            parts.insert(0, f"System: {content}")
        elif role == "human":
            parts.append(f"Human: {content}")
        elif role == "ai":
            parts.append(f"Assistant: {content}")
    parts.append("Assistant:")
    return "\n\n".join(parts)


# ─── Endpoints: /info ─────────────────────────────────────────────────────────

@app.get("/info")
def info():
    provider_names = [p.name for p in ai_router.providers] if ai_router else []
    return {
        "version": "2.1.0",
        "graphs": {"agent": {"id": "agent"}},
        "providers": provider_names,
    }


# ─── Endpoints: Stream com Auditoria Total ───────────────────────────────────

@app.post("/threads/{thread_id}/runs/stream")
async def stream_run(thread_id: str, request: Request):
    t_start_request = time.perf_counter()
    body = await request.json()

    provider_name: Optional[str] = body.get("provider_name")
    input_data: Dict = body.get("input", {}) or {}
    new_messages: List[Dict] = input_data.get("messages", [])
    
    logger.info(f"[{thread_id}] AUDIT REQ | payload_size={len(json.dumps(body))} bytes | msgs={len(new_messages)} | provider={provider_name}")

    if not provider_name:
        logger.error(f"[{thread_id}] provider_name ausente no body da requisição.")

    prompt = _build_prompt(new_messages)

    async def event_stream():
        run_id = str(uuid.uuid4())
        yield _sse("metadata", {"run_id": run_id})

        if not provider_name:
            yield _sse("error", {
                "error": "provider_name não foi enviado. Inclua 'provider_name' no body da requisição.",
            })
            return

        try:
            loop = asyncio.get_event_loop()
            t_start_ai = time.perf_counter()

            try:
                response: str = await loop.run_in_executor(
                    None,
                    lambda: ai_router.ask(prompt, provider_name=provider_name),
                )
            except (ValueError, RuntimeError) as exc:
                available = getattr(ai_router, "available_providers", lambda: [])()
                logger.error(f"[{thread_id}] AUDIT ERRO AI | tempo={(time.perf_counter() - t_start_ai):.3f}s | erro={exc}")
                yield _sse("error", {
                    "error": str(exc),
                    "available_providers": available,
                })
                return

            t_ai_duration = time.perf_counter() - t_start_ai
            logger.info(f"[{thread_id}] AUDIT AI OK | tempo_resposta={t_ai_duration:.3f}s | chars={len(response)}")

            ai_msg_id = str(uuid.uuid4())
            t_start_stream = time.perf_counter()

            # Envio direto da resposta completa sem fatiamento artificial aleatório
            yield _sse("messages/partial", [_ai_msg(ai_msg_id, response)])

            t_stream_duration = time.perf_counter() - t_start_stream
            t_total_duration = time.perf_counter() - t_start_request

            logger.info(f"[{thread_id}] AUDIT SUMMARY (Direct) | tempo_stream={t_stream_duration:.3f}s | tempo_total={t_total_duration:.3f}s | chars={len(response)}")

            final_msgs = new_messages + [_ai_msg(ai_msg_id, response)]
            yield _sse("values", {"messages": final_msgs})
            yield _sse("end", "")

        except Exception as exc:
            logger.exception(f"[{thread_id}] AUDIT EXCEPTION: {exc}")
            yield _sse("error", {"error": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)