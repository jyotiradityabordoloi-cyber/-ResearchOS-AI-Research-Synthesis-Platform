"use client";

import { AlertCircle, ChevronDown, ChevronRight, FileText, Loader2, Save, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api, type InterviewFields, type PreviewItem, type ValidationIssue } from "@/lib/api";
import { FIELD_LABEL } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ValidationBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export interface ReviewItem {
  key: string;
  preview: PreviewItem;
  fields: InterviewFields;
  status: "valid" | "invalid";
  /** Field-validation issues; refreshed from the API as the user edits. */
  issues: ValidationIssue[];
  validating: boolean;
}

const SHORT: (keyof InterviewFields)[] = ["participant_id", "participant_role", "company_size", "plan_tier"];
const LONG: (keyof InterviewFields)[] = ["pain", "behavior", "verbatim_quote"];
const REQUIRED = new Set<keyof InterviewFields>(["participant_id", "pain", "behavior"]);

export function ReviewCard({
  item,
  onChange,
  onValidated,
  onSave,
  onRemove,
  saving,
}: {
  item: ReviewItem;
  onChange: (fields: InterviewFields) => void;
  onValidated: (status: "valid" | "invalid", issues: ValidationIssue[]) => void;
  onSave: () => void;
  onRemove: () => void;
  saving: boolean;
}) {
  const [open, setOpen] = useState(item.status === "invalid");
  const [showRaw, setShowRaw] = useState(false);
  const firstRender = useRef(true);
  const onValidatedRef = useRef(onValidated);
  useEffect(() => {
    onValidatedRef.current = onValidated;
  });

  // Re-validate on the server (single source of truth) shortly after edits.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    let cancelled = false;
    const t = setTimeout(() => {
      api.interviews
        .validate(item.fields)
        .then((r) => !cancelled && onValidatedRef.current(r.status, r.issues))
        .catch(
          () =>
            !cancelled &&
            onValidatedRef.current("invalid", [
              { field: "_network", severity: "error", message: "Could not validate: the API is not reachable." },
            ]),
        );
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [item.fields]);

  const errors = item.issues.filter((i) => i.severity === "error");
  const warnings = [...item.preview.context_issues, ...item.issues.filter((i) => i.severity === "warning")];
  const errorFor = (k: string) => errors.find((e) => e.field === k)?.message;
  const set = (k: keyof InterviewFields) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    onChange({ ...item.fields, [k]: e.target.value });
  const edited = (Object.keys(item.fields) as (keyof InterviewFields)[]).some(
    (k) => item.fields[k] !== item.preview.fields[k],
  );

  return (
    <div
      className={cn(
        "rounded-xl border bg-background shadow-xs",
        item.status === "invalid" && "border-destructive/40",
      )}
    >
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <Button
          variant="ghost"
          size="icon"
          className="size-7"
          onClick={() => setOpen(!open)}
          aria-label={open ? "Collapse" : "Expand to review and edit"}
          aria-expanded={open}
        >
          {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        </Button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">
              {item.fields.participant_id || <span className="text-destructive">No participant ID</span>}
            </span>
            {item.validating ? (
              <Loader2 className="size-3.5 animate-spin text-muted-foreground" aria-label="Validating" />
            ) : (
              <ValidationBadge status={item.status} />
            )}
            {edited ? <span className="text-xs text-muted-foreground">edited</span> : null}
          </div>
          <p className="truncate text-xs text-muted-foreground">
            #{item.preview.index + 1}
            {item.preview.source_filename ? ` · ${item.preview.source_filename}` : ""}
            {item.fields.participant_role ? ` · ${item.fields.participant_role}` : ""}
            {errors.length ? ` · ${errors.length} error(s)` : ""}
            {warnings.length ? ` · ${warnings.length} warning(s)` : ""}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="outline"
            onClick={onSave}
            disabled={item.status !== "valid" || item.validating || saving}
          >
            <Save className="size-3.5" /> Save
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="size-8 text-muted-foreground hover:text-destructive"
            onClick={onRemove}
            aria-label="Remove from this import"
          >
            <X className="size-4" />
          </Button>
        </div>
      </div>

      {open ? (
        <div className="space-y-4 border-t px-4 py-4">
          {errors.length || warnings.length ? (
            <ul className="space-y-1 text-sm">
              {errors.map((e) => (
                <li key={`e-${e.field}-${e.message}`} className="flex gap-2 text-destructive">
                  <AlertCircle className="mt-0.5 size-3.5 shrink-0" /> {e.message}
                </li>
              ))}
              {warnings.map((w) => (
                <li key={`w-${w.field}-${w.message}`} className="flex gap-2 text-amber-700 dark:text-amber-400">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0" /> {w.message}
                </li>
              ))}
            </ul>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {SHORT.map((k) => (
              <div key={k} className="grid gap-1.5">
                <Label htmlFor={`${item.key}-${k}`} className="text-xs">
                  {FIELD_LABEL[k]}
                  {REQUIRED.has(k) ? " *" : ""}
                </Label>
                <Input
                  id={`${item.key}-${k}`}
                  value={item.fields[k]}
                  onChange={set(k)}
                  aria-invalid={Boolean(errorFor(k))}
                />
              </div>
            ))}
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            {LONG.map((k) => (
              <div key={k} className="grid gap-1.5">
                <Label htmlFor={`${item.key}-${k}`} className="text-xs">
                  {FIELD_LABEL[k]}
                  {REQUIRED.has(k) ? " *" : ""}
                </Label>
                <Textarea
                  id={`${item.key}-${k}`}
                  value={item.fields[k]}
                  onChange={set(k)}
                  rows={4}
                  aria-invalid={Boolean(errorFor(k))}
                />
                {errorFor(k) ? <p className="text-xs text-destructive">{errorFor(k)}</p> : null}
              </div>
            ))}
          </div>

          <div>
            <Button variant="link" size="sm" className="h-auto px-0" onClick={() => setShowRaw(!showRaw)}>
              <FileText className="size-3.5" /> {showRaw ? "Hide" : "Show"} original notes
            </Button>
            {showRaw ? (
              <pre className="mt-2 max-h-56 overflow-auto rounded-lg border bg-muted/30 p-3 font-mono text-xs whitespace-pre-wrap">
                {item.preview.raw_content}
              </pre>
            ) : null}
            <p className="mt-1 text-xs text-muted-foreground">
              The original notes are saved exactly as they were; your edits apply to the structured fields only.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
