"use client";

import { useEffect, useRef, useState } from "react";

import { useReducedMotion } from "@/lib/motion";

const DURATION = 700;
// Strong ease-out (matches --ease-out-strong): fast start, gentle landing.
const easeOut = (t: number) => 1 - Math.pow(1 - t, 4);

/**
 * Counts up to `value` on first paint and between later values, starting from
 * wherever the previous count was if it is interrupted. Reduced motion shows the
 * value immediately. Screen readers always get the exact number.
 */
export function AnimatedNumber({ value, className }: { value: number; className?: string }) {
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(0);
  const current = useRef(0);

  useEffect(() => {
    if (reduced) return;
    const start = performance.now();
    const origin = current.current;
    let frame = requestAnimationFrame(function tick(now) {
      const t = Math.min(1, (now - start) / DURATION);
      current.current = Math.round(origin + (value - origin) * easeOut(t));
      setShown(current.current);
      if (t < 1) frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [value, reduced]);

  return (
    <span className={className} aria-label={String(value)}>
      <span aria-hidden>{reduced ? value : shown}</span>
    </span>
  );
}
