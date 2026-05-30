# Blue/Green Deployment Cutover

## Overview
Blue-green deployment allows zero-downtime cutover between versions.
Both `blue` and `green` deployments run the same image tag until a cutover is initiated.
The main `nanovia-api` service selector is patched to point at the active version.

## Cutover from Blue to Green

1. Deploy new version to green:
   ```
   kubectl set image deployment/nanovia-api-green api=ghcr.io/trudelinc2895/nanovia-os/api:NEW_TAG -n nanovia
   ```

2. Wait for rollout:
   ```
   kubectl rollout status deployment/nanovia-api-green -n nanovia
   ```

3. Run smoke tests against green:
   ```
   curl https://api.nanovia.ca/health  # after temporarily routing
   ```

4. Switch the main service to green:
   ```
   kubectl patch service nanovia-api -n nanovia -p '{"spec":{"selector":{"version":"green"}}}'
   ```

5. Verify:
   ```
   kubectl get endpoints nanovia-api -n nanovia
   ```

6. Keep blue running for 15 minutes as rollback option.

7. Rollback if needed:
   ```
   kubectl patch service nanovia-api -n nanovia -p '{"spec":{"selector":{"version":"blue"}}}'
   ```

## Cutover from Green to Blue
Reverse the steps above, using `blue` as the target.

## Notes
- Ensure the new image is fully tested in staging before cutting over.
- Monitor error rate and latency for at least 15 minutes after cutover.
- Keep old deployment scaled down (not deleted) for 24 hours to allow quick rollback.

