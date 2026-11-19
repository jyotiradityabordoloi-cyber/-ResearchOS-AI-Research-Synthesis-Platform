"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  ArrowUpDown,
  ClipboardCheck,
  FileText,
  FolderKanban,
  Layers,
  MessagesSquare,
  Search,
  Upload,
  Users,
  X,
} from "lucide-react";
import { useDeferredValue, useMemo } from "react";

import { api, type Project } from "@/lib/api";
import { PROJECT_STATUS_LABEL, timeAgo } from "@/lib/format";
import { nextStep, STAGES, stageFlags } from "@/lib/progress";
import { useUrlState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, PageHeader, ProjectStatusBadge, SynthesisStatusBadge } from "@/components/common";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { StageBar } from "@/components/stage-bar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const ALL = "all";
const STATUSES = ["draft", "collecting", "in_review", "completed"] as const;

const SORTS: Record<string, { label: string; compare: (a: Project, b: Project) => number }> = {
  activity: { label: "Recent activity", compare: (a, b) => activityOf(b) - activityOf(a) },
  pending: { label: "Most to review", compare: (a, b) => b.pending_review_count - a.pending_review_count || activityOf(b) - activityOf(a) },
  interviews: { label: "Most interviews", compare: (a, b) => b.interview_count - a.interview_count },
  name: { label: "Name", compare: (a, b) => a.name.localeCompare(b.name) },
};

function activityOf(p: Project) {
  return new Date(p.last_activity_at ?? p.updated_at).getTime();
}

function progressOf(p: Project) {
  return {
    interviews: p.interview_count,
    participants: p.participant_count,
    min_participants: p.min_participants,
    synthesis_status: p.synthesis_status,
    review_total: p.review_total,
    review_done: p.review_done,
    reports: p.report_count,
  };
}

