"use client";

import { STAGES } from "@/lib/progress";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** Five segments, collect -> report. Done segments are solid, the current one is tinted. */
export function StageBar({ flags, className }: { flags: boolean[]; className?: string }) {
  const current = flags.indexOf(false);
  const done = flags.filter(Boolean).length;
  return (
    <div className={cn("flex gap-1", className)} role="img" aria-label={`${done} of ${STAGES.length} stages complete`}>
      {STAGES.map((s, i) => (
        <Tooltip key={s}>
          <TooltipTrigger asChild>
            <span
              className={cn(
                "h-1.5 flex-1 rounded-full transition-colors duration-200",
                flags[i] ? "bg-primary" : i === current ? "bg-primary/25" : "bg-muted",
              )}
            />
          </TooltipTrigger>
          <TooltipContent>
            {s}: {flags[i] ? "done" : i === current ? "current step" : "not yet"}
          </TooltipContent>
        </Tooltip>
      ))}
    </div>
  );
}
