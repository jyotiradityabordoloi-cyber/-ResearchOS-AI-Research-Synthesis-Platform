"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { FileText, LayoutTemplate, Loader2, NotebookPen } from "lucide-react";
import { toast } from "sonner";

import { api, type Project } from "@/lib/api";
import { EmptyState, ErrorState } from "@/components/common";
import { ReportList } from "@/components/reports/report-list";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function ReportsTab({ project }: { project: Project }) {
  const router = useRouter();
  const qc = useQueryClient();
  const reports = useQuery({ queryKey: ["reports", project.id], queryFn: () => api.reports.forProject(project.id) });
  const themes = useQuery({
    queryKey: ["themes", project.id, { showRejected: false }],
    queryFn: () => api.synthesis.themes(project.id),
  });
  const approved = (themes.data ?? []).filter((t) => t.status === "approved").length;
  const sensitivePending = (themes.data ?? []).filter((t) => t.requires_approval && t.status !== "approved").length;
  const hasSynthesis = project.synthesis_status === "completed" || (themes.data?.length ?? 0) > 0;

  const generate = useMutation({
    mutationFn: (kind: "draft" | "approved") => api.reports.generate(project.id, kind),
    onSuccess: (r) => {
      for (const key of [["reports"], ["project", project.id], ["projects"], ["audit", project.id], ["dashboard"]])
        qc.invalidateQueries({ queryKey: key });
      toast.success(r.status === "approved" ? "Approved report generated" : "Draft report generated");
      router.push(`/reports/${r.id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-6">
      <Card className="shadow-xs">
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-2xl space-y-1">
              <p className="font-medium">Research report</p>
              <p className="text-sm text-muted-foreground">
                Use the builder to choose sections and themes, review sensitive findings and write the executive summary
                with a live preview. A quick draft uses every section.
              </p>
              <p className="text-sm text-muted-foreground">
                A draft includes approved and not-yet-reviewed findings. An approved report includes only approved
                findings and marks the project as completed. Sensitive findings (pricing, churn, competitive switching)
                appear only once approved.
              </p>
              <p className="text-sm">
                <span className="font-medium">{approved}</span> approved theme(s)
                {sensitivePending ? (
                  <span className="text-rose-700 dark:text-rose-400"> · {sensitivePending} sensitive will be withheld</span>
                ) : null}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button variant="outline" disabled={!hasSynthesis || generate.isPending} onClick={() => generate.mutate("draft")}>
                {generate.isPending && generate.variables === "draft" ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <NotebookPen className="size-4" />
                )}
                Quick draft
              </Button>
              <Button asChild disabled={!hasSynthesis}>
                <Link href={`/projects/${project.id}/reports/new`} aria-disabled={!hasSynthesis} className={hasSynthesis ? undefined : "pointer-events-none opacity-50"}>
                  <LayoutTemplate className="size-4" /> Open report builder
                </Link>
              </Button>
            </div>
          </div>
          {!hasSynthesis ? (
            <p className="text-sm text-muted-foreground">Run synthesis on the Themes tab first.</p>
          ) : !approved ? (
            <p className="text-sm text-muted-foreground">Approve at least one theme to build an approved report.</p>
          ) : null}
        </CardContent>
      </Card>

      {reports.error ? <ErrorState error={reports.error} onRetry={() => reports.refetch()} /> : null}
      {reports.isPending ? (
        <Skeleton className="h-32 w-full" />
      ) : reports.data && reports.data.length ? (
        <ReportList reports={reports.data} />
      ) : (
        <EmptyState icon={FileText} title="No reports yet" description="Generated reports are kept here and in Reports." />
      )}
    </div>
  );
}
