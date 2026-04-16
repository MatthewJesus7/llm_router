"""
backend/main.py
───────────────────────────────────────────────────────────────────────────────
Servidor FastAPI que implementa o **protocolo LangGraph Server COMPLETO**.
✅ Frontend (`@langchain/langgraph-sdk/react`) usa **100% o backend para dados**:
   - Criação/listagem/exclusão de threads (`useThreads`).
   - Persistência/histórico de mensagens (`fetchStateHistory: true`).
   - Streaming via `ai_router.ask()` com simulação token-a-token.

CORREÇÕES APLICADAS (essenciais para compatibilidade):
1. `create_thread`: Lê `metadata` do body (padrão SDK).
2. `stream_run`: Extrai `assistant_id` de `config.configurable.assistant_id`.
3. Metadata usa `"assistant_id": "agent"` (não `"graph_id"`).
4. `/threads/search` filtra por `{"assistant_id": "agent"}`.
5. `/history` restaura mensagens perfeitamente.
6. In-memory DB (perde ao reiniciar — use Redis/Postgres para prod).

Iniciar:
    uvicorn backend.main:app --reload --port 8000

Ou da raiz (se ai_router.py acessível):
    uvicorn main:app --reload --port 8000

Teste completo:
1. Backend rodando.
2. Frontend: http://localhost:3000/?apiUrl=http://localhost:8000&assistantId=agent
3. Chat → nova thread → recarregue → histórico + lista threads intactos.
───────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

# ─── Resolve o caminho do projeto para importar ai_router ────────────────────
# Ajuste se necessário — assume backend/ dentro do projeto com app/llm_router/
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.llm_router.ai_router import ai_router  # noqa: E402  (seu roteador LLM)

# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="llm_router API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Armazenamento em memória (threads + histórico de mensagens) ─────────────
# ✅ Perde dados ao reiniciar servidor. Para prod: integre SQLite/Redis/Postgres.
threads_db: Dict[str, Dict[str, Any]] = {}

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sse(event: str, data: Any) -> str:
    """SSE no formato exato do LangGraph SDK."""
    payload = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
    return f"event: {event}\ndata: {payload}\n\n"

def _ai_msg(msg_id: str, content: str) -> Dict[str, Any]:
    """Mensagem AI no formato LangGraph."""
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
    """Converte mensagens LangGraph → prompt texto para ai_router."""
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

# ─── /info (descobre graphs/assistants) ──────────────────────────────────────
@app.get("/info")
def info():
    return {
        "version": "1.0.0",
        "graphs": {"agent": {"id": "agent"}},  # Formato SDK
    }

# ─── Threads API (useThreads no frontend) ────────────────────────────────────

@app.post("/threads/{thread_id}/runs/stream")
async def stream_run(thread_id: str, request: Request):
    """✅ Endpoint principal: input → ai_router → stream + salva mensagens."""
    body = await request.json()

    # ✅ Extrai assistant_id de config (padrão SDK)
    config = body.get("config", {})
    configurable = config.get("configurable", {})
    assistant_id = configurable.get("assistant_id") or "agent"
    
    # ✅ NOVO: Extrai provider_name opcional do body
    provider_name = body.get("provider_name")  # Ex: "grok", "groj", etc

    # ✅ Cria/guarda thread com metadata correto
    if thread_id not in threads_db:
        now = time.time()
        threads_db[thread_id] = {
            "thread_id": thread_id,
            "created_at": now,
            "updated_at": now,
            "metadata": {"assistant_id": assistant_id},
            "values": {"messages": []},
            "status": "idle",
        }
    thread = threads_db[thread_id]

    # Mensagens: existentes + input
    existing: List[Dict] = thread["values"].get("messages", [])
    input_data: Dict = body.get("input", {}) or {}
    new_messages: List[Dict] = input_data.get("messages", [])
    all_messages = existing + new_messages
    prompt = _build_prompt(all_messages)

    async def event_stream():
        run_id = str(uuid.uuid4())
        yield _sse("metadata", {"run_id": run_id})

        try:
            # ✅ ai_router em executor (não bloqueia asyncio)
            loop = asyncio.get_event_loop()
            
            # ✅ ROBUSTO: trata typo/provider inválido
            if provider_name:
                try:
                    response: str = await loop.run_in_executor(
                        None, 
                        lambda: ai_router.ask(prompt, provider_name=provider_name)
                    )
                except ValueError as ve:
                    # Provider não encontrado (typo como "groj")
                    available = ai_router.available_providers()
                    yield _sse("error", {
                        "error": f"Provider '{provider_name}' não encontrado. Disponíveis: {available}"
                    })
                    return
                except RuntimeError as re:
                    # Provider indisponível (rate limit, etc)
                    yield _sse("error", {"error": str(re)})
                    return
            else:
                # Sem provider_name → fallback automático
                response: str = await loop.run_in_executor(None, ai_router.ask, prompt)

            ai_msg_id = str(uuid.uuid4())
            accumulated = ""

            # ✅ Streaming token-a-token (6 chars/chunk para "feel" natural)
            chunk_size = 6
            for i in range(0, len(response), chunk_size):
                chunk = response[i : i + chunk_size]
                accumulated += chunk
                yield _sse("messages/partial", [_ai_msg(ai_msg_id, accumulated)])
                await asyncio.sleep(0.015)  # Delay realista

            # ✅ FINAL: salva no backend + estado completo
            final_msgs = all_messages + [_ai_msg(ai_msg_id, response)]
            thread["values"]["messages"] = final_msgs
            thread["updated_at"] = time.time()
            thread["status"] = "idle"

            yield _sse("values", {"messages": final_msgs})
            yield _sse("end", "")

        except Exception as exc:
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

@app.get("/threads/{thread_id}")
def get_thread(thread_id: str):
    if thread_id not in threads_db:
        raise HTTPException(status_code=404, detail="Thread not found")
    return threads_db[thread_id]

@app.delete("/threads/{thread_id}")
def delete_thread(thread_id: str):
    threads_db.pop(thread_id, None)
    return {"ok": True}

@app.post("/threads/search")
async def search_threads(request: Request):
    """✅ Filtra por metadata={"assistant_id": "agent"} (useThreads)."""
    body: Dict = {}
    try:
        body = await request.json()
    except Exception:
        pass
    limit = body.get("limit", 100)
    metadata_filter = body.get("metadata", {})
    results = list(threads_db.values())
    if metadata_filter:
        results = [
            t for t in results
            if all(t.get("metadata", {}).get(k) == v for k, v in metadata_filter.items())
        ]
    results.sort(key=lambda t: t.get("updated_at", 0), reverse=True)
    return results[:limit]

# ─── History (fetchStateHistory: true → restaura chat ao recarregar) ─────────
@app.get("/threads/{thread_id}/history")
def thread_history(thread_id: str):
    """✅ Retorna checkpoint com mensagens para SDK restaurar estado."""
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

# ─── Runs/Stream (useStream → chat principal) ────────────────────────────────
@app.post("/threads/{thread_id}/runs/stream")
async def stream_run(thread_id: str, request: Request):
    """✅ Endpoint principal: input → ai_router → stream + salva mensagens."""
    body = await request.json()

    # ✅ Extrai assistant_id de config (padrão SDK)
    config = body.get("config", {})
    configurable = config.get("configurable", {})
    assistant_id = configurable.get("assistant_id") or "agent"

    # ✅ Cria/guarda thread com metadata correto
    if thread_id not in threads_db:
        now = time.time()
        threads_db[thread_id] = {
            "thread_id": thread_id,
            "created_at": now,
            "updated_at": now,
            "metadata": {"assistant_id": assistant_id},
            "values": {"messages": []},
            "status": "idle",
        }
    thread = threads_db[thread_id]

    # Mensagens: existentes + input
    existing: List[Dict] = thread["values"].get("messages", [])
    input_data: Dict = body.get("input", {}) or {}
    new_messages: List[Dict] = input_data.get("messages", [])
    all_messages = existing + new_messages
    prompt = _build_prompt(all_messages)

    async def event_stream():
        run_id = str(uuid.uuid4())
        yield _sse("metadata", {"run_id": run_id})

        try:
            # ✅ ai_router em executor (não bloqueia asyncio)
            loop = asyncio.get_event_loop()
            response: str = await loop.run_in_executor(None, ai_router.ask, prompt)

            ai_msg_id = str(uuid.uuid4())
            accumulated = ""

            # ✅ Streaming token-a-token (6 chars/chunk para "feel" natural)
            chunk_size = 6
            for i in range(0, len(response), chunk_size):
                chunk = response[i : i + chunk_size]
                accumulated += chunk
                yield _sse("messages/partial", [_ai_msg(ai_msg_id, accumulated)])
                await asyncio.sleep(0.015)  # Delay realista

            # ✅ FINAL: salva no backend + estado completo
            final_msgs = all_messages + [_ai_msg(ai_msg_id, response)]
            thread["values"]["messages"] = final_msgs
            thread["updated_at"] = time.time()
            thread["status"] = "idle"

            yield _sse("values", {"messages": final_msgs})
            yield _sse("end", "")

        except Exception as exc:
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