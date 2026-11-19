"use client";

import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import {
  ArrowRightLeft,
  BadgeCheck,
  ChevronRight,
  CircleHelp,
  Flag,
  MoreHorizontal,
  Pencil,
  Scale,
  Scissors,
  ShieldAlert,
  Sparkle,
  Star,
  User,
  UserPen,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { api, type Evidence, type Theme } from "@/lib/api";
import { percent } from "@/lib/format";
import { cn } from "@/lib/utils";
import { DecisionButtons, StatusBadge, TAG_LABEL, useReviewRefresh } from "@/components/review/review-controls";
import { EditThemeDialog, SplitThemeDialog } from "@/components/review/theme-dialogs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const SOURCE_LABEL: Record<string, string> = {
  verbatim_quote: "verbatim quote",
  pain: "pain notes",
  behavior: "behavior notes",
};

export function ThemeFlags({ theme }: { theme: Theme }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {theme.requires_approval ? (
        <Badge variant="secondary" className="bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300">
          <ShieldAlert /> {theme.status === "approved" ? "Sensitive, signed off" : "Needs approval"}:{" "}
          {theme.sensitive_tags.map((t) => TAG_LABEL[t] ?? t).join(", ")}
        </Badge>
      ) : null}
      {theme.strategic_flag ? (
        <Badge variant="secondary" className="bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-300">
          <Star /> Strategic
        </Badge>
      ) : null}
      {theme.is_outlier ? (
        <Badge variant="secondary" className="bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300">
          <Sparkle /> {theme.severity >= 4 ? "High-impact outlier" : "Single participant"}
        </Badge>
      ) : null}
      {theme.has_contradictions ? (
        <Badge variant="secondary" className="bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
          <Scale /> Contradicting evidence
        </Badge>
      ) : null}
      {theme.is_low_confidence ? (
        <Badge variant="secondary" className="bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
          <CircleHelp /> Low-confidence cluster: review grouping
        </Badge>
      ) : null}
      {theme.evidence_status === "insufficient" ? (
        <Badge variant="destructive">
          <Flag /> Insufficient evidence
        </Badge>
      ) : null}
      {theme.human_edited || theme.origin === "manual" ? (
        <Badge variant="outline">
          <UserPen /> {theme.origin === "manual" ? "Created by PM" : "Edited by PM"}
        </Badge>
      ) : null}
    </div>
  );
}

