# core.py
# ─────────────────────────────────────────────────────────────
# Motor do roteador — não precisa mexer aqui
# Contém a lógica de rate limit, fallback e seleção de providers
# ─────────────────────────────────────────────────────────────

import os
import time
import threading
import requests
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any, List

logger = logging.getLogger("ai-router")


# Representa um provider de IA com suas configurações e estado de uso
# Instâncias são criadas em ai_router.py — não instancie diretamente aqui
@dataclass
class AIProvider:
    name: str
    api_key_env: str
    endpoint: str
    make_headers: Callable[[str], Dict[str, str]]
    build_payload: Callable[[str, float], Dict[str, Any]]
    parse_response: Callable[[requests.Response], str]
    usage_limit: int = 100
    window_seconds: int = 60
    used_count: int = 0
    window_start: float = field(default_factory=lambda: time.time())
    exhausted_until: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)
    model: str = "default"
    timeout: int = 30

    def has_key(self) -> bool:
        return bool(os.getenv(self.api_key_env))

    def reset_window_if_needed(self):
        now = time.time()
        if now - self.window_start >= self.window_seconds:
            logger.debug(f"[{self.name}] reset de janela de uso")
            self.window_start = now
            self.used_count = 0

    def can_use(self) -> bool:
        try:
            with self.lock:
                self.reset_window_if_needed()
                now = time.time()
                if now < self.exhausted_until:
                    logger.debug(f"[{self.name}] ainda em cooldown")
                    return False
                available = self.used_count < self.usage_limit
                if not available:
                    logger.debug(f"[{self.name}] limite de uso atingido")
                return available
        except Exception as e:
            logger.exception(f"[{self.name}] erro em can_use: {e}")
            return False

    def mark_usage(self, count: int = 1):
        with self.lock:
            self.used_count += count
            logger.debug(f"[{self.name}] uso incrementado: {self.used_count}/{self.usage_limit}")
            if self.used_count >= self.usage_limit:
                self.exhausted_until = self.window_start + self.window_seconds
                logger.warning(f"[{self.name}] entrou em cooldown (rate limit interno)")

    def force_exhaust(self, ttl_seconds: int):
        with self.lock:
            self.exhausted_until = time.time() + ttl_seconds
            logger.warning(f"[{self.name}] forçado para cooldown por {ttl_seconds}s")

    def send(self, prompt: str, temperature: float = 0.7) -> requests.Response:
        key = os.getenv(self.api_key_env)
        if not key:
            raise RuntimeError(f"API key for {self.name} not found")
        headers = self.make_headers(key)
        payload = self.build_payload(prompt, temperature)
        logger.debug(f"[{self.name}] enviando request")
        return requests.post(
            self.endpoint,
            headers=headers,
            json=payload,
            timeout=self.timeout
        )


# Gerencia a lista de providers e implementa o fallback automático entre eles
# O roteamento é round-robin com pulo automático em caso de erro ou rate limit
class ProviderManager:
    def __init__(self, providers: List[AIProvider]):
        self.providers = [p for p in providers if p.has_key()]

        if not self.providers:
            raise RuntimeError("Nenhum provider configurado com chave de API.")

        logger.info(f"{len(self.providers)} provider(s) ativos")
        self.idx = 0
        self.lock = threading.Lock()

    def _next_index(self) -> int:
        with self.lock:
            i = self.idx
            self.idx = (self.idx + 1) % len(self.providers)
            return i

    def get_available_provider(self) -> Optional[AIProvider]:
        n = len(self.providers)
        start = self._next_index()

        for offset in range(n):
            i = (start + offset) % n
            p = self.providers[i]
            if p.can_use():
                logger.debug(f"[{p.name}] selecionado")
                return p

        logger.error("Nenhum provider disponível")
        return None

    # Método principal — chame este para obter uma resposta de texto
    # Tenta cada provider disponível em sequência até um responder com sucesso
    def ask(self, prompt: str, temperature: float = 0.7) -> str:
        for attempt in range(len(self.providers)):
            p = self.get_available_provider()

            if not p:
                break

            try:
                logger.debug(f"[{p.name}] tentativa {attempt+1}")
                resp = p.send(prompt, temperature)
                logger.debug(f"[{p.name}] status {resp.status_code}")

                if 200 <= resp.status_code < 300:
                    text = p.parse_response(resp)
                    p.mark_usage(1)
                    logger.info(f"[{p.name}] sucesso")
                    return text.strip()

                if resp.status_code == 429:
                    logger.warning(f"[{p.name}] rate limited (429)")
                    p.force_exhaust(ttl_seconds=int(p.window_seconds / 2))

                elif 400 <= resp.status_code < 600:
                    logger.warning(f"[{p.name}] erro HTTP {resp.status_code}")
                    p.force_exhaust(ttl_seconds=10)

            except Exception as e:
                logger.exception(f"[{p.name}] erro na request: {e}")
                p.force_exhaust(ttl_seconds=5)

        logger.critical("Todos providers falharam")
        raise RuntimeError("Todos providers falharam.")