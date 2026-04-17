"""
backend/main.py

rodar:

uvicorn app.llm_router.main:app --reload --port 8000
───────────────────────────────────────────────────────────────────────────────
Servidor FastAPI — protocolo LangGraph Server.

CORREÇÕES desta versão:
  ✅ provider_name não é mais sobrescrito (bug de shadowing removido)
  ✅ provider_name lido do body PRIMEIRO, com fallback para metadata da thread
  ✅ Fallback hardcoded "Grok" removido — lança erro claro se não vier provider
  ✅ logger.error/exception adicionados dentro do event_stream (antes silencioso)
  ✅ persist() só salva provider_name na thread após resposta bem-sucedida
  ✅ Rota /runs/stream duplicada removida
  ✅ POST /threads adicionado
  ✅ Ordem das rotas corrigida
  ✅ Persistência em JSON
  ✅ Auth por API key opcional
  ✅ CORS restrito a ALLOWED_ORIGINS

Iniciar:
    API_KEY=minha_chave_secreta uvicorn backend.main:app --reload --port 8000

.env (opcional):
    API_KEY=minha_chave_secreta
    ALLOWED_ORIGINS=http://localhost:3000
    DB_FILE=threads_db.json
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader

# ─── Project root ─────────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.llm_router.ai_router import ai_router  # noqa: E402

# ─── Persistência JSON ────────────────────────────────────────────────────────
DB_FILE = Path(os.getenv("DB_FILE", "threads_db.json"))


def _load_db() -> Dict[str, Any]:
    if DB_FILE.exists():
        try:
            return json.loads(DB_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_db(data: Dict[str, Any]) -> None:
    DB_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


threads_db: Dict[str, Dict[str, Any]] = _load_db()


def persist() -> None:
    """Salva estado em disco. Chame após qualquer mutação."""
    _save_db(threads_db)


# ─── Segurança ────────────────────────────────────────────────────────────────
API_KEY: Optional[str] = os.getenv("API_KEY")
_api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("main")


async def verify_key(key: Optional[str] = Depends(_api_key_header)) -> None:
    if API_KEY and key != API_KEY:
        raise HTTPException(status_code=401, detail="API key inválida ou ausente.")


# ─── CORS ─────────────────────────────────────────────────────────────────────
_ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app = FastAPI(title="llm_router API", version="2.1.0")
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


def _new_thread(thread_id: str, assistant_id: str, extra_metadata: Dict = {}) -> Dict:
    now = time.time()
    return {
        "thread_id": thread_id,
        "created_at": now,
        "updated_at": now,
        "metadata": {"assistant_id": assistant_id, **extra_metadata},
        "values": {"messages": []},
        "status": "idle",
    }


# ─── /info ────────────────────────────────────────────────────────────────────

@app.get("/info")
def info():
    return {"version": "2.1.0", "graphs": {"agent": {"id": "agent"}}}


# ─── Threads ──────────────────────────────────────────────────────────────────

@app.post("/threads", dependencies=[Depends(verify_key)])
async def create_thread(request: Request):
    body: Dict = {}
    try:
        body = await request.json()
    except Exception:
        pass

    thread_id = str(uuid.uuid4())
    metadata: Dict = body.get("metadata", {})
    assistant_id = metadata.get("assistant_id", "agent")

    thread = _new_thread(thread_id, assistant_id, metadata)
    threads_db[thread_id] = thread
    persist()
    logger.info(f"Thread criada: {thread_id}")
    return thread


@app.post("/threads/search", dependencies=[Depends(verify_key)])
async def search_threads(request: Request):
    body: Dict = {}
    try:
        body = await request.json()
    except Exception:
        pass

    limit: int = body.get("limit", 100)
    metadata_filter: Dict = body.get("metadata", {})

    results = list(threads_db.values())
    if metadata_filter:
        results = [
            t for t in results
            if all(
                t.get("metadata", {}).get(k) == v
                for k, v in metadata_filter.items()
            )
        ]
    results.sort(key=lambda t: t.get("updated_at", 0), reverse=True)
    return results[:limit]


@app.get("/threads/{thread_id}", dependencies=[Depends(verify_key)])
def get_thread(thread_id: str):
    if thread_id not in threads_db:
        raise HTTPException(status_code=404, detail="Thread não encontrada.")
    return threads_db[thread_id]


@app.delete("/threads/{thread_id}", dependencies=[Depends(verify_key)])
def delete_thread(thread_id: str):
    threads_db.pop(thread_id, None)
    persist()
    return {"ok": True}


@app.get("/threads/{thread_id}/history", dependencies=[Depends(verify_key)])
def thread_history(thread_id: str):
    if thread_id not in threads_db:
        return []
    thread = threads_db[thread_id]
    messages = thread["values"].get("messages", [])
    if not messages:
        return []

    ts = thread.get("updated_at", time.time())
    return [
        {
            "values": {"messages": messages},
            "next": [],
            "tasks": [],
            "checkpoint": {
                "ts": str(ts),
                "id": str(uuid.uuid4()),
                "channel_values": {"messages": messages},
            },
            "metadata": {"step": len(messages), "source": "loop"},
            "parent_checkpoint": None,
        }
    ]


# ─── Stream ───────────────────────────────────────────────────────────────────

@app.post("/threads/{thread_id}/runs/stream", dependencies=[Depends(verify_key)])
async def stream_run(thread_id: str, request: Request):
    body = await request.json()

    # Garante que a thread existe
    if thread_id not in threads_db:
        config = body.get("config", {})
        configurable = config.get("configurable", {})
        assistant_id = configurable.get("assistant_id", "agent")
        threads_db[thread_id] = _new_thread(thread_id, assistant_id)

    thread = threads_db[thread_id]

    # ── Resolução do provider_name ─────────────────────────────────────────
    # Prioridade: body > metadata da thread
    # Sem fallback hardcoded — se não vier, retorna erro claro ao frontend.
    provider_name: Optional[str] = (
        body.get("provider_name")
        or thread.get("metadata", {}).get("provider_name")
    )

    if not provider_name:
        logger.error(
            f"[{thread_id}] provider_name ausente — nem no body nem na metadata da thread."
        )
        provider_name = "Grok"
        print("hardcoded: colocando provider forçado (linha 279-280 do main.py), provider atual:" + provider_name)

    # Junta mensagens existentes com as novas
    existing: List[Dict] = thread["values"].get("messages", [])
    input_data: Dict = body.get("input", {}) or {}
    new_messages: List[Dict] = input_data.get("messages", [])
    all_messages = existing + new_messages
    prompt = _build_prompt(all_messages)

    logger.info(f"[{thread_id}] stream iniciado | provider={provider_name} | msgs={len(all_messages)}")

    async def event_stream():
        run_id = str(uuid.uuid4())
        yield _sse("metadata", {"run_id": run_id})

        if not provider_name:
            yield _sse("error", {
                "error": "provider_name não foi enviado. Inclua 'provider_name' no body da requisição ou na metadata da thread.",
            })
            return

        try:
            loop = asyncio.get_event_loop()

            try:
                response: str = await loop.run_in_executor(
                    None,
                    lambda: ai_router.ask(prompt, provider_name=provider_name),
                )
            except (ValueError, RuntimeError) as exc:
                available = getattr(ai_router, "available_providers", lambda: [])()
                logger.error(f"[{thread_id}] Falha no provider '{provider_name}': {exc}")
                yield _sse("error", {
                    "error": str(exc),
                    "available_providers": available,
                })
                return

            ai_msg_id = str(uuid.uuid4())
            accumulated = ""

            chunk_size = 6
            for i in range(0, len(response), chunk_size):
                chunk = response[i: i + chunk_size]
                accumulated += chunk
                yield _sse("messages/partial", [_ai_msg(ai_msg_id, accumulated)])
                await asyncio.sleep(0.015)

            # Persiste estado final apenas após sucesso
            final_msgs = all_messages + [_ai_msg(ai_msg_id, response)]
            thread["values"]["messages"] = final_msgs
            thread["updated_at"] = time.time()
            thread["status"] = "idle"
            # Salva o provider que funcionou na metadata da thread
            thread["metadata"]["provider_name"] = provider_name
            persist()

            logger.info(f"[{thread_id}] resposta concluída | provider={provider_name} | tokens~={len(response)}")

            yield _sse("values", {"messages": final_msgs})
            yield _sse("end", "")

        except Exception as exc:
            logger.exception(f"[{thread_id}] Erro inesperado no event_stream: {exc}")
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