function EvidenceItem({ e, theme, others }: { e: Evidence; theme: Theme; others: Theme[] }) {
  const refresh = useReviewRefresh(theme.project_id);
  const move = useMutation({
    mutationFn: (targetId: string) => api.review.moveEvidence(e.id, targetId),
    onSuccess: (res) => {
      refresh();
      toast.success(`Moved ${e.participant_id}'s evidence to ${res[1]?.code}`);
    },
    onError: (err: Error) => toast.error(err.message),
  });
  return (
    <li className="group space-y-1">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <User className="size-3" />
        <Link
          href={`/interviews?interview=${e.interview_id}`}
          className="font-medium text-foreground underline-offset-2 hover:text-primary hover:underline"
          title="Open the source interview"
        >
          {e.participant_id}
        </Link>
        {e.source_field ? <span>· from {SOURCE_LABEL[e.source_field] ?? e.source_field}</span> : null}
        {e.quote_verified ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                <BadgeCheck className="size-3" /> verified
              </span>
            </TooltipTrigger>
            <TooltipContent>Found word-for-word in the original interview notes.</TooltipContent>
          </Tooltip>
        ) : null}
        {others.length && theme.status !== "rejected" ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="ml-auto size-6 opacity-60 group-hover:opacity-100"
                aria-label={`Move ${e.participant_id}'s evidence to another theme`}
                disabled={move.isPending}
              >
                <ArrowRightLeft className="size-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="max-w-72">
              <DropdownMenuLabel>Move to theme</DropdownMenuLabel>
              {others.map((o) => (
                <DropdownMenuItem key={o.id} onSelect={() => move.mutate(o.id)}>
                  <span className="font-mono text-xs text-muted-foreground">{o.code}</span>
                  <span className="truncate">{o.name}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
      {e.quote ? (
        <blockquote
          className={cn("border-l-2 pl-3 text-sm", e.stance === "contradicting" ? "border-amber-500" : "border-primary/50")}
        >
          “{e.quote}”
        </blockquote>
      ) : (
        <p className="border-l-2 border-dashed pl-3 text-sm text-muted-foreground">
          No verbatim quote could be verified for this point.
        </p>
      )}
      {e.note && e.note !== e.quote ? (
        <p className="pl-3 text-xs text-muted-foreground">
          {e.stance === "contradicting" ? "Why it contradicts: " : "Pain point: "}
          {e.note}
        </p>
      ) : null}
    </li>
  );
}

export function ThemeCard({
  theme,
  allThemes = [],
  selected = false,
  onSelect,
  index = 0,
}: {
  index?: number;
  theme: Theme;
  allThemes?: Theme[];
  selected?: boolean;
  onSelect?: (checked: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [splitting, setSplitting] = useState(false);
  const refresh = useReviewRefresh(theme.project_id);
  const supporting = theme.evidence.filter((e) => e.stance === "supporting");
  const contradicting = theme.evidence.filter((e) => e.stance === "contradicting");
  const others = allThemes.filter((t) => t.id !== theme.id && t.status !== "rejected");
  const rejected = theme.status === "rejected";

  return (
    <Card
      className={cn(
        "enter gap-0 py-0 shadow-xs transition-[box-shadow,opacity] duration-200",
        selected && "ring-2 ring-primary",
        rejected && "opacity-70",
      )}
      style={{ "--i": index } as React.CSSProperties}
    >
      <div className="space-y-3 px-5 py-4">
        <div className="flex items-start gap-3">
          {onSelect && !rejected ? (
            <input
              type="checkbox"
              className="mt-1 size-4 shrink-0 accent-[var(--primary)]"
              checked={selected}
              onChange={(e) => onSelect(e.target.checked)}
              aria-label={`Select ${theme.code} for merging`}
            />
          ) : null}
          <span className="mt-0.5 rounded-md bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
            {theme.code}
          </span>
          <div className="min-w-0 flex-1 space-y-1">
            <h3 className="font-semibold tracking-tight text-pretty">{theme.name}</h3>
            <p className="text-sm text-muted-foreground text-pretty">{theme.description}</p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <StatusBadge status={theme.status} />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="size-8" aria-label={`More actions for ${theme.code}`}>
                  <MoreHorizontal className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => setEditing(true)} disabled={rejected}>
                  <Pencil /> Edit name & implication
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setSplitting(true)} disabled={rejected || theme.evidence.length < 2}>
                  <Scissors /> Split theme
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center">
          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between text-xs">
              <span className="text-muted-foreground">Participant frequency</span>
              <span className="tabular-nums">
                <span className="font-semibold">{theme.participant_count}</span> of {theme.total_participants} ·{" "}
                {percent(theme.frequency)}
              </span>
            </div>
            <div
              className="h-2 overflow-hidden rounded-full bg-muted"
              role="img"
              aria-label={`${percent(theme.frequency)} of participants`}
            >
              <div className="bar-fill h-full rounded-full bg-primary" style={{ width: `${Math.max(2, theme.frequency * 100)}%` }} />
            </div>
          </div>
          <Metric label="Severity" value={`${theme.severity}/5`} />
          <Metric label="Confidence" value={percent(theme.confidence)} />
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {theme.participant_ids.map((p) => (
            <Badge key={p} variant="outline" className="font-mono text-[11px]">
              {p}
            </Badge>
          ))}
        </div>

        <ThemeFlags theme={theme} />

        {theme.implication ? (
          <p className="rounded-lg bg-muted/50 px-3 py-2 text-sm">
            <span className="font-medium">Suggested implication: </span>
            {theme.implication}
          </p>
        ) : null}

        <DecisionButtons
          status={theme.status}
          sensitiveTags={theme.sensitive_tags}
          requiresApproval={theme.requires_approval}
          onDecide={async (payload) => {
            const r = await api.review.reviewTheme(theme.id, payload);
            refresh();
            return r;
          }}
        />
      </div>

      <div className="border-t">
        <Button
          variant="ghost"
          className="h-10 w-full justify-start rounded-none rounded-b-xl px-5 text-sm"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          <ChevronRight className={cn("size-4 transition-transform duration-200 ease-out-strong", open && "rotate-90")} />
          Evidence · {supporting.length} supporting
          {contradicting.length ? ` · ${contradicting.length} contradicting` : ""}
        </Button>
        {open ? (
          <div className="reveal grid gap-6 px-5 pb-5 lg:grid-cols-2">
            <section className="space-y-3">
              <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Supporting</h4>
              <ul className="space-y-4">
                {supporting.map((e) => (
                  <EvidenceItem key={e.id} e={e} theme={theme} others={others} />
                ))}
              </ul>
            </section>
            <section className="space-y-3">
              <h4 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Contradicting</h4>
              {contradicting.length ? (
                <ul className="space-y-4">
                  {contradicting.map((e) => (
                    <EvidenceItem key={e.id} e={e} theme={theme} others={others} />
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">No opposing observations found.</p>
              )}
            </section>
          </div>
        ) : null}
      </div>

      <EditThemeDialog theme={theme} open={editing} onOpenChange={setEditing} />
      <SplitThemeDialog theme={theme} open={splitting} onOpenChange={setSplitting} />
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-right sm:min-w-20">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-semibold tabular-nums">{value}</div>
    </div>
  );
}
