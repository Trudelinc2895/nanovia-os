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
