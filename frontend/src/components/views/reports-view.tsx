"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText } from "lucide-react";

import { api } from "@/lib/api";
import { EmptyState, ErrorState, PageHeader } from "@/components/common";
import { ReportList } from "@/components/reports/report-list";
import { Skeleton } from "@/components/ui/skeleton";

export function ReportsView() {
  const reports = useQuery({ queryKey: ["reports", "all"], queryFn: api.reports.list });
  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports"
        description="Every generated research report, exportable to Markdown and PDF. Generate new ones from a project's Reports tab."
      />
      {reports.error ? <ErrorState error={reports.error} onRetry={() => reports.refetch()} /> : null}
      {reports.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : reports.data && reports.data.length ? (
        <ReportList reports={reports.data} showProject />
      ) : (
        <EmptyState
          icon={FileText}
          title="No reports yet"
          description="Open a synthesised project and use its Reports tab to generate a draft or approved report."
        />
      )}
    </div>
  );
}
