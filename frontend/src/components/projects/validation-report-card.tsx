"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, CircleAlert, ShieldCheck, TriangleAlert } from "lucide-react";

import { api, type Interview } from "@/lib/api";
import { InterviewFormDialog } from "@/components/interviews/interview-form-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const ICON = {
  pass: <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" />,
  warn: <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-600" />,
  fail: <CircleAlert className="mt-0.5 size-4 shrink-0 text-destructive" />,
};

/** Module C: whether this project's interviews are fit for synthesis, with links to fix them. */
export function ValidationReportCard({ projectId }: { projectId: string }) {
  const report = useQuery({ queryKey: ["validation", projectId], queryFn: () => api.imports.report(projectId) });
  const interviews = useQuery({
    queryKey: ["interviews", { project: projectId }],
    queryFn: () => api.interviews.forProject(projectId),
  });
  const byId = new Map<string, Interview>((interviews.data ?? []).map((i) => [i.id, i]));

  return (
    <Card className="shadow-xs">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="size-4" /> Synthesis readiness
        </CardTitle>
        <CardDescription>AI synthesis only runs on validated interviews.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {report.isPending ? (
          <Skeleton className="h-20 w-full" />
        ) : report.data ? (
          <>
            <div>
              {report.data.can_run_standard_synthesis ? (
                <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                  Ready for standard synthesis
                </Badge>
              ) : (
                <Badge variant="destructive">Not ready for standard synthesis</Badge>
              )}
            </div>
            <ul className="space-y-2">
              {report.data.checks.map((c) => (
                <li key={c.key} className="flex gap-2">
                  {ICON[c.status]}
                  <span>{c.message}</span>
                </li>
              ))}
            </ul>
            {report.data.invalid.length ? (
              <div className="space-y-2">
                <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Needs correction</p>
                <ul className="divide-y rounded-lg border">
                  {report.data.invalid.map((r) => {
                    const iv = byId.get(r.id);
                    return (
                      <li key={r.id} className="flex items-start justify-between gap-3 px-3 py-2">
                        <div className="min-w-0">
                          <p className="font-medium">{r.participant_id || "No participant ID"}</p>
                          <p className="text-xs text-destructive">{r.errors.join(" ")}</p>
                        </div>
                        {iv ? (
                          <InterviewFormDialog
                            projectId={projectId}
                            interview={iv}
                            trigger={
                              <Button size="sm" variant="outline">
                                Fix
                              </Button>
                            }
                          />
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
