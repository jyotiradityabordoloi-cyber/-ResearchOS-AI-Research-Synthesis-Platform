"use client";

import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void) {
  const mql = window.matchMedia(QUERY);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

/** True when the user asked the OS for less motion. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => false,
  );
}

/**
 * Chart animation props: short and decisive by default (Recharts' default is a
 * 1.5s ease that makes dashboards feel slow), none at all for reduced motion.
 */
export function useChartAnimation() {
  const reduced = useReducedMotion();
  return { isAnimationActive: !reduced, animationDuration: 450, animationEasing: "ease-out" as const };
}
