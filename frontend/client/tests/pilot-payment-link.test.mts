import assert from "node:assert/strict";
import test from "node:test";

import { buildPilotPaymentLink } from "../lib/pilot-payment-link.ts";


const REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000";
const CONFIGURED_PAYMENT_LINK = "https://buy.stripe.com/test_configured";


test("builds a Stripe Payment Link with only client_reference_id", () => {
  const paymentLink = buildPilotPaymentLink(
    REQUEST_ID,
    `${CONFIGURED_PAYMENT_LINK}?email=client%40example.com&name=Client#message`
  );
  const parsed = new URL(paymentLink);

  assert.equal(parsed.protocol, "https:");
  assert.equal(parsed.hostname, "buy.stripe.com");
  assert.equal(parsed.hash, "");
  assert.deepEqual([...parsed.searchParams.keys()], ["client_reference_id"]);
  assert.equal(parsed.searchParams.get("client_reference_id"), REQUEST_ID);
  assert.equal(parsed.searchParams.has("email"), false);
  assert.equal(parsed.searchParams.has("name"), false);
  assert.equal(parsed.searchParams.has("message"), false);
  assert.equal(paymentLink.includes("client%40example.com"), false);
});


test("rejects unsafe or non-Stripe base URLs", () => {
  const invalidUrls = [
    "http://buy.stripe.com/test",
    "https://buy.stripe.com.evil.example/test",
    "https://user:password@buy.stripe.com/test",
    "https://buy.stripe.com:444/test",
  ];

  for (const invalidUrl of invalidUrls) {
    assert.throws(
      () => buildPilotPaymentLink(REQUEST_ID, invalidUrl),
      /Invalid Stripe Payment Link URL/
    );
  }
});


test("rejects a non-UUID request identifier", () => {
  assert.throws(
    () => buildPilotPaymentLink("client@example.com", CONFIGURED_PAYMENT_LINK),
    /Invalid Pilot request identifier/
  );
});


test("fails closed when the Payment Link is not configured", () => {
  for (const missingUrl of [undefined, null, ""]) {
    assert.throws(
      () => buildPilotPaymentLink(REQUEST_ID, missingUrl),
      /Pilot payment link is not configured/
    );
  }
});


test("uses a rotated configured Payment Link without a fallback", () => {
  const rotatedUrl = "https://buy.stripe.com/test_rotated";
  const paymentLink = buildPilotPaymentLink(REQUEST_ID, rotatedUrl);

  assert.equal(new URL(paymentLink).pathname, "/test_rotated");
});
