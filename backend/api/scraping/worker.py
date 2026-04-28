from __future__ import annotations

import asyncio
import logging

from api.scraping.service import process_job
from api.scraping.store import dequeue_job

logger = logging.getLogger(__name__)


async def run_worker_forever(*, poll_timeout_seconds: int = 5) -> None:
    logger.info("scrape_worker_started")
    while True:
        try:
            job_id = await dequeue_job(timeout_seconds=poll_timeout_seconds)
            if not job_id:
                continue
            await process_job(job_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("scrape_worker_iteration_failed")
            await asyncio.sleep(1)


def main() -> None:
    asyncio.run(run_worker_forever())


if __name__ == "__main__":
    main()
