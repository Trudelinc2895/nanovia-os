export const PILOT_PAYMENT_LINK_URL =
  "https://buy.stripe.com/eVqaEZ2vF03j0De6bC1ZS02";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function buildPilotPaymentLink(
  requestId: string,
  baseUrl: string = PILOT_PAYMENT_LINK_URL
): string {
  if (!UUID_PATTERN.test(requestId)) {
    throw new Error("Invalid Pilot request identifier");
  }

  const paymentUrl = new URL(baseUrl);
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
