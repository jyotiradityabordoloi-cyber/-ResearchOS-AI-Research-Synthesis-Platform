"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  ArrowRight,
  BookOpenText,
  Check,
  ClipboardCheck,
  FileText,
  FolderKanban,
  FolderPlus,
  Layers,
  Lightbulb,
  MessagesSquare,
  Scale,
  ShieldAlert,
  Sparkle,
  Sparkles,
  Upload,
} from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, type DashboardStats, type ReviewQueueItem, type RunItem } from "@/lib/api";
import { formatDay, percent, timeAgo } from "@/lib/format";
import { useChartAnimation } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, PageHeader, Panel, ProjectStatusBadge, StatCard } from "@/components/common";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { StatusBadge } from "@/components/review/review-controls";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StageBar } from "@/components/stage-bar";
import { nextStep, STAGES, stageFlags } from "@/lib/progress";

const TOOLTIP_STYLE = {
  borderRadius: 8,
  border: "1px solid var(--border)",
  background: "var(--popover)",
  fontSize: 12,
  boxShadow: "0 4px 12px rgb(0 0 0 / 0.06)",
};

const PRIORITY_TONE: Record<string, string> = {
  high: "bg-rose-50 text-rose-700",
  medium: "bg-amber-50 text-amber-800",
  low: "bg-muted text-muted-foreground",
};

export function DashboardView() {
  const { data, error, isPending, refetch } = useQuery({
    queryKey: ["dashboard"],
    queryFn: api.dashboard,
    // Keep the command centre live while a synthesis run is in flight.
    refetchInterval: (q) => (q.state.data?.recent_runs.some((r) => r.status === "running") ? 4000 : false),
  });

  const pending = data?.pending_reviews ?? 0;
  const description = data
    ? data.total_projects === 0
      ? "Start a project to collect interviews and synthesise them into evidence-backed themes."
      : `${data.total_projects} project${data.total_projects === 1 ? "" : "s"} · ${
          pending ? `${pending} finding${pending === 1 ? "" : "s"} awaiting human review` : "everything reviewed"
        }`
    : "Where your research stands across every project.";

  return (
    <div className="space-y-6">
      <PageHeader title="Research overview" description={description} actions={<CreateProjectDialog />} />

      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Research projects"
          value={data?.total_projects}
          hint={data ? statusHint(data) : undefined}
          icon={FolderKanban}
          loading={isPending}
          href="/projects"
        />
        <StatCard
          label="Interviews"
          value={data?.total_interviews}
          hint={
            data ? (
              <>
                {data.valid_interviews} valid
                {data.total_interviews > data.valid_interviews ? (
                  <span className="text-amber-700"> · {data.total_interviews - data.valid_interviews} need fixes</span>
                ) : null}
              </>
            ) : undefined
          }
          icon={MessagesSquare}
          loading={isPending}
          href="/interviews"
        />
        <StatCard
          label="Themes identified"
          value={data?.themes_identified}
          hint={data ? `${data.review_counts.approved} findings approved` : undefined}
          icon={Layers}
          loading={isPending}
          href="/repository"
        />
        <StatCard
          label="Pending human reviews"
          value={data?.pending_reviews}
          hint={
            data?.sensitive_pending ? (
              <span className="text-rose-700">{data.sensitive_pending} sensitive, need sign-off</span>
            ) : data ? (
              "AI proposals wait for a person"
            ) : undefined
          }
          icon={ClipboardCheck}
          loading={isPending}
          href="/insights?status=proposed"
          attention={pending > 0}
        />
      </div>

      {data && data.total_projects === 0 ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <EmptyState
            className="bg-background lg:col-span-2"
            icon={FolderKanban}
            title="No research projects yet"
            description="Create a project, add your interview notes, and ResearchOS will synthesise them into themes you can trace back to every quote."
            action={<CreateProjectDialog />}
          />
          <QuickActions data={data} />
        </div>
      ) : (
        // Two independent columns, so a tall panel never stretches its neighbour.
        // Below xl the sidebar leaves too little room for a side column, so it stacks
        // underneath as a two-up grid instead.
        <div className="grid items-start gap-6 xl:grid-cols-3">
          <div className="min-w-0 space-y-6 xl:col-span-2">
            <InterviewActivity data={data} loading={isPending} />
            <ProjectProgressPanel data={data} loading={isPending} />
            <TopFindings data={data} loading={isPending} />
          </div>
          <div className="grid min-w-0 content-start items-start gap-6 md:grid-cols-2 xl:grid-cols-1">
            <ReviewQueue data={data} loading={isPending} />
            <QuickActions data={data} />
            <SynthesisRuns runs={data?.recent_runs} loading={isPending} />
            <RecentActivity data={data} loading={isPending} />
          </div>
        </div>
      )}
    </div>
  );
}

