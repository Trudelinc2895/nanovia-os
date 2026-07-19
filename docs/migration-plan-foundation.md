# Incremental Migration Plan (Smallest Safe Path)

## Goal
Evolve the repo toward:
- `apps/studio`
- `apps/experia`
- `services/backend`
- `packages/engine`
- `packages/shared-types`
- `packages/ui`

without breaking currently working behavior.

## Phase 0 (this change): foundation only
1. Add root `AGENTS.md` policy file to lock architecture/security/reliability rules.
2. Create target folder scaffold with README placeholders (no runtime rewiring).
3. Create a shared typed contract package starter for chat stream events.
4. Document current-state audit and next-phase migration sequence.

## Phase 1 (next)
1. Introduce backend websocket `/ws/chat` contract models using shared event schema parity.
2. Add explicit health endpoints alignment (`backend`, `ollama`) and structured diagnostics payload.
3. Add config centralization map and `.env.example` normalization for new service boundaries.

## Phase 2
1. Bootstrap `apps/studio` (React + TypeScript) with modular shell layout skeleton.
2. Add Zustand store slices and WebSocket streaming adapter.
3. Keep existing `frontend/client` alive while Studio matures.

## Phase 3
1. Extract engine domain logic into `packages/engine` incrementally.
2. Introduce adapter layer in backend for tool runtime and model runtime separation.
3. Prepare supervisor lifecycle contract for Tauri host process.

## Guardrails
- No destructive folder moves until adapters and CI path updates are ready.
- No hardcoded model names, secrets, ports, or machine paths.
- Keep rollback-friendly commits per phase.
