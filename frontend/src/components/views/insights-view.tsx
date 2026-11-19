"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useUrlState } from "@/lib/url-state";
import { ErrorState, PageHeader } from "@/components/common";
import { InsightReviewPanel } from "@/components/insights/insights-board";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const ALL = "all";

/** Cross-project insight review. Priority, status and search filters live inside the panel. */
export function InsightsView() {
  const [projectId, setProjectId] = useUrlState("project_id", ALL);
  const projects = useQuery({ queryKey: ["projects", {}], queryFn: () => api.projects.list() });
  const params = { project_id: projectId === ALL ? undefined : projectId };
  const insights = useQuery({ queryKey: ["all-insights", params], queryFn: () => api.review.allInsights(params) });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Insight review"
        description="Approve, reject and refine findings across projects. Every decision is logged, and sensitive findings need an explicit sign-off."
        actions={
          <Select value={projectId} onValueChange={setProjectId}>
            <SelectTrigger className="bg-background sm:w-60" aria-label="Filter by project">
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
        }
      />
      {insights.error ? <ErrorState error={insights.error} onRetry={() => insights.refetch()} /> : null}
      {insights.isPending ? (
        <div className="space-y-2.5">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-36 w-full rounded-xl" />
          ))}
        </div>
      ) : insights.data ? (
        <InsightReviewPanel insights={insights.data} showProject={projectId === ALL} />
      ) : null}
    </div>
  );
}
