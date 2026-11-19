"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  History,
  Layers,
  MessagesSquare,
  Target,
  Trash2,
  Upload,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { api, type AuditEntry, type Project } from "@/lib/api";
import { FIELD_LABEL, timeAgo } from "@/lib/format";
import { useUrlState } from "@/lib/url-state";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  ProjectStatusBadge,
  StatCard,
  SynthesisStatusBadge,
} from "@/components/common";
import { InterviewFormDialog } from "@/components/interviews/interview-form-dialog";
import { InterviewTable } from "@/components/interviews/interview-table";
import { ValidationReportCard } from "@/components/projects/validation-report-card";
import { InsightsBoard } from "@/components/insights/insights-board";
import { ReportsTab } from "@/components/reports/reports-tab";
import { ThemesTab } from "@/components/themes/themes-tab";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const MIN_INTERVIEWS = 5;

export function ProjectDetailView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const project = useQuery({ queryKey: ["project", id], queryFn: () => api.projects.get(id) });
  const [tab, setTab] = useUrlState("tab", "overview");

  const remove = useMutation({
    mutationFn: () => api.projects.remove(id),
    onSuccess: () => {
      qc.invalidateQueries();
      toast.success("Project deleted");
      router.push("/projects");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (project.error) return <ErrorState error={project.error} onRetry={() => project.refetch()} />;
  if (project.isPending) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  const p = project.data;

  return (
    <div className="space-y-6">
      <Link href="/projects" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-3.5" /> Research projects
      </Link>
      <PageHeader
        title={p.name}
        description={p.description || undefined}
        actions={
          <>
            <ProjectStatusBadge status={p.status} />
            <SynthesisStatusBadge status={p.synthesis_status} />
            <Button
              variant="ghost"
              size="icon"
              aria-label="Delete project"
              className="text-muted-foreground hover:text-destructive"
              onClick={() => {
                if (confirm(`Delete "${p.name}" and all its interviews? This cannot be undone.`)) remove.mutate();
              }}
            >
              <Trash2 className="size-4" />
            </Button>
          </>
        }
      />

      <Tabs value={tab} onValueChange={setTab} className="gap-6">
        <TabsList className="h-auto max-w-full flex-wrap justify-start">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="interviews">
            Interviews <Badge variant="secondary" className="ml-1">{p.interview_count}</Badge>
          </TabsTrigger>
          <TabsTrigger value="themes">
            Themes {p.theme_count ? <Badge variant="secondary" className="ml-1">{p.theme_count}</Badge> : null}
          </TabsTrigger>
          <TabsTrigger value="insights">Insights</TabsTrigger>
          <TabsTrigger value="reports">Reports</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab p={p} />
        </TabsContent>
        <TabsContent value="interviews">
          <InterviewsTab p={p} />
        </TabsContent>
        <TabsContent value="themes">
          <ThemesTab project={p} />
        </TabsContent>
        <TabsContent value="insights">
          <InsightsBoard projectId={p.id} />
        </TabsContent>
        <TabsContent value="reports">
          <ReportsTab project={p} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function OverviewTab({ p }: { p: Project }) {
  return (
    <div className="space-y-6">
      {!p.ready_for_synthesis ? (
        <Alert className="border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <AlertTriangle />
          <AlertTitle>Sample too small for standard synthesis</AlertTitle>
          <AlertDescription className="text-amber-800 dark:text-amber-300">
            {p.participant_count} of {MIN_INTERVIEWS} valid participants. Add more interviews, or fix the{" "}
            {p.invalid_interview_count} with validation errors.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Interviews"
          value={p.interview_count}
          hint={`${p.valid_interview_count} valid · ${p.invalid_interview_count} need fixes`}
          icon={MessagesSquare}
        />
        <StatCard label="Unique participants" value={p.participant_count} hint="Counted once each" icon={Users} />
        <StatCard label="Themes" value={p.theme_count} icon={Layers} />
        <StatCard label="Pending reviews" value={p.pending_review_count} icon={History} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-1">
        <ValidationReportCard projectId={p.id} />
        <Card className="shadow-xs">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Target className="size-4" /> Research objectives
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-5 text-sm">
            {p.objectives.length ? (
              <ol className="list-decimal space-y-1.5 pl-4">
                {p.objectives.map((o) => (
                  <li key={o}>{o}</li>
                ))}
              </ol>
            ) : (
              <p className="text-muted-foreground">No objectives defined.</p>
            )}
            <div>
              <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">Target segments</p>
              <div className="flex flex-wrap gap-1.5">
                {p.target_segments.length ? (
                  p.target_segments.map((s) => (
                    <Badge key={s} variant="outline">
                      {s}
                    </Badge>
                  ))
                ) : (
                  <span className="text-muted-foreground">None</span>
                )}
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Owner: {p.owner_name ?? "—"} · Created {timeAgo(p.created_at)}
            </p>
          </CardContent>
        </Card>
        </div>
        <AuditCard projectId={p.id} />
      </div>
    </div>
  );
}

const ACTION_LABEL: Record<string, string> = {
  "project.created": "created the project",
  "project.updated": "updated the project",
  "interview.created": "added an interview",
  "interview.imported": "imported an interview",
  "interview.corrected": "corrected an interview",
  "interview.deleted": "deleted an interview",
  "theme.rename": "renamed a theme",
  "theme.edit": "edited a theme",
  "theme.flag_strategic": "changed a theme's strategic flag",
  "theme.approve": "approved a theme",
  "theme.reject": "rejected a theme",
  "theme.reopen": "reopened a theme",
  "theme.merge": "merged themes",
  "theme.split": "split a theme",
  "theme.approval_reset": "approval reset after evidence changed",
  "evidence.move_evidence": "moved evidence between themes",
  "evidence.add_evidence": "added a quote to a theme",
  "insight.create": "added an insight",
  "insight.edit": "edited an insight",
  "insight.override_priority": "overrode an insight's priority",
  "insight.comment": "commented on an insight",
  "insight.flag_strategic": "changed an insight's strategic flag",
  "insight.approve": "approved an insight",
  "insight.reject": "rejected an insight",
  "insight.reopen": "reopened an insight",
  "report.generated": "generated a report",
};

function describe(e: AuditEntry): string {
  const src = (e.after ?? e.before ?? {}) as Record<string, unknown>;
  const pid = typeof src.participant_id === "string" && src.participant_id ? ` (${src.participant_id})` : "";
  const label = (k: string) => (FIELD_LABEL[k] ?? k).toLowerCase();
  const preImport = e.after?.corrected_before_import as Record<string, unknown> | undefined;
  if (e.action === "rename" && e.before && e.after)
    return `renamed “${String(e.before.name)}” to “${String(e.after.name)}”`;
  if (e.action === "override_priority" && e.after)
    return e.after.priority_override
      ? `set an insight's priority to ${String(e.after.priority_override)} (${String(e.after.override_reason ?? "")})`
      : "cleared a priority override";
  if (e.action === "move_evidence" && e.before && e.after)
    return `moved ${String(e.before.participant_id)}'s evidence from ${String(e.before.theme)} to ${String(e.after.theme)}`;
  const fields =
    e.action === "corrected" || e.action === "updated"
      ? ` — ${Object.keys(e.before ?? {}).map(label).join(", ")}`
      : preImport
        ? ` — fixed before import: ${Object.keys(preImport).map(label).join(", ")}`
        : "";
  return `${ACTION_LABEL[`${e.entity_type}.${e.action}`] ?? `${e.action} ${e.entity_type}`}${pid}${fields}`;
}

function AuditCard({ projectId }: { projectId: string }) {
  const { data, isPending } = useQuery({
    queryKey: ["audit", projectId],
    queryFn: () => api.projects.audit(projectId),
  });
  return (
    <Card className="shadow-xs lg:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <History className="size-4" /> Change history
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <Skeleton className="h-32 w-full" />
        ) : data && data.length ? (
          <ol className="max-h-80 space-y-3 overflow-y-auto pr-2 text-sm">
            {data.map((e) => (
              <li key={e.id} className="flex items-baseline justify-between gap-4 border-b pb-3 last:border-0">
                <div className="min-w-0">
                  <span className="font-medium">{e.actor ?? "System"}</span>{" "}
                  <span className="text-muted-foreground">{describe(e)}</span>
                  {e.comment ? <p className="mt-0.5 text-xs text-muted-foreground italic">“{e.comment}”</p> : null}
                </div>
                <time className="shrink-0 text-xs text-muted-foreground" dateTime={e.created_at}>
                  {timeAgo(e.created_at)}
                </time>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">No changes recorded.</p>
        )}
      </CardContent>
    </Card>
  );
}

function InterviewsTab({ p }: { p: Project }) {
  const { data, error, isPending, refetch } = useQuery({
    queryKey: ["interviews", { project: p.id }],
    queryFn: () => api.interviews.forProject(p.id),
  });
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          Only valid interviews are used for synthesis. Corrections never overwrite the original notes.
        </p>
        <div className="flex gap-2">
          <InterviewFormDialog projectId={p.id} />
          <ImportButton projectId={p.id} />
        </div>
      </div>
      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}
      {isPending ? (
        <Skeleton className="h-48 w-full" />
      ) : data && data.length ? (
        <InterviewTable interviews={data} />
      ) : (
        <EmptyState
          icon={MessagesSquare}
          title="No interviews yet"
          description="Paste your notes or upload .txt, .md, .csv or .json files. Each interview needs a Participant ID, Pain and Behavior."
          action={<ImportButton projectId={p.id} />}
        />
      )}
    </div>
  );
}

function ImportButton({ projectId }: { projectId: string }) {
  return (
    <Button asChild>
      <Link href={`/projects/${projectId}/import`}>
        <Upload className="size-4" /> Import notes
      </Link>
    </Button>
  );
}
