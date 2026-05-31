# Repository Audit — 2026-04-06

## Scope
Audit performed on the current `kt-monetization-os` repository before applying migration work for a Windows-first, local-first AI workstation direction.

## Current architecture snapshot
- Existing backend is a FastAPI service under `backend/api` with broad SaaS features (auth, billing, analytics, module routes).
- Existing frontend is a Next.js client under `frontend/client`, currently web-first rather than desktop shell/Tauri-first.
- Shared code already exists under `shared/` (`api`, `types`, `constants`, `auth`) but not yet aligned to a package-style contract boundary.
- Infra and deployment scripts are production-focused (`infra/`, Caddy, Docker, monitoring).

## Confirmed stack currently in use
- Backend: FastAPI, SQLAlchemy, Redis, Stripe, Prometheus instrumentation.
- Frontend: Next.js + TypeScript + Tailwind.
- Monorepo-style folders exist, but no unified `apps/*`, `packages/*`, `services/*` target layout yet.

## Migration risks (non-destructive focus)
1. **Route and billing coupling risk**
   - Existing backend routes are tightly coupled to current SaaS flows; large rewrites could break working behavior.
2. **Contract drift risk**
   - Shared event contracts for `/ws/chat` are not yet centralized as typed source-of-truth.
3. **Operational regression risk**
   - Existing CI/CD and infra scripts expect current paths; moving code physically too early can break deploy pipelines.
4. **Desktop transition risk**
   - Tauri shell + local supervisor behavior are not yet present; introducing process control must be explicit and secure.
5. **Configuration sprawl risk**
   - Env configuration exists but is split across areas; migration should centralize progressively.

## Recommended migration posture
- Keep current `backend/` and `frontend/` running while introducing the target architecture scaffold in parallel.
- Add shared typed contracts first (non-breaking), then adopt in backend websocket endpoint and Studio UI.
- Migrate by adapter/bridge steps before any hard moves of existing code.
