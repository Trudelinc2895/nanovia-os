# Canary Deployment

## Overview
Canary deployments route a small percentage of production traffic to a new version,
allowing gradual validation before full rollout.

## Deploy Canary (10% traffic)
```
kubectl apply -f infra/k8s/canary/
```

## Monitor Canary
```
kubectl logs -l track=canary -n nanovia --tail=100
```

## Check Canary Metrics
```
kubectl top pods -l track=canary -n nanovia
```

## Increase Canary Traffic Weight
```
kubectl annotate ingress nanovia-ingress-canary nginx.ingress.kubernetes.io/canary-weight=50 --overwrite -n nanovia
```

## Promote Canary to Stable
```
kubectl set image deployment/nanovia-api api=NEW_IMAGE -n nanovia
kubectl delete -f infra/k8s/canary/
```

## Rollback Canary
```
kubectl delete -f infra/k8s/canary/
```

## Notes
- Start at 10% weight and monitor for at least 30 minutes before increasing.
- Watch error rate: if 5xx rate increases, roll back immediately.
- Canary uses the same ConfigMap and Secrets as stable.
- The canary service (`nanovia-api-canary`) must exist for the ingress to route traffic to it.
