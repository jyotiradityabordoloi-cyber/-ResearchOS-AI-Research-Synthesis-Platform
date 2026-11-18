"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { api, type Interview, type InterviewFields } from "@/lib/api";
import { FIELD_LABEL } from "@/lib/format";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const EMPTY: InterviewFields = {
  participant_id: "",
  participant_role: "",
  company_size: "",
  plan_tier: "",
  pain: "",
  behavior: "",
  verbatim_quote: "",
};
const SHORT: (keyof InterviewFields)[] = ["participant_id", "participant_role", "company_size", "plan_tier"];
const LONG: (keyof InterviewFields)[] = ["pain", "behavior", "verbatim_quote"];
const REQUIRED = new Set<keyof InterviewFields>(["participant_id", "pain", "behavior"]);

/** Only the editable structured fields — never ids or the original raw notes. */
function pickFields(source: InterviewFields): InterviewFields {
  return Object.fromEntries((Object.keys(EMPTY) as (keyof InterviewFields)[]).map((k) => [k, source[k] ?? ""])) as unknown as InterviewFields;
}

/**
 * Add a single interview (projectId) or correct an existing one (interview).
 * Corrections only change structured fields — the original raw notes are kept.
 */
export function InterviewFormDialog({
  projectId,
  interview,
  trigger,
}: {
  projectId: string;
  interview?: Interview;
  trigger?: React.ReactNode;
}) {
  const editing = Boolean(interview);
  const [open, setOpen] = useState(false);
  const [fields, setFields] = useState<InterviewFields>(interview ? pickFields(interview) : EMPTY);
  const [comment, setComment] = useState("");
  const qc = useQueryClient();

  const save = useMutation({
    mutationFn: () =>
      interview
        ? api.interviews.correct(interview.id, { ...fields, comment: comment || undefined })
        : api.interviews.create(projectId, fields),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["interviews"] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["audit", projectId] });
      qc.invalidateQueries({ queryKey: ["validation", projectId] });
      if (saved.validation_status === "valid") toast.success(editing ? "Interview corrected" : "Interview saved");
      else toast.warning("Saved, but it still has validation errors and will be excluded from synthesis.");
      setOpen(false);
      if (!editing) setFields(EMPTY);
      setComment("");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  // Show the saved error for a field only until the user edits that field.
  const editedIssue = (k: keyof InterviewFields) =>
    interview && fields[k] === interview[k]
      ? interview.validation_errors.find((i) => i.field === k && i.severity === "error")
      : undefined;

  const set = (k: keyof InterviewFields) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setFields((f) => ({ ...f, [k]: e.target.value }));

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o && interview) setFields(pickFields(interview));
      }}
    >
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="outline">
            <Plus className="size-4" /> Add interview
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <form
          className="grid gap-5"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>{editing ? `Correct interview ${interview?.participant_id || ""}` : "Add interview"}</DialogTitle>
            <DialogDescription>
              {editing
                ? "Fix the structured fields. The original notes are preserved and every change is logged."
                : "Fields marked * are required for synthesis."}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 sm:grid-cols-2">
            {SHORT.map((k) => {
              const issue = editedIssue(k);
              return (
                <div key={k} className="grid gap-2">
                  <Label htmlFor={`f-${k}`}>
                    {FIELD_LABEL[k]}
                    {REQUIRED.has(k) ? " *" : ""}
                  </Label>
                  <Input id={`f-${k}`} value={fields[k]} onChange={set(k)} aria-invalid={Boolean(issue)} />
                  {issue ? <p className="text-xs text-destructive">{issue.message}</p> : null}
                </div>
              );
            })}
          </div>
          {LONG.map((k) => {
            const issue = editedIssue(k);
            return (
              <div key={k} className="grid gap-2">
                <Label htmlFor={`f-${k}`}>
                  {FIELD_LABEL[k]}
                  {REQUIRED.has(k) ? " *" : ""}
                </Label>
                <Textarea id={`f-${k}`} value={fields[k]} onChange={set(k)} rows={3} aria-invalid={Boolean(issue)} />
                {issue ? <p className="text-xs text-destructive">{issue.message}</p> : null}
              </div>
            );
          })}
          {editing ? (
            <div className="grid gap-2">
              <Label htmlFor="f-comment">Reason for correction (optional)</Label>
              <Input id="f-comment" value={comment} onChange={(e) => setComment(e.target.value)} />
            </div>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : editing ? "Save correction" : "Save interview"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
