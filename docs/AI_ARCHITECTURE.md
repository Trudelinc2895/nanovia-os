# Nanovia AI Architecture

Nanovia now has a control-plane oriented AI layer with three scopes:

1. **Master AI** for super-admin supervision.
2. **Tenant AI** isolated by `tenant_id` and `workspace_id`.
3. **Shared learning** for anonymized aggregate insights only.

Implementation lives in `backend/api/services/*ai*` and the API is exposed from `backend/api/routers/ai.py`.
