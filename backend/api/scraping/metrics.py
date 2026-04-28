from __future__ import annotations

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
