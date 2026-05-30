import path from "path";
import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";
const PUBLIC_API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
const DEFAULT_BACKEND_URL = isDev ? "http://127.0.0.1:8010" : "http://api:8010";
const BACKEND_URL = (process.env.BACKEND_INTERNAL_URL ?? process.env.API_BASE_URL ?? DEFAULT_BACKEND_URL).replace(/\/$/, "");

const connectSrc = [
  "'self'",
  "https://api.stripe.com",
  "https://r.stripe.com",
  "https://challenges.cloudflare.com",
  ...(isDev ? ["http://localhost:*", "http://127.0.0.1:*"] : []),
  ...(PUBLIC_API_URL ? [PUBLIC_API_URL] : []),
].join(" ");

const scriptSrc = [
  "'self'",
  "'unsafe-inline'",
  "https://challenges.cloudflare.com",
  ...(isDev ? ["'unsafe-eval'"] : []),
].join(" ");

const securityHeaders = [
  { key: "X-DNS-Prefetch-Control", value: "on" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-XSS-Protection", value: "1; mode=block" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
  { key: "Origin-Agent-Cluster", value: "?1" },
  { key: "X-Permitted-Cross-Domain-Policies", value: "none" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      `script-src ${scriptSrc}`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https:",
      "font-src 'self' data:",
      `connect-src ${connectSrc}`,
      "frame-src https://challenges.cloudflare.com https://js.stripe.com https://hooks.stripe.com",
      "form-action 'self' https://checkout.stripe.com",
      "frame-ancestors 'none'",
      "object-src 'none'",
      "base-uri 'self'",
      ...(isDev ? [] : ["upgrade-insecure-requests"]),
    ].join("; "),
  },
  ...(isDev ? [] : [
    { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  ]),
];

const nextConfig: NextConfig = {
  // output: "standalone", // enable for Docker deploy
  outputFileTracingRoot: path.join(__dirname, "..", "..", ".."),
  async rewrites() {
    // Proxy /api/v1/* to FastAPI backend (dev + prod when no reverse proxy)
    return [
      {
        source: "/api/v1/:path*",
        destination: `${BACKEND_URL}/api/v1/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
