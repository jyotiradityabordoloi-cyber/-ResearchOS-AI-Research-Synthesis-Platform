"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { BookOpenText, Lightbulb, Scale, Search, ShieldAlert, Sparkle } from "lucide-react";
import { useDeferredValue, useState } from "react";

import { api, type RepositoryHit, type SearchParams } from "@/lib/api";
import { percent } from "@/lib/format";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, PageHeader } from "@/components/common";
import { OriginalNotesButton } from "@/components/interviews/original-notes-dialog";
import { StatusBadge } from "@/components/review/review-controls";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const ALL = "all";
type Mode = "keyword" | "semantic" | "theme";
const MODES: { value: Mode; label: string; hint: string }[] = [
  { value: "keyword", label: "Keyword", hint: "Matches words in themes, quotes and insights." },
  { value: "semantic", label: "Semantic", hint: "Finds findings with a similar meaning, even with different words." },
  { value: "theme", label: "Theme name", hint: "Matches theme names only." },
];

function FacetSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="bg-background sm:w-44" aria-label={label}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{label}: any</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function HitCard({ hit, index }: { hit: RepositoryHit; index: number }) {
  const supporting = hit.evidence.filter((e) => e.stance === "supporting");
  const contradicting = hit.evidence.filter((e) => e.stance === "contradicting");
  return (
    <Card className="enter gap-3 px-5 py-4 shadow-xs" style={{ "--i": index } as React.CSSProperties}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {hit.kind === "theme" ? <BookOpenText className="size-3.5" /> : <Lightbulb className="size-3.5" />}
            <Link href={`/projects/${hit.project_id}`} className="hover:underline">
              {hit.project_name}
            </Link>
            {hit.project_status === "completed" ? <Badge variant="outline">Completed project</Badge> : null}
            {hit.code ? <span className="font-mono">{hit.code}</span> : null}
          </p>
          <h3 className="font-semibold tracking-tight">{hit.title}</h3>
          {hit.description ? <p className="text-sm text-muted-foreground">{hit.description}</p> : null}
        </div>
        <div className="flex flex-col items-end gap-1">
          <StatusBadge status={hit.status} />
          {hit.score !== null ? (
            <span className="text-xs text-muted-foreground tabular-nums">match {percent(hit.score)}</span>
          ) : null}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {hit.participant_count !== null ? (
          <Badge variant="secondary">
            {hit.participant_count} of {hit.total_participants} participants · {percent(hit.frequency)}
          </Badge>
        ) : null}
        <Badge variant="secondary">severity {hit.severity}/5</Badge>
        {hit.priority ? <Badge variant="secondary" className="capitalize">{hit.priority} priority</Badge> : null}
        {hit.requires_approval ? (
          <Badge variant="secondary" className="bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300">
            <ShieldAlert /> Sensitive{hit.status === "approved" ? ", signed off" : ", needs approval"}
          </Badge>
        ) : null}
        {hit.is_outlier ? (
          <Badge variant="secondary" className="bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300">
            <Sparkle /> Single participant
          </Badge>
        ) : null}
        {hit.has_contradictions ? (
          <Badge variant="secondary" className="bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
            <Scale /> Contradicting evidence
          </Badge>
        ) : null}
      </div>
      {hit.implication ? (
        <p className="text-sm">
          <span className="font-medium">Implication: </span>
          {hit.implication}
        </p>
      ) : null}
      {hit.evidence.length ? (
        <ul className="space-y-2.5 border-t pt-3">
          {[...supporting, ...contradicting].map((e) => (
            <li key={e.id} className="text-sm">
              <div
                className={cn(
                  "border-l-2 pl-3",
                  e.stance === "contradicting" ? "border-amber-500" : "border-primary/50",
                )}
              >
                {e.quote ? <p>“{e.quote}”</p> : <p className="text-muted-foreground">{e.note}</p>}
                <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  {e.participant_id}
                  {e.stance === "contradicting" ? <span className="text-amber-700">contradicts</span> : null}
                  <OriginalNotesButton interviewId={e.interview_id} highlight={e.quote || undefined} />
                </p>
              </div>
            </li>
          ))}
          {hit.evidence_count > hit.evidence.length ? (
            <li className="text-xs text-muted-foreground">
              +{hit.evidence_count - hit.evidence.length} more ·{" "}
              <Link href={`/projects/${hit.project_id}`} className="underline">
                open project
              </Link>
            </li>
          ) : null}
        </ul>
      ) : null}
    </Card>
  );
}

