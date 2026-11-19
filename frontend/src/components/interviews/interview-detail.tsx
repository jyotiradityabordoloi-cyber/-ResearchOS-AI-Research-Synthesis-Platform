"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowUpRight,
  BadgeCheck,
  ChevronDown,
  ChevronUp,
  Layers,
  Lightbulb,
  Pencil,
  Scale,
  ShieldAlert,
  Sparkle,
  Trash2,
  X,
} from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";

import { api, type Interview, type InterviewFindings } from "@/lib/api";
import { percent, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ValidationBadge } from "@/components/common";
import { Highlight } from "@/components/highlight";
import { InterviewFormDialog } from "@/components/interviews/interview-form-dialog";
import { StatusBadge } from "@/components/review/review-controls";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const PRIORITY_TONE: Record<string, string> = {
  high: "bg-rose-50 text-rose-700",
  medium: "bg-amber-50 text-amber-800",
  low: "bg-muted text-muted-foreground",
};

export function ParticipantAvatar({ id, className }: { id: string; className?: string }) {
  return (
    <span
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 font-mono text-xs font-semibold text-primary",
        className,
      )}
      aria-hidden
    >
      {(id || "?").slice(0, 3).toUpperCase()}
    </span>
  );
}

/**
 * Everything about one interview: the structured fields, what synthesis derived from
 * it (pain points, themes, insights), and the untouched original notes with every
 * quote that synthesis relied on highlighted.
 */
