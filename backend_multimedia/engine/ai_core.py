# ai_core.py
# ─────────────────────────────────────────────────────────────
# Motor do roteador MULTIMÍDIA (imagem | vídeo | áudio)
#
# Estrutura herdada do core de texto:
#   • AIProvider (dados + transporte HTTP)
#   • ProviderManager (rate limit, rotação, _execute, ask)
#   • _classify_http_error / _classify_exception
#   • force_exhaust / can_use / mark_usage / reset_window_if_needed
#
# Adicionado porque a doc de multimídia exige:
#   • estado de job (pendente/running/succeeded/failed)
#   • polling com deadline e backoff
#   • webhook (correlação por job_id)
# ─────────────────────────────────────────────────────────────

import os
import time
import threading
import requests
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Dict, Any, List, Tuple, Union

logger = logging.getLogger("ai-router")


# ─────────────────────────────────────────────────────────────
# Classificação de falhas — idêntica ao core de texto
# ─────────────────────────────────────────────────────────────

def _classify_http_error(status: int, body: str) -> str:
    if status == 400:
        return f"BAD_REQUEST (400) — payload rejeitado pelo provider: {body[:300]}"
    if status == 401:
        return f"UNAUTHORIZED (401) — chave de API inválida ou expirada"
    if status == 403:
        return f"FORBIDDEN (403) — sem permissão para este modelo/endpoint"
    if status == 404:
        return f"NOT_FOUND (404) — endpoint ou modelo não existe: {body[:200]}"
    if status == 422:
        return f"UNPROCESSABLE (422) — parâmetros inválidos: {body[:300]}"
    if status == 429:
        return f"RATE_LIMIT (429) — provider retornou 429 (quota externa esgotada): {body[:200]}"
    if status == 500:
        return f"SERVER_ERROR (500) — erro interno do provider (problema do lado deles): {body[:200]}"
    if status == 502:
        return f"BAD_GATEWAY (502) — gateway do provider com problema: {body[:200]}"
    if status == 503:
        return f"SERVICE_UNAVAILABLE (503) — provider fora do ar ou sobrecarregado: {body[:200]}"
    if status == 529:
        return f"OVERLOADED (529) — provider com alta demanda (código não-padrão): {body[:200]}"
    return f"HTTP_{status}: {body[:300]}"


def _classify_exception(exc: Exception) -> str:
    name = type(exc).__name__
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return f"CONNECT_TIMEOUT — não conseguiu conectar ao provider dentro do limite"
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return f"READ_TIMEOUT — provider conectou mas não respondeu a tempo"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return f"CONNECTION_ERROR — falha de rede ao alcançar o provider: {exc}"
    if isinstance(exc, requests.exceptions.Timeout):
        return f"TIMEOUT — timeout genérico: {exc}"
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return f"PARSE_ERROR ({name}) — bug no parser ou estrutura inesperada na resposta: {exc}"
    return f"UNEXPECTED ({name}): {exc}"


# ─────────────────────────────────────────────────────────────
# Estado de job (a doc exige gerenciamento de estado)
# ─────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


@dataclass
class MediaResult:
    """Resultado de um job multimídia: URL ou bytes + mime.
    (Eixo 14: download/save saíram do core — ver media_io.py)"""
    url: Optional[str] = None
    data: Optional[bytes] = None
    mime_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaJob:
    job_id: str
    provider_name: str
    submitted_at: float = field(default_factory=time.time)
    status: JobStatus = JobStatus.PENDING
    result: Optional[MediaResult] = None
    error: Optional[str] = None

    @property
    def terminal(self) -> bool:
        return self.status.terminal

    @property
    def elapsed(self) -> float:
        return time.time() - self.submitted_at


# ─────────────────────────────────────────────────────────────
# Exceções do roteador (eixo 17: distinguir falha de job
# de falha de transporte)
# ─────────────────────────────────────────────────────────────

class MediaRouterError(Exception):
    """Base para erros do roteador multimídia."""


class JobFailed(MediaRouterError):
    """O provider reportou o job como FAILED/CANCELLED (não é falha de rede)."""
    def __init__(self, job: MediaJob):
        self.job = job
        super().__init__(
            f"Job {job.job_id} ({job.provider_name}) terminou como "
            f"{job.status.value}: {job.error}"
        )


