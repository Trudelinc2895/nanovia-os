"use client";

import { useEffect, type ReactNode } from "react";
import * as amplitude from "@amplitude/unified";

declare global {
  interface Window {
    __nanoviaAmplitudeInitialized?: boolean;
  }
}

export function AmplitudeProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    if (window.__nanoviaAmplitudeInitialized) return;

    window.__nanoviaAmplitudeInitialized = true;
    void amplitude.initAll("a7e982fe47554cee97aac533a6b0b9cd", {
      analytics: { autocapture: true },
      sessionReplay: { sampleRate: 1 },
    });
  }, []);

  return children;
}

export function trackAmplitudeEvent(eventName: string, eventProperties?: Record<string, unknown>) {
  if (typeof window === "undefined" || !window.__nanoviaAmplitudeInitialized) return;
  amplitude.track(eventName, eventProperties);
}