export function RepositoryView() {
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<Mode>("keyword");
  const [projectId, setProjectId] = useState(ALL);
  const [role, setRole] = useState(ALL);
  const [size, setSize] = useState(ALL);
  const [plan, setPlan] = useState(ALL);
  const [approvedOnly, setApprovedOnly] = useState(false);
  const deferred = useDeferredValue(q.trim());

  const facets = useQuery({ queryKey: ["repository-facets"], queryFn: api.repository.facets });
  const params: SearchParams = {
    q: deferred || undefined,
    mode,
    project_id: projectId === ALL ? undefined : projectId,
    role: role === ALL ? undefined : role,
    company_size: size === ALL ? undefined : size,
    plan_tier: plan === ALL ? undefined : plan,
    approved_only: approvedOnly ? "true" : undefined,
  };
  const needsQuery = mode === "semantic" && !deferred;
  const results = useQuery({
    queryKey: ["repository", params],
    queryFn: () => api.repository.search(params),
    enabled: !needsQuery,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Research repository"
        description="Search findings from every synthesised project, so insights outlive the presentation. Every result links back to the original interview."
      />

      <div className="space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={mode === "semantic" ? "Describe a problem, e.g. “customers can't see reports without an account”" : "Search findings"}
              className="h-10 bg-background pl-9"
              aria-label="Search the research repository"
            />
          </div>
          <div className="inline-flex rounded-lg border bg-background p-0.5" role="radiogroup" aria-label="Search mode">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                role="radio"
                aria-checked={mode === m.value}
                title={m.hint}
                onClick={() => setMode(m.value)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm transition-[color,background-color,transform] duration-150 ease-out active:scale-[0.97]",
                  mode === m.value ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {m.label}
              </button>
            ))}
          </div>
        </div>
        <p className="text-xs text-muted-foreground">{MODES.find((m) => m.value === mode)?.hint}</p>
        <div className="flex flex-col flex-wrap gap-3 sm:flex-row sm:items-center">
          <FacetSelect
            label="Project"
            value={projectId}
            onChange={setProjectId}
            options={(facets.data?.projects ?? []).map((p) => ({ value: p.id, label: p.name }))}
          />
          <FacetSelect
            label="Role"
            value={role}
            onChange={setRole}
            options={(facets.data?.roles ?? []).map((r) => ({ value: r, label: r }))}
          />
          <FacetSelect
            label="Company size"
            value={size}
            onChange={setSize}
            options={(facets.data?.company_sizes ?? []).map((r) => ({ value: r, label: r }))}
          />
          <FacetSelect
            label="Plan tier"
            value={plan}
            onChange={setPlan}
            options={(facets.data?.plan_tiers ?? []).map((r) => ({ value: r, label: r }))}
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-[var(--primary)]"
              checked={approvedOnly}
              onChange={(e) => setApprovedOnly(e.target.checked)}
            />
            Approved only
          </label>
        </div>
      </div>

      {results.error ? <ErrorState error={results.error} onRetry={() => results.refetch()} /> : null}
      {needsQuery ? (
        <EmptyState
          icon={Search}
          title="Describe what you're looking for"
          description="Semantic search compares meaning, so phrase it the way a user might say it."
        />
      ) : results.isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : results.data && results.data.length ? (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{results.data.length} result(s)</p>
          {results.data.map((h, i) => (
            <HitCard key={`${h.kind}-${h.id}`} hit={h} index={i} />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={BookOpenText}
          title={deferred ? "No findings match" : "The repository is empty"}
          description={deferred ? "Try semantic search, or loosen the filters." : "Run synthesis on a project and its themes appear here."}
        />
      )}
    </div>
  );
}
