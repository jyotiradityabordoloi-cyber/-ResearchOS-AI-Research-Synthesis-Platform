"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, RotateCcw, ShieldAlert, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import type { Decision, ReviewPayload } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export const TAG_LABEL: Record<string, string> = {
  pricing: "pricing",
  churn: "churn",
  competitive_switching: "competitive switching",
};

/** Refresh everything a review action can change. */
export function useReviewRefresh(projectId: string) {
  const qc = useQueryClient();
  return () => {
    for (const key of [
      ["themes", projectId],
      ["insights", projectId],
      ["all-insights"],
      ["project", projectId],
      ["projects"],
      ["audit", projectId],
      ["dashboard"],
    ])
      qc.invalidateQueries({ queryKey: key });
  };
}

export function StatusBadge({ status }: { status: string }) {
  if (status === "approved")
    return (
      <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
        <Check /> Approved
      </Badge>
    );
  if (status === "rejected") return <Badge variant="destructive">Rejected</Badge>;
  return <Badge variant="outline">Awaiting review</Badge>;
}

/**
 * Approve / reject / reopen. Approving a sensitive finding (pricing, churn,
 * competitive switching) requires an explicit acknowledgement and a reason.
 */
export function DecisionButtons({
  status,
  sensitiveTags,
  requiresApproval,
  onDecide,
  size = "sm",
}: {
  status: string;
  sensitiveTags: string[];
  requiresApproval: boolean;
  onDecide: (payload: ReviewPayload) => Promise<unknown>;
  size?: "sm" | "xs";
}) {
  const [dialog, setDialog] = useState<Decision | null>(null);
  const [comment, setComment] = useState("");
  const [ack, setAck] = useState(false);
  const run = useMutation({
    mutationFn: onDecide,
    onSuccess: (_d, v) => {
      toast.success(v.decision === "approve" ? "Approved" : v.decision === "reject" ? "Rejected" : "Reopened for review");
      setDialog(null);
      setComment("");
      setAck(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const sensitive = requiresApproval && dialog === "approve";
  const canSubmit = dialog === "reject" || !sensitive || (ack && comment.trim().length > 0);

  return (
    <>
      <div className="flex flex-wrap gap-1.5">
        {status !== "approved" ? (
          <Button
            size={size}
            variant="outline"
            disabled={run.isPending}
            onClick={() => (requiresApproval ? setDialog("approve") : run.mutate({ decision: "approve" }))}
          >
            {requiresApproval ? <ShieldAlert className="size-3.5" /> : <Check className="size-3.5" />} Approve
          </Button>
        ) : null}
        {status !== "rejected" ? (
          <Button size={size} variant="ghost" disabled={run.isPending} onClick={() => setDialog("reject")}>
            <X className="size-3.5" /> Reject
          </Button>
        ) : null}
        {status !== "proposed" ? (
          <Button size={size} variant="ghost" disabled={run.isPending} onClick={() => run.mutate({ decision: "reopen" })}>
            <RotateCcw className="size-3.5" /> Reopen
          </Button>
        ) : null}
      </div>

      <Dialog open={dialog !== null} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent className="sm:max-w-md">
          <form
            className="grid gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (dialog && canSubmit)
                run.mutate({ decision: dialog, comment: comment || undefined, acknowledge_sensitive: ack || undefined });
            }}
          >
            <DialogHeader>
              <DialogTitle>{dialog === "approve" ? "Approve sensitive finding" : "Reject finding"}</DialogTitle>
              <DialogDescription>
                {sensitive
                  ? `This finding involves ${sensitiveTags.map((t) => TAG_LABEL[t] ?? t).join(", ")}. It can only appear in an approved report after a person signs it off.`
                  : "Rejected findings are hidden from reports but kept in the history."}
              </DialogDescription>
            </DialogHeader>
            {sensitive ? (
              <label className="flex items-start gap-2 rounded-lg border bg-rose-50/60 p-3 text-sm dark:bg-rose-950/40">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-[var(--primary)]"
                  checked={ack}
                  onChange={(e) => setAck(e.target.checked)}
                />
                I have checked the supporting evidence and approve sharing this sensitive finding.
              </label>
            ) : null}
            <div className="grid gap-2">
              <Label htmlFor="review-comment">{sensitive ? "Reason (required)" : "Reason (optional)"}</Label>
              <Textarea id="review-comment" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDialog(null)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!canSubmit || run.isPending} variant={dialog === "reject" ? "destructive" : "default"}>
                {dialog === "approve" ? "Approve" : "Reject"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
