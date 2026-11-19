import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Wraps every case-insensitive occurrence of `terms` in <mark>. Overlapping matches
 * are merged so marks never nest. Text is otherwise rendered exactly as given:
 * the original notes are evidence and must not be altered.
 */
export function Highlight({
  text,
  terms,
  className,
  markClassName,
}: {
  text: string;
  terms: (string | null | undefined)[];
  className?: string;
  markClassName?: string;
}) {
  const ranges = findRanges(text, terms);
  if (!ranges.length) return <span className={className}>{text}</span>;
  const out: ReactNode[] = [];
  let at = 0;
  ranges.forEach(([start, end], i) => {
    if (start > at) out.push(text.slice(at, start));
    out.push(
      <mark key={i} className={cn("rounded-sm bg-amber-200/70 px-0.5 text-inherit", markClassName)}>
        {text.slice(start, end)}
      </mark>,
    );
    at = end;
  });
  if (at < text.length) out.push(text.slice(at));
  return <span className={className}>{out}</span>;
}

export function findRanges(text: string, terms: (string | null | undefined)[]): [number, number][] {
  const lower = text.toLowerCase();
  const ranges: [number, number][] = [];
  for (const raw of terms) {
    const term = raw?.trim().toLowerCase();
    if (!term || term.length < 2) continue;
    for (let i = lower.indexOf(term); i !== -1; i = lower.indexOf(term, i + term.length)) {
      ranges.push([i, i + term.length]);
    }
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push([...r]);
  }
  return merged;
}
