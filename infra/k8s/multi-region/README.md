# Multi-Region Strategy

## Objective
Prepare clean multi-region routing for `nanovia-os` without introducing unnecessary operational complexity.

## Recommended topology

| Region | Role | Public API endpoint | Routing weight | Notes |
| --- | --- | --- | --- | --- |
| `eu-west-1` | Primary | `api.nanovia.ca` | 100 | Default write region and operational home |
| `us-east-1` | Fallback | `api-us.nanovia.ca` | 0 during normal ops | Warm standby / failover target |

## Routing strategy
- Use **GeoDNS / latency-based edge routing** only for **healthy regions**.
- Keep a single **primary write region** to avoid cross-region write coordination complexity.
- Keep the fallback region **warm** and able to accept traffic within DNS failover TTL.
- Recommended DNS/edge choices:
  - **Cloudflare Load Balancer** with geo steering + health checks, or
  - **Route 53 latency-based routing** with health checks.
- Recommended DNS TTL: **60 seconds**.

## Primary / fallback behavior
- **Normal mode:** traffic resolves to the primary region for write paths; read-friendly public traffic may be steered by latency if the secondary is healthy.
- **Failover mode:** edge routing removes the failing region from the pool and sends traffic to the fallback region.
- **Failback mode:** restore primary only after health remains stable through the cooldown window; avoid flapping.

## Blast-radius isolation
- Each region should run its **own Kubernetes cluster**, ingress, worker pool, and monitoring stack.
- Do **not** share regional runtime dependencies that would make both regions fail together.
- Keep these components **regional**:
  - API pods
  - scraper workers
  - Redis cache / scrape queue
  - Prometheus / Grafana agents
- Use independent region-specific secrets/config where applicable (`APP_REGION`, ingress hostnames, DB endpoints, alert routes).

## Redis / cache strategy
- Prefer **regional Redis** per cluster for scrape queue and cache.
- Do **not** make cross-region worker execution depend on a single Redis instance in one region.
- Keep scrape queue processing local to each region to avoid latency and regional blast radius.
- If replication is needed later, use it only for **best-effort cache warmup**, not as a hard runtime dependency.

## Database strategy
- Keep **one primary write region** for PostgreSQL.
- Secondary region should use:
  - a **read replica** for read-only or degraded operations, or
  - controlled failover procedures for database promotion during a true regional outage.
- The application should not assume both regions can safely perform concurrent writes without database failover.

## Cross-region timeout guidance
- Keep HTTP/service timeouts stricter for cross-region fallbacks than for in-region traffic.
- Recommended starting points:
  - edge / health check timeout: **2-5s**
  - app-to-app cross-region timeout: **3-5s**
  - scraper job timeout remains local to the worker region; avoid cross-region scraping dependencies
- Fail fast rather than building deep retry chains across regions.

## Operational failover policy
- Trigger automatic failover when one or more are sustained:
  - error rate > **10%** for two consecutive checks
  - p99 latency > **2000ms**
  - readiness endpoint unavailable
- Cooldown before failback: **300s**
- Health checks should probe `/api/v1/health/ready`.

## Phase 6 conceptual failover test
Use staging or a controlled drill before production rollout:

1. Confirm primary receives normal traffic.
2. Simulate primary outage by disabling the primary origin or ingress.
3. Verify DNS / edge routing removes the unhealthy region.
4. Confirm fallback region serves `GET /api/v1/health/ready`.
5. Confirm API stays stable and worker pods in fallback region continue processing local queue traffic.
6. Confirm Redis / cache dependency is regional, not hard-pinned to the failed region.
7. Restore primary, wait through cooldown, then reintroduce it.

## What is intentionally out of scope for now
- active/active multi-region writes
- global Redis quorum
- cross-region scrape queue sharing
- complex service mesh routing

This phase keeps the design pragmatic: **primary + warm fallback**, regional isolation, and documented failover.

