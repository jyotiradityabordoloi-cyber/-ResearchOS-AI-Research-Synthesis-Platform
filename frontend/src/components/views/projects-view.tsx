"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { FolderKanban, Layers, MessagesSquare, Search, Users } from "lucide-react";
import { useDeferredValue, useState } from "react";

import { api, type Project } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { EmptyState, ErrorState, PageHeader, ProjectStatusBadge, SynthesisStatusBadge } from "@/components/common";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";

const MIN_INTERVIEWS = 5;

function ProjectCard({ p, index }: { p: Project; index: number }) {
  const pct = Math.min(100, (p.participant_count / MIN_INTERVIEWS) * 100);
  return (
    <Link
      href={`/projects/${p.id}`}
      className="enter group rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      style={{ "--i": index } as React.CSSProperties}
    >
      <Card className="h-full gap-4 px-5 py-5 shadow-xs transition-[box-shadow,transform] duration-150 ease-out group-hover:shadow-md group-active:scale-[0.99]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <h3 className="truncate font-semibold tracking-tight">{p.name}</h3>
            <p className="line-clamp-2 min-h-10 text-sm text-muted-foreground">
              {p.objectives[0] ?? p.description ?? "No objective set"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <ProjectStatusBadge status={p.status} />
          <SynthesisStatusBadge status={p.synthesis_status} />
        </div>
        <div className="grid grid-cols-3 gap-2 text-sm">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <MessagesSquare className="size-3.5" />
            <span className="tabular-nums text-foreground">{p.interview_count}</span> notes
          </span>
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <Users className="size-3.5" />
            <span className="tabular-nums text-foreground">{p.participant_count}</span> people
          </span>
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <Layers className="size-3.5" />
            <span className="tabular-nums text-foreground">{p.theme_count}</span> themes
          </span>
        </div>
        <div className="mt-auto space-y-1.5">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>
              {p.ready_for_synthesis
                ? "Ready for synthesis"
                : `${p.participant_count}/${MIN_INTERVIEWS} valid participants for synthesis`}
            </span>
            <span>Updated {timeAgo(p.updated_at)}</span>
          </div>
          <Progress value={pct} className="h-1.5" />
        </div>
      </Card>
    </Link>
  );
}

export function ProjectsView() {
  const [q, setQ] = useState("");
  const deferred = useDeferredValue(q.trim());
  const { data, error, isPending, refetch } = useQuery({
    queryKey: ["projects", { q: deferred }],
    queryFn: () => api.projects.list({ q: deferred || undefined }),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Research projects"
        description="Each project groups the interviews, themes and report for one research question."
        actions={<CreateProjectDialog />}
      />
      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search projects"
          className="bg-background pl-9"
          aria-label="Search projects"
        />
      </div>

      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}

      {isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-56 rounded-xl" />
          ))}
        </div>
      ) : data && data.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.map((p, i) => (
            <ProjectCard key={p.id} p={p} index={i} />
          ))}
        </div>
      ) : data ? (
        <EmptyState
          icon={FolderKanban}
          title={deferred ? "No matching projects" : "No research projects yet"}
          description={deferred ? "Try a different search." : "Create your first project to start adding interviews."}
          action={deferred ? undefined : <CreateProjectDialog />}
        />
      ) : null}
    </div>
  );
}
