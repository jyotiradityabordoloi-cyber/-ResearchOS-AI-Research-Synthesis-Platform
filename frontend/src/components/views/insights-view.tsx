"use client";

import { useQuery } from "@tanstack/react-query";
import { Lightbulb, Search } from "lucide-react";
import { useDeferredValue, useState } from "react";

import { api } from "@/lib/api";
import { EmptyState, ErrorState, PageHeader } from "@/components/common";
import { InsightsTable } from "@/components/insights/insights-board";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const ALL = "all";

export function InsightsView() {
  const [q, setQ] = useState("");
  const [projectId, setProjectId] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const deferred = useDeferredValue(q.trim());
  const projects = useQuery({ queryKey: ["projects", {}], queryFn: () => api.projects.list() });
  const params = {
    q: deferred || undefined,
    project_id: projectId === ALL ? undefined : projectId,
    status: status === ALL ? undefined : status,
  };
  const insights = useQuery({ queryKey: ["all-insights", params], queryFn: () => api.review.allInsights(params) });
  const filtered = Boolean(deferred || projectId !== ALL || status !== ALL);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Insights"
        description="Prioritised findings across all projects. Frequency, severity, strategic relevance and confidence are kept separate."
      />
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1 sm:max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search insights"
            className="bg-background pl-9"
            aria-label="Search insights"
          />
        </div>
        <Select value={projectId} onValueChange={setProjectId}>
          <SelectTrigger className="bg-background sm:w-56" aria-label="Filter by project">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All projects</SelectItem>
            {projects.data?.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="bg-background sm:w-44" aria-label="Filter by review status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Any status</SelectItem>
            <SelectItem value="proposed">Awaiting review</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {insights.error ? <ErrorState error={insights.error} onRetry={() => insights.refetch()} /> : null}
      {insights.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : insights.data && insights.data.length ? (
        <InsightsTable insights={insights.data} showProject />
      ) : (
        <EmptyState
          icon={Lightbulb}
          title={filtered ? "No insights match these filters" : "No insights yet"}
          description={filtered ? undefined : "Run synthesis on a project to generate insights."}
        />
      )}
    </div>
  );
}
