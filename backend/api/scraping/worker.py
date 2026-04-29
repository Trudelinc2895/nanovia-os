from __future__ import annotations

import asyncio
import logging
import signal

from api.scraping.service import process_job
from api.scraping.store import dequeue_job
from api.config import settings

logger = logging.getLogger(__name__)


async def run_worker_forever(
    *,
    poll_timeout_seconds: int = 5,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Process scrape jobs from the queue until *stop_event* is set.

    Args:
        poll_timeout_seconds: How long to wait on BRPOP before re-checking.
        stop_event:           When set, the loop exits cleanly after the
                              current job finishes.  If None, the loop runs
                              until CancelledError.
    """
    logger.info("scrape_worker_started")
    while True:
        if stop_event is not None and stop_event.is_set():
            logger.info("scrape_worker_stop_event_received — shutting down")
            break
        try:
            job_id = await dequeue_job(timeout_seconds=poll_timeout_seconds)
            if not job_id:
                continue
            # Per-job timeout: 2× SCRAPING_TIMEOUT_SECONDS + 30 s overhead
            job_deadline = settings.SCRAPING_TIMEOUT_SECONDS * 2 + 30
            try:
                async with asyncio.timeout(job_deadline):
                    await process_job(job_id)
            except TimeoutError:
                logger.error(
                    "scrape_worker_job_timeout job_id=%s deadline=%.1fs",
                    job_id,
                    job_deadline,
                )
                # Mark job as failed
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
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("scrape_worker_iteration_failed")
            await asyncio.sleep(1)


def main() -> None:
    stop_event = asyncio.Event()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _handle_sigterm(*_):
        logger.info("SIGTERM received — signalling worker stop")
        loop.call_soon_threadsafe(stop_event.set)

    try:
        signal.signal(signal.SIGTERM, _handle_sigterm)
    except (OSError, ValueError):
        pass  # SIGTERM may not be available on Windows

    try:
        loop.run_until_complete(run_worker_forever(stop_event=stop_event))
    finally:
        loop.close()


if __name__ == "__main__":
    main()

