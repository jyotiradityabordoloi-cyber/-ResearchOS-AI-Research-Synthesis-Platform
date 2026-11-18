"use client";

import { type ReactNode, useSyncExternalStore } from "react";

const subscribe = () => () => {};

/** false during SSR and hydration, true afterwards. */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}

/**
 * Renders children only on the client. All app data comes from the API in the
 * browser, so this avoids hydration mismatches when parts of the page hydrate
 * at different times and one of them has already filled the shared query cache.
 */
export function ClientOnly({ children, fallback = null }: { children: ReactNode; fallback?: ReactNode }) {
  return useHydrated() ? children : fallback;
}
