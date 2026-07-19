# AGENTS.md

## Project purpose

This repository is being evolved into a local-first AI workstation platform designed primarily for Windows.

The project must support:
- local execution
- offline-capable workflows when Ollama is installed locally
- clean modular separation
- expert-grade observability and control
- future simplified UX without rewriting the engine

## Product layers

### 1. Engine
Responsibilities:
- orchestration
- worker coordination
- tool execution
- memory services
- model runtime integration
- event streaming
- metrics and diagnostics
- backend domain logic

### 2. Studio
Responsibilities:
- expert desktop UI
- chat-first workflow
- orchestration overlay
- observability panels
- diagnostics and advanced controls
- model and tool management surfaces

### 3. Experia
Responsibilities:
- future simplified UX
- should reuse backend and shared contracts whenever practical
- should not fork core engine logic unless required

## Core stack

- Tauri
- React
- TypeScript
- TailwindCSS
- Zustand
- Framer Motion
- React Flow
- Monaco Editor
- FastAPI
- WebSocket
- Ollama GPU

## Architecture principles

- Keep strict separation between frontend, backend, and engine logic
- Prefer modular boundaries over convenience coupling
- Preserve current working behavior unless a change is required
- Prefer incremental migration over destructive restructuring
- Shared contracts must be typed and centralized
- Avoid introducing dead abstractions
- Build for maintainability and future extension

## Repository direction

Target structure:

- apps/studio
- apps/experia
- services/backend
- packages/engine
- packages/shared-types
- packages/ui
- docs

If the current structure differs, migrate gradually and safely.

## Configuration policy

- Never hardcode secrets
- Never hardcode absolute local filesystem paths
- Never hardcode machine-specific assumptions
- Prefer environment variables and centralized config access
- Provide safe defaults where reasonable
- Add examples/templates for required configuration
- Keep configuration discoverable and documented

## Security policy

- Validate inputs at boundaries
- Avoid unsafe shell execution
- Use least-privilege design when possible
- Expert features that reveal internals must be gated or toggleable
- Tool execution should be designed for future permission controls
- Avoid exposing sensitive process or system details without explicit reason
- Fail safely and return actionable diagnostics

## Reliability policy

- The desktop shell should supervise backend startup and shutdown cleanly
- Add healthchecks for backend and Ollama
- Prefer resilient reconnect behavior for streaming
- Keep logs structured and useful
- Avoid UI freezes under streaming load
- Prepare architecture for future crash recovery and worker restart strategies

## Frontend guidance

- Use strict TypeScript
- Prefer small reusable components
- Keep business logic out of presentational components
- Prefer composition over monolith components
- Keep desktop-first UX while remaining adaptable
- Main Studio layout should support:
  - top status bar
  - left nav rail
  - center chat
  - right inspector
  - bottom collapsible diagnostics area
  - orchestration overlay
  - fullscreen chat focus
  - future dockable WebView

## UI design direction

Visual style:
- black titanium
- background: #0F1115
- panels: #151821
- subtle steel-blue accent
- radius: 14px
- smooth motion around 150ms
- fonts: Inter + JetBrains Mono

Optional alternate theme:
- Neon Ops

## Backend guidance

Backend framework:
- FastAPI

Expected interfaces:
- `/ws/chat`
- metrics endpoint and/or stream
- health endpoints where appropriate

Structured stream events should support:
- token
- tool_call
- tool_result
- reasoning
- error
- done

Design expectations:
- typed payloads
- consistent event schemas
- predictable error surfaces
- configuration-driven runtime behavior
- no hardcoded model/runtime assumptions unless configurable

## Performance expectations

- streaming must remain responsive
- avoid unnecessary rerenders
- lazy-load heavy UI modules when practical
- keep diagnostics available without degrading the main interaction flow
- prepare the architecture for future multi-worker and multi-GPU support

## Working method

When asked to implement a feature:
1. inspect the current code and patterns
2. identify the minimal correct integration point
3. implement incrementally
4. preserve compatibility where possible
5. update types/contracts consistently
6. summarize changed files and next steps

## Change discipline

- Avoid rewriting unrelated code
- Avoid speculative expansion
- Prefer rollback-friendly changes
- Keep patches understandable
- If introducing a new dependency, justify it by necessity
- If changing cross-layer contracts, update all affected layers

## Validation expectations

When changing frontend:
- run typecheck if available
- run lint if available
- run build if appropriate

When changing backend:
- validate imports
- validate startup path
- verify route behavior
- verify streaming contract shape if changed

When changing shared contracts:
- update all dependents
- keep backward compatibility if practical
