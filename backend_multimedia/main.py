# main.py
"""Ponto de entrada do módulo de geração de vídeo."""

from engine.ai_core import (
    JobStatus, MediaResult, MediaRouterError, PollTimeout, JobFailed,
)
from engine.ai_router import build_manager  # seu router monta os providers
from engine import media_io


def generate(manager, prompt: str, *, temperature: float = 0.7,
             provider_name: str = None, timeout: float = 600.0,
             out_path: str = None) -> MediaResult:
    """
    Facade síncrona: ask + (poll se preciso) + save opcional.
    Vive em main.py, não no core (eixo 13).
    """
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
    return result


def main() -> None:
    raise NotImplementedError("Montar manager via ai_router e chamar generate().")


if __name__ == "__main__":
    main()