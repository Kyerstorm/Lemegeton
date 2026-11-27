from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


@dataclass(frozen=True)
class WorkerSettings:
    host: str = os.getenv("BOTASAURUS_HOST", "127.0.0.1")
    port: int = _integer("BOTASAURUS_PORT", 8765, 1, 65535)
    worker_token: str = os.getenv("BOTASAURUS_WORKER_TOKEN", "")
    max_workers: int = _integer("BOTASAURUS_MAX_WORKERS", 2, 1, 8)
    max_queue: int = _integer("BOTASAURUS_MAX_QUEUE", 32, 1, 256)
    timeout_ms: int = _integer("BOTASAURUS_TIMEOUT_MS", 20000, 1000, 60000)
    max_response_bytes: int = _integer("BOTASAURUS_MAX_RESPONSE_BYTES", 5 * 1024 * 1024, 1024, 10 * 1024 * 1024)
    max_text_chars: int = _integer("BOTASAURUS_MAX_TEXT_CHARS", 12000, 1, 40000)
    cache_ttl_seconds: int = _integer("BOTASAURUS_CACHE_TTL_SECONDS", 900, 0, 86400)
    job_ttl_seconds: int = _integer("BOTASAURUS_JOB_TTL_SECONDS", 1800, 60, 86400)
    cache_dir: Path = Path(os.getenv("BOTASAURUS_CACHE_DIR", "./data/botasaurus-cache")).expanduser()
    obscura_binary: str = os.getenv("BOTASAURUS_OBSCURA_BINARY", "obscura")
    chromium_fallback: bool = os.getenv("BOTASAURUS_CHROMIUM_FALLBACK", "true").strip().lower() not in ("0", "false", "no", "off")
    proxy_url: str = os.getenv("BOTASAURUS_PROXY_URL", "").strip()
    log_level: str = os.getenv("BOTASAURUS_LOG_LEVEL", "INFO")


SETTINGS = WorkerSettings()