export function InterviewDetail({
  interview: iv,
  onClose,
  onPrev,
  onNext,
  onFilter,
  position,
}: {
  interview: Interview;
  onClose?: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  /** Apply a facet filter (role / company size / plan tier) from a chip. */
  onFilter?: (key: "role" | "company_size" | "plan_tier", value: string) => void;
  position?: string;
}) {
  const qc = useQueryClient();
  const findings = useQuery({
    queryKey: ["interview-findings", iv.id],
    queryFn: () => api.interviews.findings(iv.id),
  });
  const remove = useMutation({
    mutationFn: () => api.interviews.remove(iv.id),
    onSuccess: () => {
      qc.invalidateQueries();
      toast.success(`Interview ${iv.participant_id || ""} deleted`);
      onClose?.();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const quotes = [
    ...(findings.data?.themes.flatMap((t) => t.quotes.filter((q) => q.verified).map((q) => q.quote)) ?? []),
    ...(findings.data?.pain_points.filter((p) => p.quote_verified).map((p) => p.quote) ?? []),
  ];
  const issues = iv.validation_errors;

  return (
    <div className="flex h-full flex-col">
      <header className="space-y-3 border-b px-5 pt-4 pb-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1">
            {onPrev || onNext ? (
              <>
                <Button variant="ghost" size="icon" className="size-7" onClick={onPrev} disabled={!onPrev} aria-label="Previous interview">
                  <ChevronUp />
                </Button>
                <Button variant="ghost" size="icon" className="size-7" onClick={onNext} disabled={!onNext} aria-label="Next interview">
                  <ChevronDown />
                </Button>
                {position ? <span className="ml-1 text-xs text-muted-foreground tabular-nums">{position}</span> : null}
              </>
            ) : null}
          </div>
          <div className="flex items-center gap-0.5">
            <InterviewFormDialog
              projectId={iv.project_id}
              interview={iv}
              trigger={
                <Button variant="ghost" size="icon" className="size-7" aria-label="Correct interview">
                  <Pencil className="size-3.5" />
                </Button>
              }
            />
            <Button
              variant="ghost"
              size="icon"
              className="size-7 text-muted-foreground hover:text-destructive"
              aria-label="Delete interview"
              disabled={remove.isPending}
              onClick={() => {
                if (confirm(`Delete interview ${iv.participant_id || ""}? This is logged and cannot be undone.`)) remove.mutate();
              }}
            >
              <Trash2 className="size-3.5" />
            </Button>
            {onClose ? (
              <Button variant="ghost" size="icon" className="size-7" onClick={onClose} aria-label="Close interview">
                <X />
              </Button>
            ) : null}
          </div>
        </div>

        <div className="flex items-start gap-3">
          <ParticipantAvatar id={iv.participant_id} className="size-11" />
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold tracking-tight">
                {iv.participant_id || <span className="text-destructive">Missing participant ID</span>}
              </h2>
              <ValidationBadge status={iv.validation_status} />
            </div>
            <p className="truncate text-xs text-muted-foreground">
              <Link href={`/projects/${iv.project_id}?tab=interviews`} className="hover:text-foreground hover:underline">
                {iv.project_name}
              </Link>{" "}
              · added {timeAgo(iv.created_at)} · {iv.source}
              {iv.source_filename ? ` (${iv.source_filename})` : ""}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5">
          <FacetChip label="Role" value={iv.participant_role} onClick={onFilter && (() => onFilter("role", iv.participant_role))} />
          <FacetChip label="Size" value={iv.company_size} onClick={onFilter && (() => onFilter("company_size", iv.company_size))} />
          <FacetChip label="Plan" value={iv.plan_tier} onClick={onFilter && (() => onFilter("plan_tier", iv.plan_tier))} />
        </div>
      </header>

      <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
        {issues.length ? (
          <ul className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm">
            {issues.map((e) => (
              <li
                key={`${e.field}-${e.message}`}
                className={cn("flex gap-2", e.severity === "error" ? "text-destructive" : "text-amber-800")}
              >
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                {e.message}
              </li>
            ))}
          </ul>
        ) : null}

        <Section title="Pain point">
          {iv.pain ? (
            <p className="rounded-lg border-l-2 border-rose-400 bg-rose-50/60 px-3 py-2 text-sm text-pretty">{iv.pain}</p>
          ) : (
            <Empty>No pain recorded.</Empty>
          )}
        </Section>
        <Section title="Behavior">
          {iv.behavior ? <p className="text-sm text-pretty">{iv.behavior}</p> : <Empty>No behavior recorded.</Empty>}
        </Section>
        {iv.verbatim_quote ? (
          <Section title="Verbatim quote">
            <blockquote className="border-l-2 border-primary/50 pl-3 text-sm italic text-pretty">“{iv.verbatim_quote}”</blockquote>
          </Section>
        ) : null}

        <Section title="What synthesis found" hint="From the project's active synthesis run.">
          <FindingsBlock projectId={iv.project_id} findings={findings.data} loading={findings.isPending} error={findings.error} />
        </Section>

        <Section title="Original notes" hint="Read-only, exactly as imported. Highlights are quotes synthesis relied on.">
          <pre className="max-h-80 overflow-auto rounded-lg border bg-muted/30 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap">
            <Highlight text={iv.raw_content} terms={quotes} />
          </pre>
        </Section>
      </div>
    </div>
  );
}

function FacetChip({ label, value, onClick }: { label: string; value: string; onClick?: () => void }) {
  if (!value) return null;
  const body = (
    <>
      <span className="text-muted-foreground">{label}</span> {value}
    </>
  );
  return onClick ? (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          className="inline-flex h-6 items-center gap-1 rounded-md border bg-background px-2 text-xs transition-[border-color,background-color,transform] duration-150 ease-out hover:border-primary/40 hover:bg-primary/5 active:scale-[0.97]"
        >
          {body}
        </button>
      </TooltipTrigger>
      <TooltipContent>Show only interviews with this {label.toLowerCase()}</TooltipContent>
    </Tooltip>
  ) : (
    <span className="inline-flex h-6 items-center gap-1 rounded-md border bg-background px-2 text-xs">{body}</span>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <div>
        <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{title}</h3>
        {hint ? <p className="text-xs text-muted-foreground/80">{hint}</p> : null}
      </div>
      {children}
    </section>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted-foreground italic">{children}</p>;
}

function FindingsBlock({
  projectId,
  findings,
  loading,
  error,
}: {
  projectId: string;
  findings?: InterviewFindings;
  loading: boolean;
  error: unknown;
}) {
  if (loading) return <Skeleton className="h-28 w-full" />;
  if (error || !findings) return <p className="text-sm text-destructive">Could not load what synthesis found.</p>;
  if (!findings.synthesised)
    return <Empty>This project has not been synthesised yet, so nothing has been derived from this interview.</Empty>;
  if (!findings.pain_points.length && !findings.themes.length)
    return <Empty>Synthesis extracted nothing from this interview (it may have been invalid at the time).</Empty>;

  return (
    <div className="space-y-4">
      {findings.pain_points.length ? (
        <ul className="space-y-2">
          {findings.pain_points.map((pp) => (
            <li key={pp.id} className="rounded-lg border bg-background px-3 py-2.5 text-sm">
              <p className="text-pretty">{pp.text}</p>
              {pp.quote ? (
                <p className="mt-1 flex gap-1.5 text-xs text-muted-foreground italic">
                  “{pp.quote}”
                  {pp.quote_verified ? <BadgeCheck className="size-3.5 shrink-0 text-emerald-600" aria-label="Verified quote" /> : null}
                </p>
              ) : null}
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
                {pp.severity ? <Badge variant="secondary">severity {pp.severity}/5</Badge> : null}
                {pp.sensitive_tags.map((t) => (
                  <Badge key={t} variant="secondary" className="bg-rose-50 text-rose-700 capitalize">
                    <ShieldAlert /> {t}
                  </Badge>
                ))}
                {pp.duplicate_count ? (
                  <Badge variant="outline">said {pp.duplicate_count + 1}× (counted once)</Badge>
                ) : null}
                {pp.theme_id ? (
                  <Link
                    href={`/projects/${projectId}?tab=themes`}
                    className="ml-auto inline-flex items-center gap-1 text-primary hover:underline"
                  >
                    <Layers className="size-3" />
                    {pp.theme_code} {pp.theme_name}
                  </Link>
                ) : (
                  <span className="ml-auto text-muted-foreground">Not in a theme</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      {findings.themes.length ? (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Cited as evidence in</p>
          <ul className="space-y-1.5">
            {findings.themes.map((t) => {
              const contradicts = t.quotes.some((q) => q.stance === "contradicting");
              return (
                <li key={t.theme_id}>
                  <Link
                    href={`/projects/${projectId}?tab=themes`}
                    className="group flex items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm transition-colors duration-150 hover:border-primary/30 hover:bg-primary/5"
                  >
                    <span className="font-mono text-xs text-muted-foreground">{t.code}</span>
                    <span className="min-w-0 flex-1 truncate font-medium">{t.name}</span>
                    {contradicts ? (
                      <Badge variant="secondary" className="bg-amber-50 text-amber-800">
                        <Scale /> contradicts
                      </Badge>
                    ) : null}
                    {t.is_outlier ? <Sparkle className="size-3.5 text-violet-600" aria-label="Single participant" /> : null}
                    <span className="text-xs text-muted-foreground tabular-nums">{percent(t.frequency)}</span>
                    <StatusBadge status={t.status} />
                    <ArrowUpRight className="size-3.5 text-muted-foreground transition-transform duration-150 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {findings.insights.length ? (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Feeds these insights</p>
          <ul className="space-y-1">
            {findings.insights.map((i) => (
              <li key={i.id}>
                <Link
                  href={`/projects/${projectId}?tab=insights&insight=${i.id}`}
                  className="flex items-center gap-2 rounded-md px-1 py-1 text-sm hover:bg-muted/60"
                >
                  <Lightbulb className="size-3.5 shrink-0 text-muted-foreground" />
                  <Badge variant="secondary" className={cn("capitalize", PRIORITY_TONE[i.priority])}>
                    {i.priority}
                  </Badge>
                  <span className="min-w-0 flex-1 truncate">{i.title}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
