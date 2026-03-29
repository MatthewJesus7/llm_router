import os
import time
import threading
import requests
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Dict, Any, List

logger = logging.getLogger("ai-router")

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
            self.window_start = now
            self.used_count = 0

    def can_use(self) -> bool:
        try:
            with self.lock:
                self.reset_window_if_needed()
                
                now = time.time()
                if now < self.exhausted_until:
                    return False
                
                return self.used_count < self.usage_limit
                
        except Exception:
            return False

    def mark_usage(self, count: int = 1):
        with self.lock:
            self.used_count += count
            if self.used_count >= self.usage_limit:
                self.exhausted_until = self.window_start + self.window_seconds

    def force_exhaust(self, ttl_seconds: int):
        with self.lock:
            self.exhausted_until = time.time() + ttl_seconds

    def send(self, prompt: str, temperature: float = 0.7) -> requests.Response:
        key = os.getenv(self.api_key_env)
        if not key:
            raise RuntimeError(f"API key for {self.name} not found in env {self.api_key_env}")
        headers = self.make_headers(key)
        payload = self.build_payload(prompt, temperature)
        return requests.post(self.endpoint, headers=headers, json=payload, timeout=self.timeout)

class ProviderManager:
    def __init__(self, providers: List[AIProvider]):
        self.providers = [p for p in providers if p.has_key()]
        if not self.providers:
            raise RuntimeError("Nenhum provider configurado com chave de API.")
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
                return p
        
        return None

    def ask(self, prompt: str, temperature: float = 0.7) -> str:
        for attempt in range(len(self.providers)):
            p = self.get_available_provider()
            
            if not p:
                break
                
            try:
                resp = p.send(prompt, temperature)
                
                if 200 <= resp.status_code < 300:
                    text = p.parse_response(resp)
                    p.mark_usage(1)
                    return text.strip()
                
                if resp.status_code == 429:
                    p.force_exhaust(ttl_seconds=int(p.window_seconds / 2))
                elif 400 <= resp.status_code < 600:
                    p.force_exhaust(ttl_seconds=10)
                    
            except Exception:
                p.force_exhaust(ttl_seconds=5)
        
        raise RuntimeError("Todos providers falharam.")