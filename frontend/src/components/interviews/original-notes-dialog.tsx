"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useState } from "react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

/** "View original" link: opens the untouched interview notes behind a piece of evidence. */
export function OriginalNotesButton({ interviewId, highlight }: { interviewId: string; highlight?: string }) {
  const [open, setOpen] = useState(false);
  const iv = useQuery({
    queryKey: ["interview", interviewId],
    queryFn: () => api.interviews.get(interviewId),
    enabled: open,
  });
  const raw = iv.data?.raw_content ?? "";
  const idx = highlight ? raw.toLowerCase().indexOf(highlight.toLowerCase()) : -1;

  return (
    <>
      <Button variant="link" size="xs" className="h-auto px-0 text-xs" onClick={() => setOpen(true)}>
        <FileText className="size-3" /> View original
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[85svh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {iv.data ? `Interview ${iv.data.participant_id}` : "Original interview"}
            </DialogTitle>
            <DialogDescription>
              {iv.data ? (
                <>
                  {[iv.data.participant_role, iv.data.company_size, iv.data.plan_tier].filter(Boolean).join(" · ")} ·{" "}
                  <Link href={`/projects/${iv.data.project_id}`} className="underline">
                    {iv.data.project_name}
                  </Link>
                </>
              ) : (
                "Loading…"
              )}
            </DialogDescription>
          </DialogHeader>
          {iv.isPending ? (
            <Skeleton className="h-40 w-full" />
          ) : iv.data ? (
            <div className="space-y-3">
              <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Original notes (exactly as imported)
              </p>
              <pre className="max-h-96 overflow-auto rounded-lg border bg-muted/30 p-3 font-mono text-xs whitespace-pre-wrap">
                {idx >= 0 ? (
                  <>
                    {raw.slice(0, idx)}
                    <mark className="rounded bg-amber-200/70 px-0.5 dark:bg-amber-700/50">
                      {raw.slice(idx, idx + (highlight?.length ?? 0))}
                    </mark>
                    {raw.slice(idx + (highlight?.length ?? 0))}
                  </>
                ) : (
                  raw
                )}
              </pre>
              <p className="text-xs text-muted-foreground">
                Validation: {iv.data.validation_status === "valid" ? "valid" : "needs fixes"} · source: {iv.data.source}
                {iv.data.source_filename ? ` (${iv.data.source_filename})` : ""}
              </p>
            </div>
          ) : (
            <p className="text-sm text-destructive">This interview could not be loaded.</p>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
