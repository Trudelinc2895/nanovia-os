import assert from "node:assert/strict";
import test from "node:test";

import {
  PILOT_CONFIRMATION_MAX_ATTEMPTS,
  normalizePilotConfirmationStatus,
  shouldPollPilotConfirmation,
} from "../lib/pilot-confirmation.ts";


test("normalizes verified public confirmation states", () => {
  assert.equal(normalizePilotConfirmationStatus("confirmed"), "confirmed");
  assert.equal(normalizePilotConfirmationStatus("processing"), "processing");
  assert.equal(normalizePilotConfirmationStatus("manual_review"), "manual_review");
  assert.equal(normalizePilotConfirmationStatus("forged"), "manual_review");
});


test("polls only a pending confirmation and stops at the bound", () => {
  assert.equal(shouldPollPilotConfirmation("processing", 1), true);
  assert.equal(
    shouldPollPilotConfirmation(
      "processing",
      PILOT_CONFIRMATION_MAX_ATTEMPTS - 1
    ),
    true
  );
  assert.equal(
    shouldPollPilotConfirmation("processing", PILOT_CONFIRMATION_MAX_ATTEMPTS),
    false
  );
  assert.equal(shouldPollPilotConfirmation("confirmed", 1), false);
  assert.equal(shouldPollPilotConfirmation("manual_review", 1), false);
});
