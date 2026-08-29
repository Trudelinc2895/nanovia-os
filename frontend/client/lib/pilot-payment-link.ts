const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function buildPilotPaymentLink(
  requestId: string,
  baseUrl: string | null | undefined
): string {
  if (!UUID_PATTERN.test(requestId)) {
    throw new Error("Invalid Pilot request identifier");
  }
  if (!baseUrl?.trim()) {
    throw new Error("Pilot payment link is not configured");
  }

  let paymentUrl: URL;
  try {
    paymentUrl = new URL(baseUrl);
  } catch {
    throw new Error("Invalid Stripe Payment Link URL");
  }
  if (
    paymentUrl.protocol !== "https:" ||
    paymentUrl.hostname !== "buy.stripe.com" ||
    paymentUrl.username ||
    paymentUrl.password ||
    paymentUrl.port
  ) {
    throw new Error("Invalid Stripe Payment Link URL");
  }

  const parameters = new URLSearchParams();
  parameters.set("client_reference_id", requestId);
  paymentUrl.search = parameters.toString();
  paymentUrl.hash = "";
  return paymentUrl.toString();
}
