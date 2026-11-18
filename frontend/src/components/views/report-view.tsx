"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileDown, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { ErrorState, PageHeader } from "@/components/common";
import { ReportDocument } from "@/components/reports/report-document";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function ReportView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const report = useQuery({ queryKey: ["report", id], queryFn: () => api.reports.get(id) });
  const remove = useMutation({
    mutationFn: () => api.reports.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reports"] });
      toast.success("Report deleted");
      router.push(report.data ? `/projects/${report.data.project_id}` : "/reports");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (report.error) return <ErrorState error={report.error} onRetry={() => report.refetch()} />;
  if (report.isPending) return <Skeleton className="h-[70svh] w-full" />;
  const r = report.data;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link
        href={`/projects/${r.project_id}`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" /> {r.project_name}
      </Link>
      <PageHeader
        title={r.title}
        actions={
          <>
            <Button asChild variant="outline">
              <a href={api.reports.markdownUrl(r.id)} download>
                <FileDown className="size-4" /> Markdown
              </a>
            </Button>
            <Button asChild>
              <a href={api.reports.pdfUrl(r.id)} download>
                <FileDown className="size-4" /> PDF
              </a>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Delete report"
              className="text-muted-foreground hover:text-destructive"
              onClick={() => confirm("Delete this report? The findings themselves are kept.") && remove.mutate()}
            >
              <Trash2 className="size-4" />
            </Button>
          </>
        }
      />
      <ReportDocument c={r.content_json} />
    </div>
  );
}
