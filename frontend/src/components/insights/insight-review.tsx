"use client";

import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  ArrowUpRight,
  BadgeCheck,
  ChevronRight,
  Hand,
  Layers,
  Lightbulb,
  MessageSquare,
  Pencil,
  Quote,
  Scale,
  Search,
  ShieldAlert,
  Sparkle,
  Star,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { api, type AuditEntry, type Insight, type PriorityBand, type SensitiveTag } from "@/lib/api";
import { percent, timeAgo } from "@/lib/format";
import { useUrlState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/common";
import { EditableText } from "@/components/editable-text";
import { OriginalNotesButton } from "@/components/interviews/original-notes-dialog";
import { DecisionButtons, StatusBadge, useReviewRefresh } from "@/components/review/review-controls";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const ALL = "all";
const BAND_STYLE: Record<PriorityBand, string> = {
  high: "bg-rose-50 text-rose-700",
  medium: "bg-amber-50 text-amber-800",
  low: "bg-muted text-muted-foreground",
};
const BAND_RAIL: Record<PriorityBand, string> = {
  high: "before:bg-rose-500",
  medium: "before:bg-amber-400",
  low: "before:bg-muted-foreground/30",
};
const TAG_LABEL: Record<SensitiveTag, string> = {
  pricing: "Pricing",
  churn: "Churn",
  competitive_switching: "Competitive switching",
};

// ---------------------------------------------------------------------------
// List with filters
// ---------------------------------------------------------------------------

/**
 * Card-based insight review. Filters live in the URL (`?priority=high&status=proposed`)
 * and so does the open card (`?insight=<id>`), so the dashboard can deep-link straight
 * to one finding.
 */
export function InsightReview({
  insights,
  showProject = false,
  onEditScores,
  focus,
}: {
  insights: Insight[];
  showProject?: boolean;
  onEditScores: (insight: Insight) => void;
  /** Open and scroll to this insight (e.g. a dot clicked on the chart). A new object re-focuses. */
  focus?: { id: string } | null;
}) {
  const [q, setQ] = useState("");
  const [priority, setPriority] = useUrlState("priority", ALL);
  const [status, setStatus] = useUrlState("status", ALL);
  const [sensitiveOnly, setSensitiveOnly] = useUrlState("sensitive", "");
  const [open, setOpen] = useUrlState("insight", "");
  const term = q.trim().toLowerCase();

  const matchesText = (i: Insight) =>
    !term ||
    [i.title, i.statement, i.implication, i.theme_name ?? "", i.theme_code ?? "", i.project_name ?? ""].some((t) =>
      t.toLowerCase().includes(term),
    );
  const base = insights.filter((i) => matchesText(i) && (!sensitiveOnly || i.requires_approval));
  const visible = base.filter((i) => (priority === ALL || i.effective_priority === priority) && (status === ALL || i.status === status));
  const priorityCounts = countBy(base.filter((i) => status === ALL || i.status === status), (i) => i.effective_priority);
  const statusCounts = countBy(base.filter((i) => priority === ALL || i.effective_priority === priority), (i) => i.status);
  const filtered = Boolean(term || sensitiveOnly || priority !== ALL || status !== ALL);
  const pending = visible.filter((i) => i.status === "proposed");

  useEffect(() => {
    if (focus) setOpen(focus.id);
    // Only a new focus request should re-open a card.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus]);

  const openNextPending = (after: string) => {
    const idx = visible.findIndex((i) => i.id === after);
    const next = [...visible.slice(idx + 1), ...visible.slice(0, Math.max(idx, 0))].find((i) => i.status === "proposed" && i.id !== after);
    if (!next) {
      setOpen("");
      toast.success("Nothing left to review in this view");
      return;
    }
    setOpen(next.id);
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2.5">
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <div className="relative flex-1 md:max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search insights, themes, implications"
              className="bg-background pl-9"
              aria-label="Search insights"
            />
          </div>
          <label className="flex items-center gap-2 text-sm md:ml-auto">
            <input
              type="checkbox"
              className="size-4 accent-[var(--primary)]"
              checked={Boolean(sensitiveOnly)}
              onChange={(e) => setSensitiveOnly(e.target.checked ? "1" : "")}
            />
            <ShieldAlert className="size-3.5 text-rose-600" /> Sensitive only
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <ChipGroup
            label="Priority"
            value={priority}
            onChange={setPriority}
            options={[
              [ALL, "All", base.filter((i) => status === ALL || i.status === status).length],
              ["high", "High", priorityCounts.high ?? 0],
              ["medium", "Medium", priorityCounts.medium ?? 0],
              ["low", "Low", priorityCounts.low ?? 0],
            ]}
          />
          <ChipGroup
            label="Status"
            value={status}
            onChange={setStatus}
            options={[
              [ALL, "All", base.filter((i) => priority === ALL || i.effective_priority === priority).length],
              ["proposed", "Awaiting review", statusCounts.proposed ?? 0],
              ["approved", "Approved", statusCounts.approved ?? 0],
              ["rejected", "Rejected", statusCounts.rejected ?? 0],
            ]}
          />
          {filtered ? (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-muted-foreground"
              onClick={() => {
                setQ("");
                setPriority(ALL);
                setStatus(ALL);
                setSensitiveOnly("");
              }}
            >
              <X /> Clear
            </Button>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">
          {visible.length} insight{visible.length === 1 ? "" : "s"}
          {pending.length ? ` · ${pending.length} awaiting review` : ""}. Frequency, severity, strategic relevance and
          confidence are separate measures; priority combines them unless a reviewer overrode it.
        </p>
      </div>

      {visible.length ? (
        <div className="space-y-2.5">
          {visible.map((i, n) => (
            <InsightCard
              key={i.id}
              insight={i}
              index={n}
              open={open === i.id}
              showProject={showProject}
              onToggle={() => setOpen(open === i.id ? "" : i.id)}
              onEditScores={() => onEditScores(i)}
              onDecided={(decision) => {
                if (decision !== "reopen") openNextPending(i.id);
              }}
              onNext={() => openNextPending(i.id)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Lightbulb}
          title={filtered ? "No insights match these filters" : "No insights yet"}
          description={filtered ? "Loosen a filter to see more." : "Run synthesis on a project to generate insights."}
        />
      )}
    </div>
  );
}

function countBy<T>(items: T[], key: (t: T) => string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const item of items) out[key(item)] = (out[key(item)] ?? 0) + 1;
  return out;
}

function ChipGroup({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string, number][];
}) {
  return (
    <div className="flex flex-wrap items-center gap-1" role="radiogroup" aria-label={`Filter by ${label.toLowerCase()}`}>
      <span className="mr-1 text-xs text-muted-foreground">{label}</span>
      {options.map(([v, text, count]) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={value === v}
          onClick={() => onChange(v)}
          className={cn(
            "inline-flex h-7 items-center gap-1 rounded-full border px-2.5 text-xs transition-[color,background-color,border-color,transform] duration-150 ease-out active:scale-[0.97]",
            value === v ? "border-primary/30 bg-primary/8 font-medium text-primary" : "bg-background text-muted-foreground hover:text-foreground",
          )}
        >
          {text} <span className="tabular-nums opacity-70">{count}</span>
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card
// ---------------------------------------------------------------------------

function InsightCard({
  insight: i,
  index,
  open,
  showProject,
  onToggle,
  onEditScores,
  onDecided,
  onNext,
}: {
  insight: Insight;
  index: number;
  open: boolean;
  showProject: boolean;
  onToggle: () => void;
  onEditScores: () => void;
  onDecided: (decision: "approve" | "reject" | "reopen") => void;
  onNext: () => void;
}) {
  const refresh = useReviewRefresh(i.project_id);
  const ref = useRef<HTMLElement>(null);
  const [flagging, setFlagging] = useState(false);

  useEffect(() => {
    if (open) ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [open]);

  const edit = useMutation({
    mutationFn: (data: Parameters<typeof api.review.editInsight>[1]) => api.review.editInsight(i.id, data),
    onSuccess: () => {
      refresh();
      toast.success("Insight updated");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <article
      ref={ref}
      className={cn(
        "enter relative overflow-hidden rounded-xl border bg-background shadow-xs transition-[border-color,box-shadow] duration-150",
        "before:absolute before:inset-y-0 before:left-0 before:w-1",
        BAND_RAIL[i.effective_priority],
        open ? "border-primary/30 shadow-md" : "hover:border-foreground/15",
        i.status === "rejected" && "opacity-70",
      )}
      style={{ "--i": index } as React.CSSProperties}
    >
      <div className="flex gap-3 py-3.5 pr-4 pl-5">
        <button
          type="button"
          onClick={onToggle}
          className="mt-0.5 h-fit rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-expanded={open}
          aria-label={open ? "Collapse insight" : "Expand insight"}
        >
          <ChevronRight className={cn("size-4 transition-transform duration-200 ease-out-strong", open && "rotate-90")} />
        </button>

        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <PriorityBadge insight={i} />
            {i.theme_id ? (
              <Link
                href={`/projects/${i.project_id}?tab=themes&theme=${i.theme_id}`}
                className="inline-flex min-w-0 items-center gap-1 text-muted-foreground hover:text-primary"
                title="Open the theme on the canvas"
              >
                <Layers className="size-3 shrink-0" />
                <span className="font-mono">{i.theme_code}</span>
                <span className="truncate">{i.theme_name}</span>
              </Link>
            ) : (
              <span className="text-muted-foreground">No linked theme</span>
            )}
            {showProject ? (
              <Link href={`/projects/${i.project_id}?tab=insights`} className="truncate text-muted-foreground hover:text-foreground">
                · {i.project_name}
              </Link>
            ) : null}
          </div>
          <button type="button" onClick={onToggle} className="block text-left">
            <h3 className="font-medium text-pretty">{i.title}</h3>
          </button>

          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-5">
            <Metric label="Frequency" hint={i.theme_id ? `${i.participant_count} participants` : "No theme"}>
              <div className="flex items-center gap-1.5">
                <span className="h-1.5 w-10 overflow-hidden rounded-full bg-muted">
                  <span className="bar-fill block h-full rounded-full bg-primary/70" style={{ width: `${Math.max(i.frequency * 100, 3)}%` }} />
                </span>
                {percent(i.frequency)}
              </div>
            </Metric>
            <Metric label="Severity" hint={`${i.severity} of 5`}>
              <Dots value={i.severity} />
            </Metric>
            <Metric label="Strategic" hint={`${i.strategic_relevance} of 5`}>
              <Dots value={i.strategic_relevance} />
            </Metric>
            <Metric label="Confidence">{percent(i.confidence)}</Metric>
            <Metric label="Evidence">
              <span className="inline-flex items-center gap-1">
                <Quote className="size-3 text-muted-foreground" />
                {i.evidence_count}
                {i.contradicting_count ? (
                  <span className="inline-flex items-center gap-0.5 text-amber-700">
                    · <Scale className="size-3" />
                    {i.contradicting_count}
                  </span>
                ) : null}
              </span>
            </Metric>
          </dl>

          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge status={i.status} />
            {i.requires_approval ? (
              <Badge variant="secondary" className="bg-rose-50 text-rose-700">
                <ShieldAlert /> {i.sensitive_tags.map((t) => TAG_LABEL[t as SensitiveTag] ?? t).join(", ") || "Sensitive"}
              </Badge>
            ) : null}
            {i.strategic_flag ? (
              <Badge variant="secondary" className="bg-sky-50 text-sky-700">
                <Star /> Strategic
              </Badge>
            ) : null}
            {i.is_outlier ? (
              <Badge variant="secondary" className="bg-violet-50 text-violet-700">
                <Sparkle /> Single participant
              </Badge>
            ) : null}
            {i.origin === "manual" ? <Badge variant="outline">PM-written</Badge> : null}
            {i.comment_count ? (
              <Badge variant="outline" className="text-muted-foreground">
                <MessageSquare /> {i.comment_count}
              </Badge>
            ) : null}
          </div>
        </div>

        <div className="hidden shrink-0 sm:block">
          <DecisionButtons
            size="xs"
            status={i.status}
            sensitiveTags={i.sensitive_tags}
            requiresApproval={i.requires_approval}
            onDecide={async (payload) => {
              const r = await api.review.reviewInsight(i.id, payload);
              refresh();
              onDecided(payload.decision);
              return r;
            }}
          />
        </div>
      </div>

      {open ? (
        <div className="reveal grid gap-5 border-t bg-muted/20 px-5 py-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-4">
            <div className="sm:hidden">
              <DecisionButtons
                size="xs"
                status={i.status}
                sensitiveTags={i.sensitive_tags}
                requiresApproval={i.requires_approval}
                onDecide={async (payload) => {
                  const r = await api.review.reviewInsight(i.id, payload);
                  refresh();
                  onDecided(payload.decision);
                  return r;
                }}
              />
            </div>
            {i.statement ? (
              <Section title="What we learned">
                <p className="text-sm text-pretty">{i.statement}</p>
              </Section>
            ) : null}
            <Section title="Product implication" hint={i.origin === "ai" ? "AI-suggested; edit it into something your team will act on" : undefined}>
              <EditableText
                value={i.implication}
                multiline
                disabled={edit.isPending || i.status === "rejected"}
                onSave={(v) => edit.mutate({ implication: v })}
                render={(v) => <p className="text-sm text-pretty">{v || <span className="text-muted-foreground italic">No implication yet.</span>}</p>}
                label="implication"
              />
            </Section>
            <EvidenceSection insight={i} />
          </div>

          <aside className="space-y-4">
            <div className="flex flex-wrap gap-1.5">
              <Button size="sm" variant="outline" onClick={onEditScores}>
                <Pencil /> Scores & priority
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => edit.mutate({ strategic_flag: !i.strategic_flag })}
                disabled={edit.isPending}
                aria-pressed={i.strategic_flag}
              >
                <Star className={cn(i.strategic_flag && "fill-current text-sky-600")} /> {i.strategic_flag ? "Strategic" : "Mark strategic"}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setFlagging(true)}>
                <ShieldAlert className="text-rose-600" /> Flag sensitive
              </Button>
            </div>
            {i.is_overridden ? (
              <p className="rounded-lg border bg-background px-3 py-2 text-xs text-muted-foreground">
                <Hand className="mr-1 inline size-3" />
                Priority set by hand to <span className="font-medium text-foreground">{i.effective_priority}</span> (computed:{" "}
                {i.computed_priority}). Reason: {i.override_reason}
              </p>
            ) : null}
            <CommentThread insight={i} />
            {i.status === "proposed" ? null : (
              <Button variant="ghost" size="sm" className="w-full text-muted-foreground" onClick={onNext}>
                Next awaiting review <ArrowRight />
              </Button>
            )}
          </aside>
        </div>
      ) : null}

      <FlagSensitiveDialog insight={i} open={flagging} onOpenChange={setFlagging} />
    </article>
  );
}

function PriorityBadge({ insight }: { insight: Insight }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="secondary" className={cn("capitalize", BAND_STYLE[insight.effective_priority])}>
          {insight.is_overridden ? <Hand /> : null}
          {insight.effective_priority}
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">
        {insight.is_overridden
          ? `Set by hand (computed: ${insight.computed_priority}). ${insight.override_reason ?? ""}`
          : `Computed from frequency, severity, strategic relevance and confidence (score ${insight.priority_score.toFixed(2)}).`}
      </TooltipContent>
    </Tooltip>
  );
}

function Metric({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div title={hint}>
      <dt className="text-[10px] tracking-wide text-muted-foreground uppercase">{label}</dt>
      <dd className="text-sm font-medium tabular-nums">{children}</dd>
    </div>
  );
}

function Dots({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="inline-flex gap-0.5" aria-hidden>
        {[1, 2, 3, 4, 5].map((n) => (
          <span key={n} className={cn("h-2.5 w-1.5 rounded-sm", n <= value ? "bg-primary/80" : "bg-muted")} />
        ))}
      </span>
      <span className="text-xs text-muted-foreground">{value}/5</span>
    </span>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="space-y-1.5">
      <div>
        <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{title}</h4>
        {hint ? <p className="text-xs text-muted-foreground/80">{hint}</p> : null}
      </div>
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Evidence, comments, sensitive flag
// ---------------------------------------------------------------------------

function EvidenceSection({ insight }: { insight: Insight }) {
  const q = useQuery({ queryKey: ["insight-evidence", insight.id], queryFn: () => api.review.insightEvidence(insight.id) });
  if (q.isPending) return <Skeleton className="h-32 w-full" />;
  if (q.error || !q.data) return <p className="text-sm text-destructive">Could not load the evidence.</p>;
  if (!q.data.theme)
    return (
      <Section title="Evidence">
        <p className="text-sm text-muted-foreground italic">This insight is not linked to a theme, so it has no interview evidence.</p>
      </Section>
    );
  const supporting = q.data.evidence.filter((e) => e.stance === "supporting");
  const contradicting = q.data.evidence.filter((e) => e.stance === "contradicting");
  return (
    <>
      <Section
        title={`Supporting evidence (${supporting.length})`}
        hint={`${q.data.theme.participant_ids.length} of ${q.data.theme.total_participants} participants: ${q.data.theme.participant_ids.join(", ")}`}
      >
        <EvidenceList items={supporting} />
      </Section>
      {contradicting.length ? (
        <section className="space-y-1.5 rounded-lg border border-amber-200 bg-amber-50/50 p-3">
          <h4 className="flex items-center gap-1 text-xs font-medium tracking-wide text-amber-800 uppercase">
            <Scale className="size-3" /> Contradicting evidence ({contradicting.length})
          </h4>
          <EvidenceList items={contradicting} />
        </section>
      ) : null}
    </>
  );
}

function EvidenceList({ items }: { items: NonNullable<Awaited<ReturnType<typeof api.review.insightEvidence>>>["evidence"] }) {
  return (
    <ul className="space-y-2">
      {items.map((e) => (
        <li key={e.id} className="rounded-lg border bg-background px-3 py-2 text-sm">
          <blockquote className={cn("border-l-2 pl-2.5 text-pretty", e.stance === "contradicting" ? "border-amber-500" : "border-primary/40")}>
            “{e.quote}”
          </blockquote>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <Link
              href={`/interviews?interview=${e.interview_id}`}
              className="inline-flex items-center gap-0.5 font-medium text-foreground hover:text-primary"
              title="Open the source interview"
            >
              {e.participant_id} <ArrowUpRight className="size-3" />
            </Link>
            <span className="truncate">{[e.participant_role, e.company_size, e.plan_tier].filter(Boolean).join(" · ")}</span>
            {e.quote_verified ? (
              <span className="inline-flex items-center gap-0.5 text-emerald-700">
                <BadgeCheck className="size-3" /> verified
              </span>
            ) : (
              <span>not verbatim</span>
            )}
            <span className="ml-auto">
              <OriginalNotesButton interviewId={e.interview_id} highlight={e.quote} />
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}

const DECISION_TEXT: Record<string, string> = {
  approve: "approved",
  reject: "rejected",
  reopen: "reopened",
  flag_sensitive: "flagged as sensitive",
  override_priority: "overrode the priority",
  edit: "edited",
  create: "created",
  flag_strategic: "changed the strategic flag",
  comment: "updated the PM comment",
};

function CommentThread({ insight }: { insight: Insight }) {
  const refresh = useReviewRefresh(insight.project_id);
  const history = useQuery({ queryKey: ["insight-history", insight.id], queryFn: () => api.review.insightHistory(insight.id) });
  const [text, setText] = useState("");
  const add = useMutation({
    mutationFn: () => api.review.commentOnInsight(insight.id, text.trim()),
    onSuccess: () => {
      setText("");
      void history.refetch();
      refresh();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const entries = useMemo(
    () => (history.data ?? []).filter((h) => h.action === "review_comment" || h.comment || DECISION_TEXT[h.action]),
    [history.data],
  );

  return (
    <section className="space-y-2">
      <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Reviewer comments & activity</h4>
      <form
        className="space-y-1.5"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) add.mutate();
        }}
      >
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && text.trim()) add.mutate();
          }}
          placeholder="Add a comment for other reviewers…"
          rows={2}
          className="resize-none bg-background text-sm"
          aria-label="Reviewer comment"
        />
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-muted-foreground">Ctrl/⌘ + Enter to post</span>
          <Button size="xs" type="submit" disabled={!text.trim() || add.isPending}>
            Comment
          </Button>
        </div>
      </form>
      {history.isPending ? (
        <Skeleton className="h-16 w-full" />
      ) : entries.length ? (
        <ol className="max-h-72 space-y-2 overflow-y-auto">
          {entries.map((h) => (
            <ActivityItem key={h.id} entry={h} />
          ))}
        </ol>
      ) : (
        <p className="text-xs text-muted-foreground">No comments yet.</p>
      )}
    </section>
  );
}

function ActivityItem({ entry: h }: { entry: AuditEntry }) {
  const isComment = h.action === "review_comment";
  return (
    <li className={cn("rounded-lg px-2.5 py-2 text-sm", isComment ? "border bg-background" : "bg-muted/50")}>
      <p className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          <span className="font-medium text-foreground">{h.actor ?? "Someone"}</span>
          {isComment ? " commented" : ` ${DECISION_TEXT[h.action] ?? h.action.replaceAll("_", " ")}`}
        </span>
        <span className="shrink-0">{timeAgo(h.created_at)}</span>
      </p>
      {h.comment ? <p className={cn("mt-0.5 text-pretty", !isComment && "text-xs text-muted-foreground")}>{h.comment}</p> : null}
    </li>
  );
}

function FlagSensitiveDialog({ insight, open, onOpenChange }: { insight: Insight; open: boolean; onOpenChange: (o: boolean) => void }) {
  const refresh = useReviewRefresh(insight.project_id);
  const [tags, setTags] = useState<SensitiveTag[]>([]);
  const [reason, setReason] = useState("");
  const existing = new Set(insight.sensitive_tags);
  const flag = useMutation({
    mutationFn: () => api.review.flagSensitive(insight.id, tags, reason.trim()),
    onSuccess: (r) => {
      refresh();
      toast.success(insight.status === "approved" && r.status === "proposed" ? "Flagged as sensitive and sent back for approval" : "Flagged as sensitive");
      onOpenChange(false);
      setTags([]);
      setReason("");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            flag.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>Flag as sensitive</DialogTitle>
            <DialogDescription>
              Sensitive findings are withheld from reports until someone approves them with an explicit acknowledgement.
              {insight.status === "approved" ? " This insight is approved, so it goes back to review." : ""}
            </DialogDescription>
          </DialogHeader>
          <fieldset className="grid gap-2">
            <legend className="mb-1 text-sm font-medium">Topic</legend>
            {(Object.keys(TAG_LABEL) as SensitiveTag[]).map((t) => (
              <label key={t} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-[var(--primary)]"
                  checked={existing.has(t) || tags.includes(t)}
                  disabled={existing.has(t)}
                  onChange={(e) => setTags((prev) => (e.target.checked ? [...prev, t] : prev.filter((x) => x !== t)))}
                />
                {TAG_LABEL[t]}
                {existing.has(t) ? <span className="text-xs text-muted-foreground">already flagged</span> : null}
              </label>
            ))}
          </fieldset>
          <div className="grid gap-2">
            <Label htmlFor="flag-reason">Why is it sensitive?</Label>
            <Textarea id="flag-reason" rows={2} value={reason} onChange={(e) => setReason(e.target.value)} required minLength={3} />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!tags.length || reason.trim().length < 3 || flag.isPending}>
              <ShieldAlert /> Flag
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
