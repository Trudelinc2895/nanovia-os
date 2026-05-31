from __future__ import annotations

import time

from prometheus_client import Counter, Gauge, Histogram


SCRAPE_REQUESTS_TOTAL = Counter(
    "scrape_requests_total",
    "Total scrape requests grouped by mode and outcome.",
    ["mode", "outcome", "domain"],
)

SCRAPE_LATENCY_SECONDS = Histogram(
    "scrape_latency_seconds",
    "End-to-end scrape latency.",
    ["mode", "source", "domain"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 30, 60),
)

SCRAPE_QUEUE_DEPTH = Gauge(
    "scrape_queue_depth",
    "Current scrape queue depth.",
)

SCRAPE_CIRCUIT_OPEN_TOTAL = Counter(
    "scrape_circuit_open_total",
    "Number of times a domain circuit breaker opened.",
    ["domain"],
)

SCRAPE_RESPONSE_BYTES = Histogram(
    "scrape_response_bytes",
    "Response payload size for scrape results.",
    ["mode", "source", "domain"],
    buckets=(256, 1024, 4_096, 16_384, 65_536, 262_144, 1_048_576, 2_097_152),
)

SCRAPE_REDIRECTS_TOTAL = Counter(
    "scrape_redirects_total",
    "Number of redirects followed by scrape requests.",
    ["mode", "source", "domain"],
)

SCRAPE_CACHE_REQUESTS_TOTAL = Counter(
    "scrape_cache_requests_total",
    "Cache lookup results for scrape requests.",
    ["result"],
)

SCRAPE_RETRIES_TOTAL = Counter(
    "scrape_retries_total",
    "Number of scrape retries.",
    ["mode", "domain", "reason"],
)

SCRAPE_ERRORS_TOTAL = Counter(
    "scrape_errors_total",
    "Number of scrape request failures grouped by mode, domain, and reason.",
    ["mode", "domain", "reason"],
)

SCRAPE_WORKER_ACTIVE = Gauge(
    "scrape_worker_active",
    "Number of active scrape workers with a fresh heartbeat.",
)

SCRAPE_WORKER_STATUS = Gauge(
    "scrape_worker_status",
    "Current scrape worker status by worker ID, region, and state.",
    ["worker_id", "region", "status"],
)

SCRAPE_WORKER_LAST_SEEN_AGE_SECONDS = Gauge(
    "scrape_worker_last_seen_age_seconds",
    "Age in seconds of the latest scrape worker heartbeat.",
    ["worker_id", "region"],
)


async def sync_runtime_metrics() -> None:
    """Refresh gauges that depend on runtime state kept in Redis/local fallback."""
    from api.scraping.store import get_worker_heartbeats, queue_depth

    SCRAPE_QUEUE_DEPTH.set(await queue_depth())

    worker_heartbeats = await get_worker_heartbeats()
    SCRAPE_WORKER_ACTIVE.set(len(worker_heartbeats))
    SCRAPE_WORKER_STATUS.clear()
    SCRAPE_WORKER_LAST_SEEN_AGE_SECONDS.clear()

    now = time.time()
    for heartbeat in worker_heartbeats:
        worker_id = heartbeat.get("worker_id", "unknown")
        region = heartbeat.get("region", "unknown")
        status = heartbeat.get("status", "unknown")
        updated_at_raw = heartbeat.get("updated_at") or str(int(now))
        try:
            updated_at = float(updated_at_raw)
        except (TypeError, ValueError):
            updated_at = now

        SCRAPE_WORKER_STATUS.labels(worker_id=worker_id, region=region, status=status).set(1)
        SCRAPE_WORKER_LAST_SEEN_AGE_SECONDS.labels(worker_id=worker_id, region=region).set(
            max(0.0, now - updated_at)
        )