export function ProjectsView() {
  const [q, setQ] = useUrlState("q", "");
  const [status, setStatus] = useUrlState("status", ALL);
  const [synthesis, setSynthesis] = useUrlState("synthesis", ALL);
  const [sort, setSort] = useUrlState("sort", "activity");
  const deferred = useDeferredValue(q.trim().toLowerCase());

  // One request; filtering is client side so every filter can show live counts.
  const { data, error, isPending, refetch } = useQuery({ queryKey: ["projects", {}], queryFn: () => api.projects.list() });

  const searched = useMemo(
    () =>
      (data ?? []).filter(
        (p) =>
          !deferred ||
          [p.name, p.description, ...p.objectives, ...p.target_segments].some((t) => t.toLowerCase().includes(deferred)),
      ),
    [data, deferred],
  );
  const visible = useMemo(
    () =>
      searched
        .filter((p) => status === ALL || p.status === status)
        .filter((p) => synthesis === ALL || p.synthesis_status === synthesis)
        .sort((SORTS[sort] ?? SORTS.activity).compare),
    [searched, status, synthesis, sort],
  );
  const filtered = Boolean(deferred || status !== ALL || synthesis !== ALL);
  const clear = () => {
    setQ("");
    setStatus(ALL);
    setSynthesis(ALL);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Research projects"
        description="Each project groups the interviews, themes and report for one research question."
        actions={<CreateProjectDialog />}
      />

      <div className="space-y-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <div className="relative flex-1 md:max-w-sm">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search names, objectives, segments"
              className="bg-background pl-9"
              aria-label="Search projects"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2 md:ml-auto">
            <Select value={synthesis} onValueChange={setSynthesis}>
              <SelectTrigger className="w-44 bg-background" aria-label="Filter by synthesis status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Any synthesis</SelectItem>
                <SelectItem value="completed">Synthesised</SelectItem>
                <SelectItem value="not_started">Not synthesised</SelectItem>
                <SelectItem value="running">Synthesising</SelectItem>
                <SelectItem value="failed">Synthesis failed</SelectItem>
              </SelectContent>
            </Select>
            <Select value={sort} onValueChange={setSort}>
              <SelectTrigger className="w-44 bg-background" aria-label="Sort projects">
                <ArrowUpDown className="size-3.5 text-muted-foreground" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(SORTS).map(([value, s]) => (
                  <SelectItem key={value} value={value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5" role="radiogroup" aria-label="Filter by project status">
          {[ALL, ...STATUSES].map((s) => {
            const count = s === ALL ? searched.length : searched.filter((p) => p.status === s).length;
            const active = status === s;
            return (
              <button
                key={s}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setStatus(s)}
                className={cn(
                  "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm transition-[color,background-color,border-color,transform] duration-150 ease-out active:scale-[0.97]",
                  active
                    ? "border-primary/30 bg-primary/8 font-medium text-primary"
                    : "bg-background text-muted-foreground hover:border-foreground/20 hover:text-foreground",
                )}
              >
                {s === ALL ? "All" : PROJECT_STATUS_LABEL[s]}
                <span className={cn("text-xs tabular-nums", active ? "text-primary/70" : "text-muted-foreground/70")}>
                  {data ? count : "–"}
                </span>
              </button>
            );
          })}
          {filtered ? (
            <Button variant="ghost" size="sm" className="h-8 text-muted-foreground" onClick={clear}>
              <X /> Clear filters
            </Button>
          ) : null}
        </div>
      </div>

      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}

      {isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-72 rounded-xl" />
          ))}
        </div>
      ) : visible.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visible.map((p, i) => (
            <ProjectCard key={p.id} p={p} index={i} />
          ))}
        </div>
      ) : data ? (
        <EmptyState
          icon={FolderKanban}
          title={filtered ? "No projects match these filters" : "No research projects yet"}
          description={filtered ? "Try a different search or status." : "Create your first project to start adding interviews."}
          action={
            filtered ? (
              <Button variant="outline" size="sm" onClick={clear}>
                Clear filters
              </Button>
            ) : (
              <CreateProjectDialog />
            )
          }
        />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Card. The title link stretches over the whole card (`after:inset-0`) so the
// card is one big target, while the hover actions stay separate, valid links.
// ---------------------------------------------------------------------------

function ProjectCard({ p, index }: { p: Project; index: number }) {
  const progress = progressOf(p);
  const flags = stageFlags(progress);
  const current = flags.indexOf(false);
  const readiness = Math.min(100, (p.participant_count / Math.max(1, p.min_participants)) * 100);

  return (
    <Card
      className="enter group relative h-full gap-4 px-5 py-5 shadow-xs transition-[box-shadow,border-color,transform] duration-150 ease-out focus-within:ring-2 focus-within:ring-ring hover:border-primary/25 hover:shadow-md has-[a.card-link:active]:scale-[0.99]"
      style={{ "--i": index } as React.CSSProperties}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h3 className="truncate font-semibold tracking-tight">
            <Link
              href={`/projects/${p.id}`}
              className="card-link outline-none after:absolute after:inset-0 after:rounded-xl group-hover:text-primary"
            >
              {p.name}
            </Link>
          </h3>
          <p className="line-clamp-2 min-h-10 text-sm text-muted-foreground">
            {p.objectives[0] || p.description || "No objective set yet."}
          </p>
        </div>
        <ProjectStatusBadge status={p.status} />
      </div>

      {p.target_segments.length ? (
        <div className="-mt-1 flex flex-wrap gap-1">
          {p.target_segments.slice(0, 3).map((s) => (
            <Badge key={s} variant="outline" className="font-normal text-muted-foreground">
              {s}
            </Badge>
          ))}
          {p.target_segments.length > 3 ? (
            <Badge variant="outline" className="font-normal text-muted-foreground">
              +{p.target_segments.length - 3}
            </Badge>
          ) : null}
        </div>
      ) : null}

      <dl className="grid grid-cols-4 gap-2 rounded-lg bg-muted/40 px-3 py-2.5 text-center">
        <Stat icon={MessagesSquare} label="Notes" value={p.interview_count} warn={p.invalid_interview_count > 0} />
        <Stat icon={Users} label="People" value={p.participant_count} />
        <Stat icon={Layers} label="Themes" value={p.theme_count} />
        <Stat icon={ClipboardCheck} label="To review" value={p.pending_review_count} attention={p.pending_review_count > 0} />
      </dl>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">
            Interview readiness{" "}
            <span className="font-medium text-foreground tabular-nums">
              {p.participant_count}/{p.min_participants}
            </span>{" "}
            valid participants
          </span>
          {p.invalid_interview_count > 0 ? (
            <span className="flex items-center gap-1 text-amber-700">
              <AlertTriangle className="size-3" /> {p.invalid_interview_count} need fixes
            </span>
          ) : null}
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-muted">
          <div
            className={cn("bar-fill h-full rounded-full", p.ready_for_synthesis ? "bg-emerald-500" : "bg-amber-400")}
            style={{ width: `${Math.max(readiness, 2)}%` }}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <StageBar flags={flags} className="relative z-10" />
        <p className="flex justify-between gap-2 text-xs">
          <span className={cn("truncate", p.synthesis_status === "failed" ? "text-destructive" : "text-muted-foreground")}>
            {nextStep(progress, flags)}
          </span>
          <span className="shrink-0 text-muted-foreground">{current === -1 ? "Done" : STAGES[current]}</span>
        </p>
      </div>

      <div className="relative mt-auto flex items-center justify-between gap-2 border-t pt-3">
        <div className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
          <SynthesisStatusBadge status={p.synthesis_status} />
          <span className="truncate">Active {timeAgo(p.last_activity_at ?? p.updated_at)}</span>
        </div>
        {/* Overlays the footer on hover/focus so it never steals width from the text. */}
        <div className="absolute right-0 bottom-0 z-10 flex gap-0.5 rounded-md bg-card pl-2 opacity-0 transition-opacity duration-150 group-focus-within:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100">
          <QuickAction href={`/projects/${p.id}/import`} icon={Upload} label="Import interviews" />
          <QuickAction href={`/interviews?project_id=${p.id}`} icon={MessagesSquare} label="Explore interviews" />
          {p.theme_count ? <QuickAction href={`/projects/${p.id}?tab=themes`} icon={Layers} label="Review themes" /> : null}
          {p.synthesis_status === "completed" ? (
            <QuickAction href={`/projects/${p.id}?tab=reports`} icon={FileText} label="Reports" />
          ) : null}
        </div>
      </div>
    </Card>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  warn,
  attention,
}: {
  icon: LucideIcon;
  label: string;
  value: number;
  warn?: boolean;
  attention?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="flex items-center justify-center gap-1 text-[11px] text-muted-foreground">
        <Icon className="size-3" />
        {label}
      </dt>
      <dd
        className={cn(
          "text-lg font-semibold tabular-nums",
          attention && "text-amber-700",
          warn && "underline decoration-amber-400 decoration-2 underline-offset-4",
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function QuickAction({ href, icon: Icon, label }: { href: string; icon: LucideIcon; label: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button asChild variant="ghost" size="icon" className="size-7 text-muted-foreground hover:text-primary">
          <Link href={href} aria-label={label}>
            <Icon className="size-3.5" />
          </Link>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
