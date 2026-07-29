import type { PilotConfirmationStatus } from "./api";

export const PILOT_CONFIRMATION_POLL_INTERVAL_MS = 3000;
export const PILOT_CONFIRMATION_MAX_ATTEMPTS = 20;

const PUBLIC_STATES = new Set<PilotConfirmationStatus>([
  "confirmed",
  "processing",
  "manual_review",
]);

export function normalizePilotConfirmationStatus(
  value: string
): PilotConfirmationStatus {
  return PUBLIC_STATES.has(value as PilotConfirmationStatus)
    ? (value as PilotConfirmationStatus)
    : "manual_review";
}

export function shouldPollPilotConfirmation(
  status: PilotConfirmationStatus,
  completedAttempts: number
): boolean {
  return (
    status === "processing" &&
    completedAttempts < PILOT_CONFIRMATION_MAX_ATTEMPTS
  );
}
