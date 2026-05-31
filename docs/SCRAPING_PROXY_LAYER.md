# Scraping proxy layer

Nanovia expose toujours `GET /scrape?url=...` sans casser le contrat existant.

## Compatibilite

- `SCRAPING_ENABLED=true` garde l'endpoint `/scrape` actif.
- `ENABLE_SCRAPE_PROXY=false` laisse l'endpoint en **mode legacy direct**.
- `ENABLE_SCRAPE_PROXY=true` active la couche scalable: cache, queue async, worker dedie, circuit breaker, rate limits et protections SSRF.

## Flow

1. Requete API
2. Correlation ID middleware
3. Auth optionnelle/obligatoire selon `SCRAPING_REQUIRE_AUTH`
4. Validation URL + allowlist + SSRF DNS/IP
5. Normalisation URL pour execution
6. Canonicalisation cache/dedupe (suppression `utm_*`, `fbclid`, `gclid`, etc.)
7. Rate limit domaine + client
8. Cache read-through + stale fallback
9. Circuit breaker domaine
10. Sync direct ou async queue
11. Worker Playwright/HTTP
12. Validation redirects + content-type + size limits
13. Cache write + logs JSON + metrics

## Architecture reelle du repo

Le repo est en **FastAPI/Python** avec Redis, worker dedie `scraper-worker`, Playwright et Prometheus.  
Il n'utilise pas BullMQ/Node pour le scraping; le compromis retenu garde l'architecture Python existante et renforce ses primitives Redis/worker au lieu d'introduire une seconde stack concurrente.

## Variables importantes

- `SCRAPING_ENABLED`
- `ENABLE_SCRAPE_PROXY`
- `SCRAPE_ALLOWED_DOMAINS`
- `SCRAPE_BLOCK_PRIVATE_IPS`
- `SCRAPE_RATE_LIMIT_DOMAIN_PER_MINUTE`
- `SCRAPE_RATE_LIMIT_CLIENT_PER_MINUTE`
- `SCRAPE_CACHE_TTL_SECONDS`
- `SCRAPE_CACHE_STALE_TTL_SECONDS`
- `SCRAPE_QUEUE_MAX_WAITING`
- `SCRAPE_QUEUE_JOB_TIMEOUT_MS`
- `SCRAPE_FALLBACK_DIRECT_ENABLED`
- `SCRAPE_PROXY_ENABLED`
- `SCRAPE_PROXY_URLS`

## Local

```bash
make scrape-dev
make scrape-health
make scrape-test
```

## Production rollout

1. Deploy avec `ENABLE_SCRAPE_PROXY=false`
2. Verifier `/scrape` legacy
3. Demarrer `redis` + `scraper-worker`
4. Activer allowlist stricte
5. Activer `ENABLE_SCRAPE_PROXY=true` en staging
6. Tester sync, async, cache, redirects, SSRF, queue saturation
7. Monitorer `/metrics`
8. Rollback immediat: `ENABLE_SCRAPE_PROXY=false`
