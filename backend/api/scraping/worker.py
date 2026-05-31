from __future__ import annotations

import asyncio
import logging
import signal
import time
from collections import defaultdict
from urllib.parse import urlsplit

from api.scraping.feature_flags import async_queue_enabled
from api.scraping.fetcher_browser import _browser_pool
from api.scraping.service import process_job
from api.scraping.store import dequeue_job
from api.config import settings

logger = logging.getLogger(__name__)

# ── Domain circuit breaker ────────────────────────────────────────────────────
# Tracks recent failures per domain: list of failure timestamps
_domain_failures: dict[str, list[float]] = defaultdict(list)
# Domains blocked until this timestamp
_domain_blocked_until: dict[str, float] = {}

_CB_WINDOW_SECONDS = 300      # 5-minute sliding window
_CB_FAIL_THRESHOLD = 3        # failures before blocking
_CB_BLOCK_SECONDS = 600       # block for 10 minutes


def _domain_of(job_id: str) -> str | None:
    """Extract domain from job URL if available via job state (best-effort)."""
    return None  # resolved at call site when URL is known


def _is_domain_blocked(domain: str) -> bool:
    """Return True if the domain circuit breaker is open."""
    now = time.monotonic()
    if domain in _domain_blocked_until:
        if _domain_blocked_until[domain] > now:
            return True
        del _domain_blocked_until[domain]
    return False


def _record_domain_failure(domain: str) -> None:
    """Record a job failure for the given domain; open circuit if threshold exceeded."""
    now = time.monotonic()
    # Purge entries outside the sliding window
    _domain_failures[domain] = [t for t in _domain_failures[domain] if now - t < _CB_WINDOW_SECONDS]
    _domain_failures[domain].append(now)
    if len(_domain_failures[domain]) >= _CB_FAIL_THRESHOLD:
        _domain_blocked_until[domain] = now + _CB_BLOCK_SECONDS
        logger.warning(
            "circuit_breaker_open domain=%s failures=%d block_seconds=%d",
            domain,
            len(_domain_failures[domain]),
            _CB_BLOCK_SECONDS,
        )


def _record_domain_success(domain: str) -> None:
    """Clear failure history on success (half-open recovery)."""
    _domain_failures.pop(domain, None)
    _domain_blocked_until.pop(domain, None)


async def _get_job_domain(job_id: str) -> str | None:
    """Retrieve the target URL domain from job state."""
    try:
        from api.scraping.store import get_job_state
        raw = await get_job_state(job_id)
        if raw and raw.get("url"):
            return urlsplit(raw["url"]).hostname or None
    except Exception:
        pass
    return None


async def _get_process_memory_mb() -> float:
    """Return current process RSS in MB."""
    try:
        import psutil
        import os
        proc = psutil.Process(os.getpid())
        return proc.memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0


async def run_worker_forever(
    *,
    poll_timeout_seconds: int = 5,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Process scrape jobs from the queue until *stop_event* is set."""
    logger.info("scrape_worker_started")
    _memory_baseline = await _get_process_memory_mb()

    while True:
        domain: str | None = None
        if stop_event is not None and stop_event.is_set():
            logger.info("scrape_worker_stop_event_received — shutting down")
            break
        if not async_queue_enabled():
            await asyncio.sleep(1)
            continue
        try:
            job_id = await dequeue_job(timeout_seconds=poll_timeout_seconds)
            if not job_id:
                continue

            # Resolve domain for circuit breaker
            domain = await _get_job_domain(job_id)
            if domain and _is_domain_blocked(domain):
                logger.warning(
                    "circuit_breaker_skip job_id=%s domain=%s",
                    job_id,
                    domain,
                )
                # Mark job as skipped/failed
                from api.scraping.store import get_job_state, set_job_state
                raw = await get_job_state(job_id)
                if raw:
                    await set_job_state(
                        job_id,
                        {**raw, "status": "failed", "error": "circuit_breaker_open"},
                        settings.SCRAPING_JOB_TTL_SECONDS,
                    )
                continue

            # Per-job timeout: 2× SCRAPING_TIMEOUT_SECONDS + 30 s overhead
            job_deadline = settings.SCRAPING_TIMEOUT_SECONDS * 2 + 30
            mem_before = await _get_process_memory_mb()
            try:
                async with asyncio.timeout(job_deadline):
                    await process_job(job_id)
                if domain:
                    _record_domain_success(domain)
            except TimeoutError:
                logger.error(
                    "scrape_worker_job_timeout job_id=%s deadline=%.1fs",
                    job_id,
                    job_deadline,
                )
                if domain:
                    _record_domain_failure(domain)
                from api.scraping.store import get_job_state, set_job_state
                import time as _time
                raw = await get_job_state(job_id)
                if raw:
                    await set_job_state(
                        job_id,
                        {
                            **raw,
                            "status": "failed",
                            "updated_at": str(int(_time.time())),
                            "error": "worker_timeout",
                        },
                        settings.SCRAPING_JOB_TTL_SECONDS,
                    )

            # Memory budget check: warn if job spiked > 200 MB over baseline
            mem_after = await _get_process_memory_mb()
            mem_delta = mem_after - mem_before
            if mem_delta > 200:
                logger.warning(
                    "worker_memory_spike job_id=%s delta_mb=%.1f — closing browser",
                    job_id,
                    mem_delta,
                )
                try:
                    await _browser_pool._close_browser()
                except Exception as exc:
                    logger.warning("worker_memory_spike browser_close_error: %s", exc)

        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("scrape_worker_iteration_failed")
            if domain:
                _record_domain_failure(domain)
            await asyncio.sleep(1)


def main() -> None:
    stop_event = asyncio.Event()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _handle_sigterm(*_):
        logger.info("SIGTERM received — signalling worker stop")
        loop.call_soon_threadsafe(stop_event.set)

    def _handle_sigint(*_):
        logger.info("SIGINT received — signalling worker stop")
        loop.call_soon_threadsafe(stop_event.set)

    try:
        signal.signal(signal.SIGTERM, _handle_sigterm)
    except (OSError, ValueError):
        pass  # SIGTERM may not be available on Windows

    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except (OSError, ValueError):
        pass

    try:
        loop.run_until_complete(run_worker_forever(stop_event=stop_event))
    finally:
        try:
            loop.run_until_complete(_browser_pool.shutdown())
        except Exception:
            logger.exception("scrape_worker_shutdown_cleanup_failed")
        loop.close()


if __name__ == "__main__":
    main()

