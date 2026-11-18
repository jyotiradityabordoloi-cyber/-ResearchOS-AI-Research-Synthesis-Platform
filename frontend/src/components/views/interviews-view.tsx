"use client";

import { useQuery } from "@tanstack/react-query";
import { MessagesSquare, Search } from "lucide-react";
import { useDeferredValue, useState } from "react";

import { api } from "@/lib/api";
import { EmptyState, ErrorState, PageHeader } from "@/components/common";
import { InterviewTable } from "@/components/interviews/interview-table";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const ALL = "all";

export function InterviewsView() {
  const [q, setQ] = useState("");
  const [projectId, setProjectId] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const deferred = useDeferredValue(q.trim());

  const projects = useQuery({ queryKey: ["projects", {}], queryFn: () => api.projects.list() });
  const params = {
    q: deferred || undefined,
    project_id: projectId === ALL ? undefined : projectId,
    validation_status: status === ALL ? undefined : status,
  };
  const { data, error, isPending, refetch } = useQuery({
    queryKey: ["interviews", params],
    queryFn: () => api.interviews.list(params),
  });
  const filtered = Boolean(deferred || projectId !== ALL || status !== ALL);

  return (
    <div className="space-y-6">
      <PageHeader title="Interviews" description="Every interview across all research projects, with its validation status." />

      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1 sm:max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search participant, role, pain, quote…"
            className="bg-background pl-9"
            aria-label="Search interviews"
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
          <SelectTrigger className="bg-background sm:w-44" aria-label="Filter by validation status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Any status</SelectItem>
            <SelectItem value="valid">Valid</SelectItem>
            <SelectItem value="invalid">Needs fixes</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : data && data.length ? (
        <InterviewTable interviews={data} showProject />
      ) : data ? (
        <EmptyState
          icon={MessagesSquare}
          title={filtered ? "No interviews match these filters" : "No interviews yet"}
          description={filtered ? undefined : "Open a research project to add interview notes."}
        />
      ) : null}
    </div>
  );
}
