"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BadgeCheck, Eye, FileDown, FileText, Loader2, NotebookPen, RotateCcw, ShieldAlert, Sparkle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { api, type ReportRequest, type ReportSectionKey, type Theme } from "@/lib/api";
import { percent } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ErrorState } from "@/components/common";
import { DEFAULT_TITLES, ReportDocument } from "@/components/reports/report-document";
import { DecisionButtons, StatusBadge, useReviewRefresh } from "@/components/review/review-controls";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const ALL_SECTIONS: ReportSectionKey[] = [
  "summary",
  "objective",
  "participants",
  "methodology",
  "themes",
  "frequency",
  "quotes",
  "contradictions",
  "outliers",
  "implications",
  "next_steps",
  "limitations",
];
const ESSENTIALS: ReportSectionKey[] = ["summary", "objective", "themes", "quotes", "contradictions", "implications", "next_steps", "limitations"];

type Kind = "draft" | "approved";

/**
 * Interactive report builder: choose sections and themes, review sensitive findings in
 * place, edit the executive summary, and see the exact report the server will save.
 * The preview comes from the same code that writes the saved report and its exports.
 */
export function ReportBuilderView() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const refresh = useReviewRefresh(id);

  const project = useQuery({ queryKey: ["project", id], queryFn: () => api.projects.get(id) });
  const themes = useQuery({ queryKey: ["themes", id, { showRejected: false }], queryFn: () => api.synthesis.themes(id) });

  const [kind, setKind] = useState<Kind>("draft");
  const [title, setTitle] = useState("");
  const [sections, setSections] = useState<ReportSectionKey[]>(ALL_SECTIONS);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [summary, setSummary] = useState<string | null>(null); // null: use the generated one
  const [view, setView] = useState<"document" | "markdown">("document");

  const request: ReportRequest = useMemo(
    () => ({
      kind,
      title: title.trim() || undefined,
      options: { sections, excluded_theme_ids: excluded, executive_summary: summary },
    }),
    [kind, title, sections, excluded, summary],
  );

  // Typing in the summary or title shouldn't fire a request per keystroke.
  const [debounced, setDebounced] = useState(request);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(request), 350);
    return () => clearTimeout(t);
  }, [request]);

  const preview = useQuery({
    queryKey: ["report-preview", id, debounced],
    queryFn: () => api.reports.preview(id, debounced),
    placeholderData: keepPreviousData,
    retry: false,
  });

  const save = useMutation({
    mutationFn: (download: "pdf" | "md" | null) => api.reports.create(id, request).then((r) => ({ r, download })),
    onSuccess: ({ r, download }) => {
      for (const key of [["reports"], ["project", id], ["projects"], ["audit", id], ["dashboard"]]) qc.invalidateQueries({ queryKey: key });
      toast.success(r.status === "approved" ? "Approved report saved" : "Draft report saved");
      if (download) {
        const a = document.createElement("a");
        a.href = download === "pdf" ? api.reports.pdfUrl(r.id) : api.reports.markdownUrl(r.id);
        a.download = "";
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
      router.push(`/reports/${r.id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const list = themes.data ?? [];
  const approvedCount = list.filter((t) => t.status === "approved").length;
  const content = preview.data?.content;
  const generatedSummary = content?.summary?.generated ?? "";
  const stale = preview.isFetching || debounced !== request;

  const runSave = (download: "pdf" | "md" | null) => {
    if (kind === "approved" && !confirm("Save an approved report? It includes approved findings only and marks the project as completed.")) return;
    save.mutate(download);
  };

  if (project.error) return <ErrorState error={project.error} onRetry={() => project.refetch()} />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <Link
            href={`/projects/${id}?tab=reports`}
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" /> {project.data?.name ?? "Project"}
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">Report builder</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={save.isPending || !content} onClick={() => runSave("md")}>
            <FileDown /> Save & Markdown
          </Button>
          <Button variant="outline" disabled={save.isPending || !content} onClick={() => runSave("pdf")}>
            <FileDown /> Save & PDF
          </Button>
          <Button disabled={save.isPending || !content} onClick={() => runSave(null)}>
            {save.isPending ? <Loader2 className="animate-spin" /> : kind === "approved" ? <BadgeCheck /> : <NotebookPen />}
            Save {kind === "approved" ? "approved report" : "draft"}
          </Button>
        </div>
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="space-y-4 lg:sticky lg:top-6 lg:max-h-[calc(100svh-3rem)] lg:overflow-y-auto lg:pr-1">
          <Block title="Report">
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={preview.data?.title ?? "Report title"}
              aria-label="Report title"
              className="bg-background"
            />
            <div className="grid grid-cols-2 gap-1 rounded-lg border bg-muted/50 p-0.5" role="radiogroup" aria-label="Report type">
              {(
                [
                  ["draft", "Draft", "Approved and unreviewed findings"],
                  ["approved", "Approved", approvedCount ? "Approved findings only" : "Approve a theme first"],
                ] as const
              ).map(([value, label, hint]) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={kind === value}
                  disabled={value === "approved" && !approvedCount}
                  onClick={() => setKind(value)}
                  className={cn(
                    "rounded-md px-2.5 py-1.5 text-left transition-[color,background-color,box-shadow,transform] duration-150 ease-out active:scale-[0.98] disabled:opacity-50",
                    kind === value ? "bg-background shadow-xs" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <span className="block text-sm font-medium">{label}</span>
                  <span className="block text-[11px] text-muted-foreground">{hint}</span>
                </button>
              ))}
            </div>
          </Block>

          <Block
            title="Sections"
            action={
              <div className="flex gap-2 text-xs">
                <button type="button" className="text-primary hover:underline" onClick={() => setSections(ALL_SECTIONS)}>
                  All
                </button>
                <button type="button" className="text-primary hover:underline" onClick={() => setSections(ESSENTIALS)}>
                  Essentials
                </button>
              </div>
            }
          >
            <ul className="space-y-0.5">
              {ALL_SECTIONS.map((key) => (
                <li key={key}>
                  <label className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-sm hover:bg-muted/60">
                    <input
                      type="checkbox"
                      className="size-3.5 accent-[var(--primary)]"
                      checked={sections.includes(key)}
                      onChange={(e) =>
                        setSections((prev) =>
                          e.target.checked ? ALL_SECTIONS.filter((k) => prev.includes(k) || k === key) : prev.filter((k) => k !== key),
                        )
                      }
                    />
                    {DEFAULT_TITLES[key]}
                  </label>
                </li>
              ))}
            </ul>
          </Block>

          <Block
            title="Themes"
            hint="Untick to leave a theme out. Left-out themes are listed under Limitations so the report stays honest."
          >
            {themes.isPending ? (
              <Skeleton className="h-40 w-full" />
            ) : list.length ? (
              <ul className="space-y-1">
                {list.map((t) => (
                  <ThemeRow
                    key={t.id}
                    theme={t}
                    kind={kind}
                    included={!excluded.includes(t.id)}
                    onToggle={(on) => setExcluded((prev) => (on ? prev.filter((x) => x !== t.id) : [...prev, t.id]))}
                    onDecided={async () => {
                      refresh();
                      await qc.invalidateQueries({ queryKey: ["report-preview", id] });
                    }}
                  />
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Run synthesis to get themes.</p>
            )}
          </Block>

          <Block
            title="Executive summary"
            hint={summary === null ? "Assembled from the report's numbers. Edit it in your own words." : "Your version is saved with the report."}
            action={
              summary !== null ? (
                <button type="button" className="inline-flex items-center gap-1 text-xs text-primary hover:underline" onClick={() => setSummary(null)}>
                  <RotateCcw className="size-3" /> Reset
                </button>
              ) : null
            }
          >
            <Textarea
              value={summary ?? generatedSummary}
              onChange={(e) => setSummary(e.target.value)}
              rows={7}
              disabled={!sections.includes("summary")}
              placeholder={sections.includes("summary") ? "Loading…" : "The executive summary section is turned off."}
              className="bg-background text-sm"
              aria-label="Executive summary"
            />
          </Block>
        </aside>

        <section aria-label="Report preview" className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Eye className="size-4" /> Live preview
              {stale ? (
                <span className="inline-flex items-center gap-1 text-xs">
                  <Loader2 className="size-3 animate-spin" /> updating
                </span>
              ) : content ? (
                <span className="text-xs">
                  {content.sections.frequency.length} theme(s) · {content.excluded.sensitive_pending.length} sensitive withheld
                </span>
              ) : null}
            </div>
            <div className="inline-flex rounded-lg border bg-muted/50 p-0.5" role="radiogroup" aria-label="Preview format">
              {(
                [
                  ["document", "Document"],
                  ["markdown", "Markdown"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={view === value}
                  onClick={() => setView(value)}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-xs transition-[color,background-color,box-shadow] duration-150",
                    view === value ? "bg-background font-medium shadow-xs" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {preview.error && !content ? (
            <ErrorState error={preview.error} onRetry={() => preview.refetch()} />
          ) : preview.error ? (
            <p className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {(preview.error as Error).message} The preview below shows the last valid version.
            </p>
          ) : null}

          {!content ? (
            preview.isPending ? <Skeleton className="h-[70svh] w-full rounded-xl" /> : null
          ) : (
            <div className={cn("transition-opacity duration-200", stale && "opacity-60")}>
              {view === "document" ? (
                <div className="space-y-3">
                  <h2 className="px-1 text-xl font-semibold tracking-tight">{preview.data?.title}</h2>
                  <ReportDocument c={content} />
                </div>
              ) : (
                <pre className="max-h-[75svh] overflow-auto rounded-xl border bg-background p-5 font-mono text-xs leading-relaxed whitespace-pre-wrap">
                  {preview.data?.markdown}
                </pre>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Block({ title, hint, action, children }: { title: string; hint?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="space-y-2 rounded-xl border bg-background p-3.5 shadow-xs">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {hint ? <p className="text-xs text-muted-foreground text-pretty">{hint}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function ThemeRow({
  theme: t,
  kind,
  included,
  onToggle,
  onDecided,
}: {
  theme: Theme;
  kind: Kind;
  included: boolean;
  onToggle: (on: boolean) => void;
  onDecided: () => Promise<unknown>;
}) {
  const withheld = t.requires_approval && t.status !== "approved";
  const notApproved = kind === "approved" && t.status !== "approved" && !withheld;
  const blocked = withheld || notApproved;
  const reason = withheld
    ? "Sensitive: withheld until someone approves it with an acknowledgement."
    : notApproved
      ? "Only approved themes appear in an approved report."
      : null;

  return (
    <li className={cn("rounded-lg border px-2.5 py-2", withheld ? "border-rose-200 bg-rose-50/40" : "bg-background", blocked && !withheld && "opacity-60")}>
      <label className={cn("flex items-start gap-2", blocked ? "cursor-not-allowed" : "cursor-pointer")}>
        <input
          type="checkbox"
          className="mt-0.5 size-3.5 accent-[var(--primary)]"
          checked={included && !blocked}
          disabled={blocked}
          onChange={(e) => onToggle(e.target.checked)}
          aria-label={`Include ${t.code} in the report`}
        />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span className="font-mono text-[11px] text-muted-foreground">{t.code}</span>
            <span className="truncate text-sm font-medium">{t.name}</span>
          </span>
          <span className="mt-0.5 flex flex-wrap items-center gap-1 text-[11px] text-muted-foreground">
            {t.participant_count}/{t.total_participants} · {percent(t.frequency)}
            <StatusBadge status={t.status} />
            {t.is_outlier ? (
              <Badge variant="secondary" className="bg-violet-50 text-violet-700">
                <Sparkle /> 1 participant
              </Badge>
            ) : null}
          </span>
        </span>
        {reason ? (
          <Tooltip>
            <TooltipTrigger asChild>
              {withheld ? <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-rose-600" /> : <FileText className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />}
            </TooltipTrigger>
            <TooltipContent className="max-w-60">{reason}</TooltipContent>
          </Tooltip>
        ) : null}
      </label>
      {withheld ? (
        <div className="mt-2 space-y-1.5 border-t border-rose-200 pt-2">
          <p className="text-[11px] text-rose-800">
            Sensitive ({t.sensitive_tags.join(", ").replaceAll("_", " ")}). Review it here to include it.
          </p>
          <DecisionButtons
            size="xs"
            status={t.status}
            sensitiveTags={t.sensitive_tags}
            requiresApproval={t.requires_approval}
            onDecide={async (payload) => {
              const r = await api.review.reviewTheme(t.id, payload);
              await onDecided();
              return r;
            }}
          />
        </div>
      ) : null}
    </li>
  );
}
