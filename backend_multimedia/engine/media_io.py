# media_io.py
# ─────────────────────────────────────────────────────────────
# I/O de mídia — fora do core (eixo 14).
# Recebe um MediaResult e materializa em bytes/arquivo.
# ─────────────────────────────────────────────────────────────

import requests
from typing import Optional

from engine.ai_core import MediaResult


def download(result: MediaResult, timeout: int = 120) -> bytes:
    if result.data is not None:
        return result.data
    if not result.url:
        raise ValueError("MediaResult sem URL nem bytes")
    r = requests.get(result.url, timeout=timeout)
    r.raise_for_status()
    result.data = r.content
    if not result.mime_type:
        result.mime_type = r.headers.get("Content-Type")
    return result.data


def save(result: MediaResult, path: str, timeout: int = 120) -> str:
    with open(path, "wb") as f:
        f.write(download(result, timeout=timeout))
    return path