function statusHint(d: DashboardStats) {
  const s = d.projects_by_status;
  const parts = [
    s.in_review ? `${s.in_review} in review` : null,
    s.collecting ? `${s.collecting} collecting` : null,
    s.completed ? `${s.completed} completed` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Drafts only";
}

function ListSkeleton({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-3", className)} aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Interview activity: two views of the same interviews, both click-through.
// ---------------------------------------------------------------------------

type ActivityMode = "time" | "project";

function InterviewActivity({ data, loading, className }: { data?: DashboardStats; loading: boolean; className?: string }) {
  const router = useRouter();
  const motion = useChartAnimation();
  const [mode, setMode] = useState<ActivityMode>("time");

  const days = data?.interview_activity ?? [];
  const recent = days.reduce((n, d) => n + d.valid + d.needs_fixes, 0);
  const timeData = days.map((d) => ({ ...d, label: formatDay(d.day), Valid: d.valid, "Needs fixes": d.needs_fixes }));
  const projectData =
    data?.per_project.map((p) => ({
      id: p.project_id,
      label: p.project_name.length > 18 ? `${p.project_name.slice(0, 17)}…` : p.project_name,
      Valid: p.valid_interviews,
      "Needs fixes": p.interviews - p.valid_interviews,
    })) ?? [];

  const open = (entry: unknown, status: "valid" | "invalid") => {
    const row = (entry as { payload?: { day?: string; id?: string } }).payload;
    if (!row) return;
    const params = new URLSearchParams({ status });
    if (mode === "time" && row.day) params.set("created_on", row.day);
    if (mode === "project" && row.id) params.set("project_id", row.id);
    router.push(`/interviews?${params}`);
  };

  return (
    <Panel
      className={className}
      title="Interview activity"
      description={
        mode === "time"
          ? `${recent} interview${recent === 1 ? "" : "s"} added in the last 30 days. Click a bar to open them.`
          : "Valid interviews are ready for synthesis. Click a bar to open them."
      }
      action={
        <div className="inline-flex rounded-lg border bg-muted/50 p-0.5" role="radiogroup" aria-label="Chart view">
          {(
            [
              ["time", "Last 30 days"],
              ["project", "By project"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={mode === value}
              onClick={() => setMode(value)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs transition-[color,background-color,box-shadow,transform] duration-150 ease-out active:scale-[0.97]",
                mode === value ? "bg-background font-medium shadow-xs" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      }
      bodyClassName="h-72 pt-4"
    >
      {loading ? (
        <Skeleton className="h-full w-full" />
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            key={mode}
            data={mode === "time" ? timeData : projectData}
            margin={{ left: -20, right: 4, top: 4, bottom: 0 }}
            barCategoryGap={mode === "time" ? 3 : "28%"}
          >
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="label"
              tickLine={false}
              axisLine={false}
              fontSize={11}
              interval={mode === "time" ? 6 : 0}
              tick={{ fill: "var(--muted-foreground)" }}
            />
            <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={11} tick={{ fill: "var(--muted-foreground)" }} />
            <Tooltip cursor={{ fill: "var(--muted)" }} contentStyle={TOOLTIP_STYLE} />
            <Bar
              dataKey="Valid"
              stackId="a"
              fill="var(--chart-1)"
              maxBarSize={mode === "time" ? 18 : 44}
              className="cursor-pointer"
              onClick={(e) => open(e, "valid")}
              {...motion}
            />
            <Bar
              dataKey="Needs fixes"
              stackId="a"
              fill="var(--chart-3)"
              radius={[3, 3, 0, 0]}
              maxBarSize={mode === "time" ? 18 : 44}
              className="cursor-pointer"
              onClick={(e) => open(e, "invalid")}
              {...motion}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Review queue: what a person has to look at next.
// ---------------------------------------------------------------------------

function ReviewQueue({ data, loading }: { data?: DashboardStats; loading: boolean }) {
  const counts = data?.review_counts;
  const total = counts ? counts.approved + counts.rejected + counts.proposed : 0;
  return (
    <Panel
      title="Needs your review"
      description="AI proposals stay drafts until someone approves them."
      action={
        data?.pending_reviews ? (
          <Badge variant="secondary" className="bg-amber-50 text-amber-800 tabular-nums">
            {data.pending_reviews}
          </Badge>
        ) : null
      }
      bodyClassName="flex flex-col gap-4"
    >
      {loading ? (
        <ListSkeleton rows={5} />
      ) : !data || total === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Nothing to review until a project is synthesised.</p>
      ) : (
        <>
          <div className="space-y-2">
            <div className="flex h-2 overflow-hidden rounded-full bg-muted">
              <Segment value={counts!.approved} total={total} className="bg-emerald-500" />
              <Segment value={counts!.rejected} total={total} className="bg-muted-foreground/40" />
              <Segment value={counts!.proposed} total={total} className="bg-amber-400" />
            </div>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <Legend className="bg-emerald-500" label={`${counts!.approved} approved`} />
              <Legend className="bg-muted-foreground/40" label={`${counts!.rejected} rejected`} />
              <Legend className="bg-amber-400" label={`${counts!.proposed} awaiting`} />
            </div>
          </div>

          {data.review_queue.length ? (
            <ul className="-mx-2 space-y-0.5">
              {data.review_queue.slice(0, 6).map((item, i) => (
                <QueueRow key={item.id} item={item} index={i} />
              ))}
            </ul>
          ) : (
            <p className="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800">
              <Check className="size-4" /> Every finding has been reviewed.
            </p>
          )}

          {data.pending_reviews > 0 ? (
            <Button asChild variant="outline" size="sm" className="mt-auto w-full">
              <Link href="/insights?status=proposed">
                Review all pending <ArrowRight />
              </Link>
            </Button>
          ) : null}
        </>
      )}
    </Panel>
  );
}

function Segment({ value, total, className }: { value: number; total: number; className: string }) {
  if (!value) return null;
  return <div className={cn("bar-fill h-full", className)} style={{ width: `${(value / total) * 100}%` }} />;
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 tabular-nums">
      <span className={cn("size-2 rounded-full", className)} />
      {label}
    </span>
  );
}

function QueueRow({ item, index }: { item: ReviewQueueItem; index: number }) {
  const Icon = item.kind === "theme" ? Layers : Lightbulb;
  return (
    <li className="enter" style={{ "--i": index } as React.CSSProperties}>
      <Link
        href={
          item.kind === "theme"
            ? `/projects/${item.project_id}?tab=themes&theme=${item.id}`
            : `/projects/${item.project_id}?tab=insights&insight=${item.id}`
        }
        className="group flex items-start gap-3 rounded-lg px-2 py-2 transition-colors duration-150 hover:bg-muted/70"
      >
        <span
          className={cn(
            "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md",
            item.requires_approval ? "bg-rose-50 text-rose-700" : "bg-muted text-muted-foreground",
          )}
        >
          {item.requires_approval ? <ShieldAlert className="size-3.5" /> : <Icon className="size-3.5" />}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">
            <span className="mr-1.5 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
              {item.kind === "theme" ? `Theme ${item.code ?? ""}` : "Insight"}
            </span>
            {item.title}
          </p>
          <p className="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
            <span className="truncate">{item.project_name}</span>
            <span>·</span>
            <span className="shrink-0 tabular-nums">sev {item.severity}/5</span>
            {item.is_outlier ? <Sparkle className="size-3 shrink-0 text-violet-600" aria-label="Single participant" /> : null}
            {item.has_contradictions ? <Scale className="size-3 shrink-0 text-amber-600" aria-label="Has contradicting evidence" /> : null}
          </p>
        </div>
        <ArrowRight className="mt-1 size-3.5 shrink-0 text-muted-foreground opacity-0 transition-opacity duration-150 group-hover:opacity-100" />
      </Link>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Project progress: where each project is in collect -> report.
// ---------------------------------------------------------------------------

function ProjectProgressPanel({ data, loading, className }: { data?: DashboardStats; loading: boolean; className?: string }) {
  return (
    <Panel
      className={className}
      title="Project progress"
      description="Each project moves from interviews to an approved report."
      action={
        <Button asChild variant="ghost" size="sm" className="-my-1 text-muted-foreground">
          <Link href="/projects">
            All projects <ArrowRight />
          </Link>
        </Button>
      }
      bodyClassName="p-0"
    >
      {loading ? (
        <ListSkeleton rows={3} className="p-5" />
      ) : (
        <ul className="divide-y">
          {data?.project_progress.map((p, i) => {
            const flags = stageFlags(p);
            const current = flags.indexOf(false);
            return (
              <li key={p.project_id} className="enter" style={{ "--i": i } as React.CSSProperties}>
                <Link
                  href={`/projects/${p.project_id}`}
                  className="group grid gap-3 px-5 py-4 transition-colors duration-150 hover:bg-muted/40 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] sm:items-center"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate font-medium group-hover:text-primary">{p.project_name}</p>
                      <ProjectStatusBadge status={p.status} />
                    </div>
                    <p className="text-xs text-muted-foreground tabular-nums">
                      {p.participants} participants · {p.themes} themes
                      {p.review_total ? ` · ${p.review_done}/${p.review_total} reviewed` : ""} · {timeAgo(p.last_activity_at)}
                    </p>
                  </div>
                  <div className="space-y-1.5">
                    <StageBar flags={flags} />
                    <p className="flex justify-between gap-2 text-xs">
                      <span className={cn("truncate", p.synthesis_status === "failed" ? "text-destructive" : "text-muted-foreground")}>
                        {nextStep(p, flags)}
                      </span>
                      <span className="shrink-0 text-muted-foreground tabular-nums">
                        {current === -1 ? "Done" : STAGES[current]}
                      </span>
                    </p>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Quick actions
// ---------------------------------------------------------------------------

function ActionTile({
  icon: Icon,
  label,
  hint,
  href,
  ...rest
}: { icon: LucideIcon; label: string; hint: string; href?: string } & React.ComponentProps<"button">) {
  const inner = (
    <>
      <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/8 text-primary transition-colors duration-150 group-hover:bg-primary group-hover:text-primary-foreground">
        <Icon className="size-4" />
      </span>
      <span className="min-w-0 text-left">
        <span className="block text-sm font-medium">{label}</span>
        <span className="block truncate text-xs text-muted-foreground">{hint}</span>
      </span>
    </>
  );
  const cls =
    "group flex w-full items-center gap-3 rounded-lg border bg-background px-3 py-2.5 transition-[border-color,box-shadow,transform] duration-150 ease-out hover:border-primary/30 hover:shadow-sm active:scale-[0.98]";
  return href ? (
    <Link href={href} className={cls}>
      {inner}
    </Link>
  ) : (
    <button type="button" {...rest} className={cls}>
      {inner}
    </button>
  );
}

function QuickActions({ data }: { data?: DashboardStats }) {
  const latest = data?.project_progress[0];
  return (
    <Panel title="Quick actions" bodyClassName="grid gap-2 p-3">
      <CreateProjectDialog trigger={<ActionTile icon={FolderPlus} label="New project" hint="Set objectives and segments" />} />
      {latest ? (
        <ActionTile
          icon={Upload}
          label="Import interviews"
          hint={`Into ${latest.project_name}`}
          href={`/projects/${latest.project_id}/import`}
        />
      ) : null}
      <ActionTile icon={BookOpenText} label="Search the repository" hint="Keyword or semantic search" href="/repository" />
      {latest && latest.synthesis_status === "completed" ? (
        <ActionTile
          icon={FileText}
          label="Build a report"
          hint={`From ${latest.project_name}`}
          href={`/projects/${latest.project_id}/reports/new`}
        />
      ) : null}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// AI synthesis runs
// ---------------------------------------------------------------------------

const RUN_DOT: Record<string, string> = {
  completed: "bg-emerald-500",
  running: "bg-sky-500 animate-pulse",
  failed: "bg-destructive",
};

function duration(run: RunItem) {
  if (!run.finished_at) return null;
  const s = Math.max(1, Math.round((new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000));
  return s < 90 ? `${s}s` : `${Math.round(s / 60)} min`;
}

function SynthesisRuns({ runs, loading }: { runs?: RunItem[]; loading: boolean }) {
  return (
    <Panel title="AI synthesis" description="Latest pipeline runs and the model that ran them.">
      {loading ? (
        <ListSkeleton rows={3} />
      ) : runs && runs.length ? (
        <ol className="space-y-3.5">
          {runs.map((r) => (
            <li key={r.id}>
              <Link href={`/projects/${r.project_id}?tab=themes`} className="group flex gap-3 text-sm">
                <span className="mt-1.5 flex size-2 shrink-0">
                  <span className={cn("size-2 rounded-full", RUN_DOT[r.status] ?? "bg-muted-foreground")} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium group-hover:text-primary">{r.project_name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {r.status === "running"
                      ? `Running · ${r.stage.replaceAll("_", " ")}`
                      : r.status === "failed"
                        ? `Failed${r.error ? ` · ${r.error}` : ""}`
                        : `${r.themes ?? 0} themes from ${r.participants ?? 0} participants${duration(r) ? ` · ${duration(r)}` : ""}`}
                  </p>
                  <p className="truncate text-xs text-muted-foreground/80">
                    {r.provider} · {r.model} · {timeAgo(r.finished_at ?? r.started_at)}
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ol>
      ) : (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Sparkles className="size-4" /> No synthesis has run yet.
        </p>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Top findings: highest-priority insights, with their dimensions kept apart.
// ---------------------------------------------------------------------------

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <span className="tabular-nums">
      <span className="text-muted-foreground/80">{label}</span> <span className="font-medium text-foreground">{value}</span>
    </span>
  );
}

function TopFindings({ data, loading, className }: { data?: DashboardStats; loading: boolean; className?: string }) {
  return (
    <Panel
      className={className}
      title="Top research findings"
      description="Ranked by priority. Frequency, severity and strategic relevance are shown separately."
      action={
        <Button asChild variant="ghost" size="sm" className="-my-1 text-muted-foreground">
          <Link href="/insights">
            All insights <ArrowRight />
          </Link>
        </Button>
      }
      bodyClassName="p-0"
    >
      {loading ? (
        <ListSkeleton rows={3} className="p-5" />
      ) : data?.top_findings.length ? (
        <ul className="divide-y">
          {data.top_findings.map((f, i) => (
            <li key={f.id} className="enter" style={{ "--i": i } as React.CSSProperties}>
              <Link
                href={`/projects/${f.project_id}?tab=insights&insight=${f.id}`}
                className="group flex flex-col gap-1.5 px-5 py-3.5 transition-colors duration-150 hover:bg-muted/40"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary" className={cn("capitalize", PRIORITY_TONE[f.priority])}>
                    {f.priority}
                  </Badge>
                  {f.theme_code ? <span className="font-mono text-xs text-muted-foreground">{f.theme_code}</span> : null}
                  <p className="min-w-0 flex-1 truncate text-sm font-medium group-hover:text-primary">{f.title}</p>
                  <StatusBadge status={f.status} />
                </div>
                {f.implication ? <p className="line-clamp-2 text-sm text-muted-foreground">{f.implication}</p> : null}
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                  <Metric label="Frequency" value={percent(f.frequency)} />
                  <Metric label="Severity" value={`${f.severity}/5`} />
                  <Metric label="Strategic" value={`${f.strategic_relevance}/5`} />
                  <span className="truncate text-muted-foreground">{f.project_name}</span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-5 py-8 text-center text-sm text-muted-foreground">
          Findings appear here once a project has been synthesised.
        </p>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Recent activity (audit log)
// ---------------------------------------------------------------------------

function RecentActivity({ data, loading }: { data?: DashboardStats; loading: boolean }) {
  return (
    <Panel title="Recent activity" description="Every human and AI action is logged.">
      {loading ? (
        <ListSkeleton rows={5} />
      ) : data && data.recent_activity.length > 0 ? (
        <ol className="relative space-y-4 before:absolute before:top-2 before:bottom-2 before:left-[11px] before:w-px before:bg-border">
          {data.recent_activity.slice(0, 7).map((a, i) => (
            <li key={`${a.kind}-${a.at}-${i}`} className="relative flex gap-3 text-sm">
              <span
                className={cn(
                  "z-10 mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border bg-background",
                  a.kind.startsWith("synthesis") && "border-primary/30 text-primary",
                )}
              >
                {a.kind.startsWith("synthesis") ? <Sparkles className="size-3" /> : <Activity className="size-3 text-muted-foreground" />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">
                  {a.title}
                  {a.detail ? <span className="font-normal text-muted-foreground"> · {a.detail}</span> : null}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {a.project_id ? (
                    <Link href={`/projects/${a.project_id}`} className="hover:text-foreground hover:underline">
                      {a.project_name ?? "Deleted project"}
                    </Link>
                  ) : null}
                  {" · "}
                  {timeAgo(a.at)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-muted-foreground">No activity yet.</p>
      )}
    </Panel>
  );
}