class PollTimeout(MediaRouterError):
    """O polling esgotou o tempo sem chegar a estado terminal."""
    def __init__(self, job: MediaJob, timeout: float):
        self.job = job
        self.timeout = timeout
        super().__init__(
            f"Polling do job {job.job_id} ({job.provider_name}) excedeu {timeout}s"
        )


# ─────────────────────────────────────────────────────────────
# Provider multimídia
# ─────────────────────────────────────────────────────────────

SubmitParser = Callable[[requests.Response], Union[str, Tuple[str, Optional[MediaResult]]]]
StatusParser = Callable[[requests.Response], Tuple[JobStatus, Optional[MediaResult], Optional[str]]]
WebhookParser = Callable[[Dict[str, Any]], Tuple[JobStatus, Optional[MediaResult], Optional[str]]]


@dataclass
class AIProvider:
    name: str
    api_key_env: str
    endpoint: str
    make_headers: Callable[[str], Dict[str, str]]
    build_payload: Callable[[str, float], Dict[str, Any]]
    parse_submit: SubmitParser

    # ── polling (fluxo 2) ──────────────────────────────────
    build_status_url: Optional[Callable[[str], str]] = None
    parse_status: Optional[StatusParser] = None
    poll_interval: float = 2.0
    # Eixo 18: max_poll_timeout saiu daqui — agora é por job.
    max_consecutive_poll_errors: int = 5

    # ── webhook (fluxo 3) ──────────────────────────────────
    supports_webhook: bool = False
    parse_webhook: Optional[WebhookParser] = None

    # ── rate limit interno (idêntico ao core de texto) ─────
    usage_limit: int = 100
    window_seconds: int = 60
    used_count: int = 0
    window_start: float = field(default_factory=lambda: time.time())
    exhausted_until: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    # ── modelo / timeout HTTP ──────────────────────────────
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
        return requests.post(self.endpoint, headers=headers, json=payload, timeout=self.timeout)

    def check_status(self, job_id: str) -> requests.Response:
        key = os.getenv(self.api_key_env)
        if not key:
            raise RuntimeError(f"API key for {self.name} not found")
        if not self.build_status_url:
            raise RuntimeError(f"Provider {self.name} não suporta polling")
        headers = self.make_headers(key)
        url = self.build_status_url(job_id)
        logger.debug(f"[{self.name}] status check → {job_id}")
        return requests.get(url, headers=headers, timeout=self.timeout)


# ─────────────────────────────────────────────────────────────
# JobStore (eixo 15: registry extraído do Manager)
# ─────────────────────────────────────────────────────────────

