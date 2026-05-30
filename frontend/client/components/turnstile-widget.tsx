"use client";

import { useEffect, useId, useRef } from "react";
import Script from "next/script";

declare global {
  interface Window {
    turnstile?: {
      render: (
        container: HTMLElement,
        options: {
          sitekey: string;
          action?: string;
          theme?: "light" | "dark" | "auto";
          callback?: (token: string) => void;
          "expired-callback"?: () => void;
          "error-callback"?: () => void;
        },
      ) => string;
      remove: (widgetId: string) => void;
    };
  }
}

const SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "";
const SCRIPT_ID = "cloudflare-turnstile-script";

type TurnstileWidgetProps = {
  action: "login" | "register" | "contact" | "billing_checkout";
  onTokenChange: (token: string | null) => void;
  theme?: "light" | "dark" | "auto";
};

export function TurnstileWidget({
  action,
  onTokenChange,
  theme = "dark",
}: TurnstileWidgetProps) {
  const elementId = useId().replace(/:/g, "");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const widgetIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!SITE_KEY) return;

    const renderWidget = () => {
      if (!containerRef.current || !window.turnstile || widgetIdRef.current) return;
      widgetIdRef.current = window.turnstile.render(containerRef.current, {
        sitekey: SITE_KEY,
        action,
        theme,
        callback: (token) => onTokenChange(token),
        "expired-callback": () => onTokenChange(null),
        "error-callback": () => onTokenChange(null),
      });
    };

    renderWidget();
    const interval = window.setInterval(renderWidget, 250);
    return () => {
      window.clearInterval(interval);
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
        widgetIdRef.current = null;
      }
    };
  }, [action, onTokenChange, theme]);

  if (!SITE_KEY) {
    return null;
  }

  return (
    <>
      <Script
        id={SCRIPT_ID}
        src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
        strategy="afterInteractive"
      />
      <div className="space-y-2">
        <div id={elementId} ref={containerRef} />
        <p className="text-xs text-text-muted">
          Protection Cloudflare activee pour bloquer les abus automatises.
        </p>
      </div>
    </>
  );
}

export default TurnstileWidget;
