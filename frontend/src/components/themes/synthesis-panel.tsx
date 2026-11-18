"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, CircleAlert, Loader2, Sparkles, TriangleAlert } from "lucide-react";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { api, type Project, type SynthesisRun } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export const STAGES = [
  ["extraction", "Extract pain points"],
  ["embeddings", "Embed"],
  ["similarity", "Deduplicate"],
  ["clustering", "Cluster & name"],
  ["evidence", "Validate evidence"],
  ["frequency", "Count participants"],
  ["insights", "Draft insights"],
  ["contradictions", "Contradictions & outliers"],
] as const;

export function useRuns(projectId: string) {
  return useQuery({
    queryKey: ["runs", projectId],
    queryFn: () => api.synthesis.runs(projectId),
    refetchInterval: (q) => (q.state.data?.[0]?.status === "running" ? 1500 : false),
  });
}

function StageProgress({ run }: { run: SynthesisRun }) {
  const current = STAGES.findIndex(([key]) => key === run.stage);
  return (
    <ol className="flex flex-wrap gap-x-4 gap-y-2 text-xs">
      {STAGES.map(([key, label], i) => {
        const done = current > i;
        const active = current === i;
        return (
          <li
            key={key}
            className={cn(
              "flex items-center gap-1.5",
              done ? "text-foreground" : active ? "font-medium text-primary" : "text-muted-foreground",
            )}
          >
            {done ? (
              <CheckCircle2 className="size-3.5 text-emerald-600" />
            ) : active ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <span className="size-3.5 rounded-full border" />
            )}
            {label}
          </li>
        );
      })}
    </ol>
  );
}

export function SynthesisPanel({ project, reviewedCount = 0 }: { project: Project; reviewedCount?: number }) {
  const qc = useQueryClient();
  const runs = useRuns(project.id);
  const latest = runs.data?.[0];
  const active = runs.data?.find((r) => r.is_active);
  const prevStatus = useRef<string | undefined>(undefined);

  // When a run finishes, refresh everything derived from it.
  useEffect(() => {
    if (prevStatus.current === "running" && latest && latest.status !== "running") {
      for (const key of [["themes", project.id], ["insights", project.id], ["project", project.id], ["projects"], ["dashboard"]])
        qc.invalidateQueries({ queryKey: key });
      if (latest.status === "completed") toast.success(`Synthesis complete: ${latest.stats.themes ?? 0} themes`);
      else toast.error("Synthesis failed. Previous results are unchanged.");
    }
    prevStatus.current = latest?.status;
  }, [latest, project.id, qc]);

  const start = useMutation({
    mutationFn: (force: boolean) => api.synthesis.start(project.id, force),
    onSuccess: () => {
      prevStatus.current = "running";
      qc.invalidateQueries({ queryKey: ["runs", project.id] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const running = latest?.status === "running" || start.isPending;
  const onRun = () => {
    if (
      reviewedCount > 0 &&
      !confirm(
        `You have reviewed or edited ${reviewedCount} theme(s) in the current synthesis.\n\n` +
          "Re-running creates a fresh set of AI themes; your review decisions stay in the change history but will not carry over. Continue?",
      )
    )
      return;
    if (!project.ready_for_synthesis) {
      const ok = confirm(
        `Only ${project.participant_count} valid participant(s); standard synthesis needs at least 5.\n\n` +
          "Run an exploratory synthesis anyway? Results will be marked as not representative.",
      );
      if (!ok) return;
      start.mutate(true);
    } else start.mutate(false);
  };

  return (
    <Card className="shadow-xs">
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <p className="font-medium">AI theme synthesis</p>
            <p className="text-sm text-muted-foreground">
              {latest
                ? `Last run ${timeAgo(latest.started_at)} · ${latest.provider} · ${latest.model}`
                : `Clusters pain points from ${project.valid_interview_count} valid interview(s) into evidence-backed themes.`}
              {latest?.is_demo ? (
                <Badge variant="secondary" className="ml-2 bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                  Local demo mode
                </Badge>
              ) : null}
            </p>
          </div>
          <Button onClick={onRun} disabled={running || project.valid_interview_count === 0}>
            {running ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
            {running ? "Synthesising…" : latest ? "Re-run synthesis" : "Run synthesis"}
          </Button>
        </div>

        {latest?.status === "running" ? <StageProgress run={latest} /> : null}

        {latest?.status === "failed" ? (
          <Alert variant="destructive">
            <CircleAlert />
            <AlertTitle>The last synthesis run failed</AlertTitle>
            <AlertDescription>
              <p>{latest.error}</p>
              <p className="mt-1">
                No research data was changed.{" "}
                {active ? `Showing results from the run of ${timeAgo(active.started_at)}.` : "There are no earlier results."}
              </p>
            </AlertDescription>
          </Alert>
        ) : null}

        {active && active.warnings.length ? (
          <ul className="space-y-1.5 text-sm">
            {active.warnings.map((w) => (
              <li key={w.code} className="flex gap-2 text-amber-800 dark:text-amber-300">
                {w.code === "few_themes" || w.code === "insufficient_sample" ? (
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                ) : (
                  <TriangleAlert className="mt-0.5 size-4 shrink-0" />
                )}
                {w.message}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}
