"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, MessagesSquare, MousePointerClick, Search, X } from "lucide-react";
import { useDeferredValue, useMemo, type KeyboardEvent } from "react";

import { api, type FacetValue, type Interview } from "@/lib/api";
import { formatDay, timeAgo } from "@/lib/format";
import { useMediaQuery } from "@/lib/motion";
import { useUrlState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { EmptyState, ErrorState, PageHeader, ValidationBadge } from "@/components/common";
import { Highlight } from "@/components/highlight";
import { InterviewDetail, ParticipantAvatar } from "@/components/interviews/interview-detail";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";

const ALL = "all";
type FacetKey = "role" | "company_size" | "plan_tier";

export function InterviewsView() {
  const [q, setQ] = useUrlState("q", "");
  const [projectId, setProjectId] = useUrlState("project_id", ALL);
  const [status, setStatus] = useUrlState("status", ALL);
  const [role, setRole] = useUrlState("role", ALL);
  const [size, setSize] = useUrlState("company_size", ALL);
  const [plan, setPlan] = useUrlState("plan_tier", ALL);
  const [createdOn, setCreatedOn] = useUrlState("created_on", "");
  const [selected, setSelected] = useUrlState("interview", "");
  const deferred = useDeferredValue(q.trim());
  const wide = useMediaQuery("(min-width: 80rem)");

  const projects = useQuery({ queryKey: ["projects", {}], queryFn: () => api.projects.list() });
  const facets = useQuery({
    queryKey: ["interview-facets", projectId],
    queryFn: () => api.interviews.facets(projectId === ALL ? undefined : projectId),
  });
  const params = {
    q: deferred || undefined,
    project_id: projectId === ALL ? undefined : projectId,
    validation_status: status === ALL ? undefined : status,
    role: role === ALL ? undefined : role,
    company_size: size === ALL ? undefined : size,
    plan_tier: plan === ALL ? undefined : plan,
    created_on: createdOn || undefined,
  };
  const list = useQuery({ queryKey: ["interviews", params], queryFn: () => api.interviews.list(params) });
  const rows = useMemo(() => list.data ?? [], [list.data]);

  // A deep link (?interview=<id>) may point outside the current filters; fetch it directly.
  const inList = rows.find((r) => r.id === selected);
  const direct = useQuery({
    queryKey: ["interview", selected],
    queryFn: () => api.interviews.get(selected),
    enabled: Boolean(selected) && !inList && !list.isPending,
  });
  const current = inList ?? direct.data;
  const index = inList ? rows.indexOf(inList) : -1;

  const setters: Record<FacetKey, (v: string) => void> = { role: setRole, company_size: setSize, plan_tier: setPlan };
  const active: { key: string; label: string; value: string; clear: () => void }[] = [
    role !== ALL && { key: "role", label: "Role", value: role, clear: () => setRole(ALL) },
    size !== ALL && { key: "size", label: "Size", value: size, clear: () => setSize(ALL) },
    plan !== ALL && { key: "plan", label: "Plan", value: plan, clear: () => setPlan(ALL) },
    createdOn && { key: "day", label: "Added on", value: formatDay(createdOn), clear: () => setCreatedOn("") },
  ].filter(Boolean) as { key: string; label: string; value: string; clear: () => void }[];
  const filtered = Boolean(deferred || projectId !== ALL || status !== ALL || active.length);
  const clearAll = () => {
    setQ("");
    setProjectId(ALL);
    setStatus(ALL);
    setRole(ALL);
    setSize(ALL);
    setPlan(ALL);
    setCreatedOn("");
  };

  const participants = new Set(rows.map((r) => r.participant_id.toLowerCase()).filter(Boolean)).size;
  const select = (iv: Interview | undefined) => {
    if (!iv) return;
    setSelected(iv.id);
    document.querySelector<HTMLElement>(`[data-interview="${iv.id}"]`)?.focus({ preventScroll: false });
  };
  // Arrow keys move through the list. Keyboard navigation is instant: no animation.
  const onListKey = (e: KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const from = index === -1 ? (e.key === "ArrowDown" ? -1 : rows.length) : index;
    select(rows[from + (e.key === "ArrowDown" ? 1 : -1)]);
  };

  const detail = current ? (
    <InterviewDetail
      key={current.id}
      interview={current}
      onClose={() => setSelected("")}
      onPrev={index > 0 ? () => select(rows[index - 1]) : undefined}
      onNext={index !== -1 && index < rows.length - 1 ? () => select(rows[index + 1]) : undefined}
      position={index !== -1 ? `${index + 1} of ${rows.length}` : "Outside current filters"}
      onFilter={(key, value) => setters[key](value)}
    />
  ) : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Interview explorer"
        description="Search participants, slice by segment, and trace every interview to the themes and insights it supports."
      />

      <div className="space-y-3">
        <div className="flex flex-col gap-3 lg:flex-row">
          <div className="relative flex-1 lg:max-w-md">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search participant, role, pain, behavior, quote…"
              className="bg-background pl-9"
              aria-label="Search interviews"
            />
          </div>
          <Select value={projectId} onValueChange={setProjectId}>
            <SelectTrigger className="bg-background lg:w-60" aria-label="Filter by project">
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
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
          <FacetSelect label="Role" value={role} onChange={setRole} options={facets.data?.roles} />
          <FacetSelect label="Company size" value={size} onChange={setSize} options={facets.data?.company_sizes} />
          <FacetSelect label="Plan tier" value={plan} onChange={setPlan} options={facets.data?.plan_tiers} />
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="bg-background sm:w-40" aria-label="Filter by validation status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Any status</SelectItem>
              <SelectItem value="valid">Valid</SelectItem>
              <SelectItem value="invalid">Needs fixes</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex min-h-7 flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground tabular-nums">
            {list.data ? (
              <>
                <span className="font-medium text-foreground">{rows.length}</span> interview{rows.length === 1 ? "" : "s"} ·{" "}
                <span className="font-medium text-foreground">{participants}</span> participant{participants === 1 ? "" : "s"}
              </>
            ) : (
              "Loading…"
            )}
          </span>
          {active.map((f) => (
            <span key={f.key} className="enter inline-flex h-7 items-center gap-1 rounded-full border bg-background pr-1 pl-2.5 text-xs">
              {f.key === "day" ? <CalendarDays className="size-3 text-muted-foreground" /> : null}
              <span className="text-muted-foreground">{f.label}</span> {f.value}
              <button
                type="button"
                onClick={f.clear}
                className="rounded-full p-0.5 transition-colors hover:bg-foreground/10"
                aria-label={`Clear the ${f.label.toLowerCase()} filter`}
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
          {filtered ? (
            <Button variant="ghost" size="sm" className="h-7 text-muted-foreground" onClick={clearAll}>
              Clear all
            </Button>
          ) : null}
        </div>
      </div>

      {list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> : null}

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,460px)]">
        <div className="min-w-0">
          {list.isPending ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-20 w-full rounded-lg" />
              ))}
            </div>
          ) : rows.length ? (
            <div role="listbox" aria-label="Interviews" className="space-y-2" onKeyDown={onListKey}>
              {rows.map((iv, i) => (
                <InterviewRow
                  key={iv.id}
                  iv={iv}
                  index={i}
                  query={deferred}
                  selected={iv.id === selected}
                  showProject={projectId === ALL}
                  onSelect={() => setSelected(iv.id)}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={MessagesSquare}
              title={filtered ? "No interviews match these filters" : "No interviews yet"}
              description={filtered ? "Loosen a filter or clear them all." : "Open a research project to add interview notes."}
              action={
                filtered ? (
                  <Button variant="outline" size="sm" onClick={clearAll}>
                    Clear all filters
                  </Button>
                ) : undefined
              }
            />
          )}
        </div>

        {wide ? (
          <aside className="sticky top-6 h-[calc(100svh-3rem)] min-h-96 overflow-hidden rounded-xl border bg-background shadow-xs">
            {detail ?? (
              direct.isFetching ? (
                <div className="space-y-3 p-5">
                  <Skeleton className="h-12 w-full" />
                  <Skeleton className="h-40 w-full" />
                </div>
              ) : (
                <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
                  <span className="flex size-10 items-center justify-center rounded-full bg-muted">
                    <MousePointerClick className="size-5 text-muted-foreground" />
                  </span>
                  <p className="font-medium">Select an interview</p>
                  <p className="text-sm text-muted-foreground text-pretty">
                    See its pain points, the themes and insights it supports, and the original notes with every cited quote
                    highlighted. Use ↑ ↓ to move through the list.
                  </p>
                </div>
              )
            )}
          </aside>
        ) : null}
      </div>

      {!wide ? (
        <Sheet open={Boolean(current)} onOpenChange={(open) => !open && setSelected("")}>
          <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-lg [&>button:last-child]:hidden">
            <SheetTitle className="sr-only">Interview {current?.participant_id}</SheetTitle>
            {detail}
          </SheetContent>
        </Sheet>
      ) : null}
    </div>
  );
}

function FacetSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options?: FacetValue[];
}) {
  // Keep a value from the URL selectable even if it has no interviews in this project.
  const values = options ?? [];
  const missing = value !== ALL && !values.some((o) => o.value.toLowerCase() === value.toLowerCase());
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className={cn("bg-background sm:w-48", value !== ALL && "border-primary/40 text-primary")} aria-label={`Filter by ${label.toLowerCase()}`}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL}>{label}: any</SelectItem>
        {missing ? <SelectItem value={value}>{value} (0)</SelectItem> : null}
        {values.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.value} <span className="text-muted-foreground tabular-nums">({o.count})</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function InterviewRow({
  iv,
  index,
  query,
  selected,
  showProject,
  onSelect,
}: {
  iv: Interview;
  index: number;
  query: string;
  selected: boolean;
  showProject: boolean;
  onSelect: () => void;
}) {
  const segment = [iv.participant_role, iv.company_size, iv.plan_tier].filter(Boolean).join(" · ");
  return (
    <button
      type="button"
      role="option"
      aria-selected={selected}
      data-interview={iv.id}
      onClick={onSelect}
      className={cn(
        "enter flex w-full gap-3 rounded-lg border px-4 py-3 text-left outline-none transition-[background-color,border-color,box-shadow] duration-150 focus-visible:ring-2 focus-visible:ring-ring",
        selected ? "border-primary/40 bg-primary/5 shadow-xs" : "bg-background hover:border-foreground/15 hover:shadow-xs",
      )}
      style={{ "--i": index } as React.CSSProperties}
    >
      <ParticipantAvatar id={iv.participant_id} />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">
            {iv.participant_id ? <Highlight text={iv.participant_id} terms={[query]} /> : <span className="text-destructive">Missing ID</span>}
          </span>
          <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
            <Highlight text={segment || "No segment"} terms={[query]} />
          </span>
          <ValidationBadge status={iv.validation_status} />
        </div>
        <p className="line-clamp-2 text-sm text-muted-foreground">
          <Highlight text={iv.pain || iv.behavior || "No pain recorded."} terms={[query]} />
        </p>
        <p className="truncate text-xs text-muted-foreground/80">
          {showProject && iv.project_name ? `${iv.project_name} · ` : ""}
          added {timeAgo(iv.created_at)}
        </p>
      </div>
    </button>
  );
}
