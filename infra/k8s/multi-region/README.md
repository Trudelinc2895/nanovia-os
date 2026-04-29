# Multi-Region Strategy

## Overview
Nanovia OS is deployed across two regions for high availability and low latency.

| Region      | Role      | Endpoint              |
|-------------|-----------|----------------------|
| eu-west-1   | Primary   | api.nanovia.ca       |
| us-east-1   | Secondary | api-us.nanovia.ca    |

## Routing Strategy
- **Latency-based DNS routing** (e.g., AWS Route 53 or Cloudflare Load Balancing).
- Traffic is directed to the region with the lowest latency for the client.
- DNS TTL: 60 seconds to allow fast failover.

## Failover
- **Automatic failover** triggered when:
  - Error rate exceeds 10% for 2 consecutive health checks.
  - P99 latency exceeds 2000ms.
- Cooldown period: 300 seconds before switching back.
- Health checks run every 10 seconds on `/health`.

## Deploying to Multiple Regions
Each region runs its own Kubernetes cluster with the same manifests.
Use region-specific `values.yaml` overrides to set region-specific config (e.g., `APP_REGION`).

### Apply to eu-west-1
```
kubectl apply -k infra/k8s/overlays/production/ --context=k8s-eu-west-1
```

### Apply to us-east-1
```
kubectl apply -k infra/k8s/overlays/production/ --context=k8s-us-east-1
```

## Database Replication
- PostgreSQL primary runs in eu-west-1.
- us-east-1 uses a read replica (configure `DATABASE_URL` per region via secrets).
- Write operations always target the primary region.

## Observability
- Each region has its own Prometheus + Grafana stack.
- A global Grafana instance aggregates metrics from all regions using remote_read.
