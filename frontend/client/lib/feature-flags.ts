export const PRIVATE_ORCHESTRATOR_ADMIN_UI_ENABLED =
  process.env.NEXT_PUBLIC_PRIVATE_ORCHESTRATOR_ENABLED === "true";

export function isPrivateOrchestratorUiEnabled(): boolean {
  return PRIVATE_ORCHESTRATOR_ADMIN_UI_ENABLED;
}
