"use client";

import Link from "next/link";
import { FileDown, FileText, ShieldAlert } from "lucide-react";

import { api, type ReportSummary } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function ReportStatusBadge({ status }: { status: string }) {
  return status === "approved" ? (
    <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
      Approved
    </Badge>
  ) : (
    <Badge variant="outline">Draft</Badge>
  );
}

export function ReportList({ reports, showProject = false }: { reports: ReportSummary[]; showProject?: boolean }) {
  return (
    <ul className="divide-y rounded-xl border bg-background">
      {reports.map((r) => (
        <li key={r.id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted">
              <FileText className="size-4 text-muted-foreground" />
            </span>
            <div className="min-w-0">
              <Link href={`/reports/${r.id}`} className="font-medium hover:underline">
                {r.title}
              </Link>
              <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                <ReportStatusBadge status={r.status} />
                {showProject && r.project_name ? (
                  <Link href={`/projects/${r.project_id}`} className="hover:underline">
                    {r.project_name}
                  </Link>
                ) : null}
                <span title={formatDate(r.created_at)}>{timeAgo(r.created_at)}</span>
                {r.excluded_sensitive_count ? (
                  <span className="inline-flex items-center gap-1 text-rose-700 dark:text-rose-400">
                    <ShieldAlert className="size-3" /> {r.excluded_sensitive_count} sensitive withheld
                  </span>
                ) : null}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button asChild variant="outline" size="sm">
              <a href={api.reports.markdownUrl(r.id)} download>
                <FileDown className="size-3.5" /> Markdown
              </a>
            </Button>
            <Button asChild variant="outline" size="sm">
              <a href={api.reports.pdfUrl(r.id)} download>
                <FileDown className="size-3.5" /> PDF
              </a>
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}
