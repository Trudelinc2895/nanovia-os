export const PRO_PILOT = {
  name: "Nanovia Pro Pilot",
  deliveryWindow: "30 jours",
  priceCad: 297,
  optionalFollowUpCadMonthly: 79,
  paymentUrl:
    process.env.NEXT_PUBLIC_PRO_PILOT_PAYMENT_URL ??
    "https://buy.stripe.com/eVqaEZ2vF03j0De6bC1ZS02",
  publicEmail: "nanovia@duck.com",
} as const;

export const PRO_PILOT_EMAIL_LINK = `mailto:${PRO_PILOT.publicEmail}`;