class JobStore:
    """Estado de jobs em memória. Injetável; o Manager não guarda estado de job."""

    def __init__(self):
        self._jobs: Dict[str, MediaJob] = {}
        self._lock = threading.Lock()

    def put(self, job: MediaJob):
        if not job.job_id:
            return
        with self._lock:
            self._jobs[job.job_id] = job

    def get(self, job_id: str) -> Optional[MediaJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def require(self, job_id: str) -> MediaJob:
        job = self.get(job_id)
        if not job:
            raise MediaRouterError(f"Job '{job_id}' não encontrado no JobStore")
        return job


class ProviderManager:
    def __init__(self, providers: List[AIProvider],
                 job_store: Optional[JobStore] = None):
        self.providers = [p for p in providers if p.has_key()]

        if not self.providers:
            raise RuntimeError("Nenhum provider configurado com chave de API.")

        logger.info(f"{len(self.providers)} provider(s) ativos")

        self.providers_map = {p.name.lower(): p for p in self.providers}
        self.idx = 0
        self.lock = threading.Lock()

        # Eixo 15: registry fora do Manager (injetável, default em memória)
        self.jobs = job_store if job_store is not None else JobStore()

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

    def get_job(self, job_id: str) -> Optional[MediaJob]:
        return self.jobs.get(job_id)

    def _execute(self, p: AIProvider, prompt: str, temperature: float) -> Optional[MediaJob]:
        try:
            resp = p.send(prompt, temperature)
            status = resp.status_code

            if 200 <= status < 300:
                try:
                    raw = p.parse_submit(resp)
                    if isinstance(raw, tuple):
                        job_id, immediate = raw
                    else:
                        job_id, immediate = raw, None

                    if not job_id and not immediate:
                        logger.error(
                            f"[{p.name}] PARSE_EMPTY — submit sem job_id. "
                            f"Body (500 chars): {resp.text[:500]}"
                        )
                        p.force_exhaust(ttl_seconds=4)
                        return None

                    p.mark_usage(1)
                    job = MediaJob(
                        job_id=job_id or "",
                        provider_name=p.name,
                        status=JobStatus.SUCCEEDED if immediate else JobStatus.PENDING,
                        result=immediate,
                    )
                    self.jobs.put(job)
                    return job

                except Exception as parse_exc:
                    logger.error(
                        f"[{p.name}] PARSE_ERROR — {_classify_exception(parse_exc)}. "
                        f"Body (500 chars): {resp.text[:500]}"
                    )
                    p.force_exhaust(ttl_seconds=4)
                    return None

            body = resp.text
            diagnosis = _classify_http_error(status, body)

            if status == 429:
                cooldown = int(p.window_seconds / 2)
                logger.error(f"[{p.name}] API_SIDE | {diagnosis} → cooldown {cooldown}s")
                p.force_exhaust(ttl_seconds=cooldown)
            elif status in (500, 502, 503, 529):
                logger.error(
                    f"[{p.name}] API_SIDE | {diagnosis} "
                    f"→ provável problema de infraestrutura do provider, cooldown 30s"
                )
                p.force_exhaust(ttl_seconds=30)
            elif status in (400, 422):
                logger.error(f"[{p.name}] CODE_SIDE | {diagnosis}")
                p.force_exhaust(ttl_seconds=4)
            elif status in (401, 403):
                logger.error(f"[{p.name}] CODE_SIDE | {diagnosis} → cooldown 300s")
                p.force_exhaust(ttl_seconds=300)
            else:
                logger.error(f"[{p.name}] UNKNOWN | {diagnosis} → cooldown 4s")
                p.force_exhaust(ttl_seconds=4)

        except Exception as exc:
            diagnosis = _classify_exception(exc)
            is_timeout = isinstance(exc, requests.exceptions.Timeout)
            cooldown = 10 if is_timeout else 5
            logger.error(f"[{p.name}] NETWORK | {diagnosis} → cooldown {cooldown}s")
            p.force_exhaust(ttl_seconds=cooldown)

        return None

    def poll(self, job: MediaJob, timeout: Optional[float] = None) -> MediaResult:
        """
        Acompanha o job até estado terminal.

        Eixo 17: levanta JobFailed em FAILED/CANCELLED e PollTimeout no
        deadline, em vez de devolver None (que se confundia com falha de rede).

        Eixo 18: timeout por job — default derivado do próprio job
        (job.max_poll_timeout se existir, senão 600s).
        """
        if job.terminal:
            if job.status == JobStatus.SUCCEEDED and job.result is not None:
                return job.result
            raise JobFailed(job)

        p = self.providers_map.get(job.provider_name.lower())
        if not p or not p.build_status_url or not p.parse_status:
            raise MediaRouterError(f"Provider '{job.provider_name}' não suporta polling")

        # Eixo 18: deadline por job, não por provider.
        effective_timeout = timeout if timeout is not None else getattr(
            job, "max_poll_timeout", 600.0
        )
        deadline = time.time() + effective_timeout
        interval = p.poll_interval
        consecutive_errors = 0

        while time.time() < deadline:
            time.sleep(interval)

            try:
                resp = p.check_status(job.job_id)
                status = resp.status_code

                if 200 <= status < 300:
                    consecutive_errors = 0
                    try:
                        new_status, result, error = p.parse_status(resp)
                    except Exception as parse_exc:
                        logger.error(
                            f"[{p.name}] PARSE_ERROR poll — {_classify_exception(parse_exc)}. "
                            f"Body (500 chars): {resp.text[:500]}"
                        )
                        p.force_exhaust(ttl_seconds=4)
                        raise MediaRouterError(
                            f"Parser de status falhou para job {job.job_id}"
                        ) from parse_exc

                    job.status = new_status
                    job.result = result
                    job.error = error

                    if job.terminal:
                        if new_status == JobStatus.SUCCEEDED and result is not None:
                            return result
                        # Eixo 17: falha de job ≠ falha de transporte.
                        raise JobFailed(job)

                elif status == 429:
                    p.force_exhaust(int(p.window_seconds / 2))
                    interval = min(interval * 2, 30)
                    logger.warning(f"[{p.name}] poll 429 → backoff {interval}s")

                elif status in (500, 502, 503, 529):
                    p.force_exhaust(30)
                    consecutive_errors += 1
                    logger.warning(
                        f"[{p.name}] poll 5xx ({consecutive_errors}/{p.max_consecutive_poll_errors})"
                    )
                    if consecutive_errors >= p.max_consecutive_poll_errors:
                        p.force_exhaust(30)
                        raise MediaRouterError(
                            f"Polling abortado: {consecutive_errors} erros 5xx consecutivos"
                        )

                elif status in (401, 403):
                    logger.error(f"[{p.name}] poll auth error {status} — abortando")
                    p.force_exhaust(300)
                    raise MediaRouterError(
                        f"Polling abortado: auth error {status} no provider {p.name}"
                    )

                else:
                    logger.error(f"[{p.name}] poll HTTP_{status} — abortando")
                    raise MediaRouterError(
                        f"Polling abortado: HTTP_{status} no provider {p.name}"
                    )

            except MediaRouterError:
                raise
            except Exception as exc:
                consecutive_errors += 1
                diagnosis = _classify_exception(exc)
                logger.warning(
                    f"[{p.name}] poll NETWORK ({consecutive_errors}/"
                    f"{p.max_consecutive_poll_errors}) — {diagnosis}"
                )
                if consecutive_errors >= p.max_consecutive_poll_errors:
                    p.force_exhaust(30)
                    raise MediaRouterError(
                        f"Polling abortado: {consecutive_errors} erros de rede consecutivos"
                    ) from exc
                interval = min(interval * 1.5, 30)

        # Eixo 17/18: timeout explícito, não None.
        raise PollTimeout(job, effective_timeout)

    def handle_webhook(self, provider_name: str, payload: Dict[str, Any]) -> MediaJob:
        """
        Recebe o payload de webhook do provider e atualiza o estado do job.

        Eixo 16: não cria mais job stub. Se o job_id não for conhecido,
        levanta MediaRouterError — indica bug de correlação e deve ser
        tratado pelo chamador (ex.: registrar o job antes de aceitar
        o webhook, ou enfileirar o payload).
        """
        p = self.providers_map.get(provider_name.strip().lower())
        if not p:
            raise ValueError(f"Provider '{provider_name}' não encontrado")
        if not p.supports_webhook or not p.parse_webhook:
            raise RuntimeError(f"Provider '{p.name}' não suporta webhook")

        status, result, error = p.parse_webhook(payload)

        job_id = (
            payload.get("job_id")
            or payload.get("id")
            or (payload.get("data") or {}).get("id")
            or ""
        )
        if not job_id:
            raise MediaRouterError(
                f"Webhook do provider '{p.name}' sem job_id — payload inválido"
            )

        job = self.jobs.get(job_id)
        if not job:
            # Eixo 16: falha explícita em vez de stub silencioso.
            raise MediaRouterError(
                f"Webhook do provider '{p.name}' para job desconhecido '{job_id}' "
                f"— registre o job antes de aceitar o webhook"
            )

        job.status = status
        job.result = result
        job.error = error
        self.jobs.put(job)

        logger.info(f"[{p.name}] webhook: job {job_id} → {status.value}")
        return job

    def ask(self, prompt: str, temperature: float = 0.7,
            provider_name: str = None) -> MediaJob:
        """Submete o prompt e retorna o MediaJob.
        Pode já vir SUCCEEDED (provider síncrono) ou PENDING (assíncrono)."""
        if provider_name:
            p = self.providers_map.get(provider_name.strip().lower())
            if not p:
                raise ValueError(f"Provider '{provider_name}' não encontrado")
            if not p.can_use():
                raise RuntimeError(f"Provider '{p.name}' indisponível (rate limit/cooldown)")

            job = self._execute(p, prompt, temperature)
            if job:
                return job
            raise RuntimeError(f"Provider '{p.name}' falhou na execução")

        for attempt in range(len(self.providers)):
            p = self.get_available_provider()
            if not p:
                break
            job = self._execute(p, prompt, temperature)
            if job:
                logger.info(f"[{p.name}] sucesso")
                return job

        logger.critical("Todos providers falharam")
        raise RuntimeError("Todos providers falharam.")

    def available_providers(self) -> List[str]:
        return list(self.providers_map.keys())