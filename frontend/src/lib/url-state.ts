"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useState, useSyncExternalStore } from "react";

const EVENT = "researchos:urlstate";

/**
 * A string filter that is seeded from, and mirrored to, the URL query string so
 * dashboard links like `/insights?status=proposed` open a pre-filtered view and the
 * filtered view can be shared or reloaded.
 *
 * Seeds from `useSearchParams()` rather than `window.location`: on a client-side
 * navigation the new page renders before the browser URL changes. Pages render
 * inside <ClientOnly>, so this never runs during prerendering.
 *
 * Updates use `history.replaceState` (no navigation, no re-render of the page) and
 * announce the change so components outside the page, like the copilot, can follow.
 */
export function useUrlState(key: string, fallback: string): [string, (value: string) => void] {
  const params = useSearchParams();
  const [value, setValue] = useState(() => params.get(key) ?? fallback);
  const update = useCallback(
    (next: string) => {
      setValue(next);
      const url = new URL(window.location.href);
      if (next === fallback || next === "") url.searchParams.delete(key);
      else url.searchParams.set(key, next);
      window.history.replaceState(window.history.state, "", url);
      window.dispatchEvent(new Event(EVENT));
    },
    [key, fallback],
  );
  return [value, update];
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("popstate", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("popstate", onChange);
  };
}

/**
 * The current query string, including changes made by `useUrlState`. Also re-reads on
 * router navigations, because `useSearchParams()` re-renders the caller.
 */
export function useLiveSearchParams(): URLSearchParams {
  useSearchParams();
  const search = useSyncExternalStore(
    subscribe,
    () => window.location.search,
    () => "",
  );
  return new URLSearchParams(search);
}
