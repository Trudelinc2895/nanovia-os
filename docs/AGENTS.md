# Agents Sandbox

Tous les agents passent par l'**orchestrator**.

## Agents disponibles

- `orchestrator`
- `billing_agent`
- `module_agent`
- `devops_agent`
- `security_agent`
- `code_agent`
- `memory_agent`
- `support_agent`
- `product_agent`

## Endpoint principal

`POST /agents/route`

Le routage:

1. choisit l'agent selon la tâche
2. vérifie le workspace et les permissions
3. bloque les actions dangereuses sans confirmation
4. écrit un audit log sandbox
