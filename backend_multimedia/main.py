# main.py
"""CLI de teste do módulo de geração de vídeo (multimídia)."""

import argparse
import sys
from pathlib import Path

from engine.ai_core import (
    JobStatus, MediaResult, MediaRouterError, PollTimeout, JobFailed,
)
from engine.ai_router import ai_router, create_ai_router
from engine import media_io


# ─────────────────────────────────────────────────────────────
# Facade síncrona: ask + (poll se preciso) + save opcional
# (eixo 13 — pertence ao main, não ao core)
# ─────────────────────────────────────────────────────────────

def generate(manager, prompt: str, *, temperature: float = 0.7,
             provider_name: str = None, timeout: float = 600.0,
             out_path: str = None) -> MediaResult:
    job = manager.ask(prompt, temperature, provider_name)

    if job.terminal:
        if job.status == JobStatus.SUCCEEDED and job.result is not None:
            result = job.result
        else:
            raise JobFailed(job)
    else:
        result = manager.poll(job, timeout=timeout)

    if out_path:
        media_io.save(result, out_path)
        print(f"[ok] salvo em {out_path}")
    return result


# ─────────────────────────────────────────────────────────────
# Helpers de CLI
# ─────────────────────────────────────────────────────────────

_EXT_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
}


def _default_out(result: MediaResult, prefix: str) -> str:
    ext = _EXT_BY_MIME.get((result.mime_type or "").split(";")[0].strip(), ".bin")
    return f"{prefix}{ext}"


def _get_manager():
    manager = ai_router or create_ai_router()
    if manager is None:
        print("[erro] nenhum provider multimídia configurado", file=sys.stderr)
        sys.exit(2)
    return manager


# ─────────────────────────────────────────────────────────────
# Subcomandos
# ─────────────────────────────────────────────────────────────

def cmd_list(_args) -> int:
    manager = _get_manager()
    names = manager.available_providers()
    if not names:
        print("(nenhum provider)")
        return 0
    for name in names:
        print(name)
    return 0


def cmd_generate(args) -> int:
    manager = _get_manager()

    try:
        result = generate(
            manager,
            args.prompt,
            temperature=args.temperature,
            provider_name=args.provider,
            timeout=args.timeout,
        )
    except JobFailed as e:
        print(f"[job falhou] {e}", file=sys.stderr)
        print(f"[detalhe] status={e.job.status.value} erro={e.job.error}", file=sys.stderr)
        return 1
    except PollTimeout as e:
        print(f"[timeout] {e}", file=sys.stderr)
        return 1
    except MediaRouterError as e:
        print(f"[router] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[erro] {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    out_path = args.out or _default_out(result, "output")
    media_io.save(result, out_path)
    print(f"[ok] {out_path} (mime={result.mime_type or '?'})")
    return 0


# ─────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="CLI de teste do módulo multimídia (imagem | vídeo | áudio)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="lista providers disponíveis")
    p_list.set_defaults(func=cmd_list)

    p_gen = sub.add_parser("generate", help="gera mídia a partir de um prompt")
    p_gen.add_argument("prompt", help="prompt de geração")
    p_gen.add_argument("--provider", "-p", default=None,
                       help="nome exato do provider (use 'list' para ver)")
    p_gen.add_argument("--out", "-o", default=None,
                       help="caminho de saída (default: output.<ext> inferido do MIME)")
    p_gen.add_argument("--timeout", "-t", type=float, default=600.0,
                       help="timeout de polling em segundos (default: 600)")
    p_gen.add_argument("--temperature", type=float, default=0.7,
                       help="temperature (ignorada por imagem/vídeo, útil p/ áudio)")
    p_gen.set_defaults(func=cmd_generate)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())