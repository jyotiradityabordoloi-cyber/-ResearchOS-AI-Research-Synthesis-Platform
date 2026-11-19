"use client";

import { useQuery } from "@tanstack/react-query";
import { LayoutGrid, Layers, List, Merge, X } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, type Project } from "@/lib/api";
import { useChartAnimation } from "@/lib/motion";
import { percent } from "@/lib/format";
import { useUrlState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { ThemeCanvas } from "@/components/canvas/theme-canvas";
import { EmptyState, ErrorState } from "@/components/common";
import { MergeThemesDialog } from "@/components/review/theme-dialogs";
import { SynthesisPanel } from "@/components/themes/synthesis-panel";
import { ThemeCard } from "@/components/themes/theme-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

type ChartRow = { code: string; name: string; participants: number; frequency: number };

function FrequencyTooltip({ active, payload }: { active?: boolean; payload?: { payload: ChartRow }[] }) {
  const row = active ? payload?.[0]?.payload : undefined;
  if (!row) return null;
  return (
    <div className="max-w-64 rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="font-medium">
        {row.code} · {row.name}
      </p>
      <p className="text-muted-foreground">
        {row.participants} participant(s) · {percent(row.frequency)}
      </p>
    </div>
  );
}

function ViewSwitch({ view, onChange }: { view: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="inline-flex rounded-lg border bg-muted/50 p-0.5" role="radiogroup" aria-label="Themes view">
        {(
          [
            ["canvas", "Canvas", LayoutGrid],
            ["list", "List", List],
          ] as const
        ).map(([value, label, Icon]) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={view === value}
            onClick={() => onChange(value)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1 text-sm transition-[color,background-color,box-shadow,transform] duration-150 ease-out active:scale-[0.97]",
              view === value ? "bg-background font-medium shadow-xs" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="size-3.5" /> {label}
          </button>
        ))}
      </div>
      <p className="hidden text-xs text-muted-foreground sm:block">
        {view === "canvas"
          ? "Drag observations between themes. Every change is saved and can be undone."
          : "Review themes one by one with their full evidence and history."}
      </p>
    </div>
  );
}

export function ThemesTab({ project }: { project: Project }) {
  const chartMotion = useChartAnimation();
  const [showRejected, setShowRejected] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [merging, setMerging] = useState(false);
  const [view, setView] = useUrlState("view", "canvas");
  const themes = useQuery({
    queryKey: ["themes", project.id, { showRejected }],
    queryFn: () => api.synthesis.themes(project.id, showRejected),
  });
  const data = themes.data ?? [];
  const live = data.filter((t) => t.status !== "rejected");
  const chart: ChartRow[] = live.map((t) => ({
    code: t.code,
    name: t.name,
    participants: t.participant_count,
    frequency: t.frequency,
  }));
  const counts = {
    approved: live.filter((t) => t.status === "approved").length,
    pending: live.filter((t) => t.status === "proposed").length,
    sensitivePending: live.filter((t) => t.status === "proposed" && t.requires_approval).length,
  };
  const reviewed = data.filter((t) => t.status !== "proposed" || t.human_edited).length;
  const selectedThemes = selected.map((id) => data.find((t) => t.id === id)).filter((t) => t !== undefined);

  if (view === "canvas" && data.length) {
    return (
      <div className="space-y-6">
        <SynthesisPanel project={project} reviewedCount={reviewed} />
        <ViewSwitch view={view} onChange={setView} />
        <ThemeCanvas project={project} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SynthesisPanel project={project} reviewedCount={reviewed} />
      {data.length ? <ViewSwitch view={view} onChange={setView} /> : null}
      {themes.error ? <ErrorState error={themes.error} onRetry={() => themes.refetch()} /> : null}
      {themes.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : data.length === 0 && !showRejected ? (
        <EmptyState
          icon={Layers}
          title="No themes yet"
          description="Run synthesis to cluster pain points from valid interviews into themes, each with participant frequency and supporting quotes."
        />
      ) : (
        <>
          <Card className="shadow-xs">
            <CardHeader>
              <CardTitle>Participant frequency</CardTitle>
              <CardDescription>
                Unique participants per theme. Frequency is not importance: check severity and evidence too.
              </CardDescription>
            </CardHeader>
            <CardContent style={{ height: Math.max(160, chart.length * 40) }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chart} layout="vertical" margin={{ left: 0, right: 16 }}>
                  <CartesianGrid horizontal={false} stroke="var(--border)" />
                  <XAxis
                    type="number"
                    allowDecimals={false}
                    domain={[0, live[0]?.total_participants ?? "auto"]}
                    tickLine={false}
                    axisLine={false}
                    fontSize={12}
                  />
                  <YAxis type="category" dataKey="code" width={36} tickLine={false} axisLine={false} fontSize={12} />
                  <Tooltip cursor={{ fill: "var(--muted)" }} content={<FrequencyTooltip />} />
                  <Bar dataKey="participants" fill="var(--chart-1)" radius={[0, 4, 4, 0]} maxBarSize={22} {...chartMotion} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">{counts.approved}</span> approved ·{" "}
              <span className="font-medium text-foreground">{counts.pending}</span> awaiting review
              {counts.sensitivePending ? (
                <span className="text-rose-700 dark:text-rose-400"> · {counts.sensitivePending} sensitive need sign-off</span>
              ) : null}
              . Select two or more themes to merge them.
            </p>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4 accent-[var(--primary)]"
                checked={showRejected}
                onChange={(e) => setShowRejected(e.target.checked)}
              />
              Show rejected themes
            </label>
          </div>

          <div className="space-y-4">
            {data.map((t, i) => (
              <ThemeCard
                index={i}
                key={t.id}
                theme={t}
                allThemes={data}
                selected={selected.includes(t.id)}
                onSelect={(checked) =>
                  setSelected((prev) => (checked ? [...prev, t.id] : prev.filter((id) => id !== t.id)))
                }
              />
            ))}
          </div>
        </>
      )}

      {selected.length ? (
        <div className="dock fixed inset-x-0 bottom-0 z-20 border-t bg-background/95 backdrop-blur lg:left-64">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-10">
            <p className="text-sm">
              {selected.length} theme(s) selected: {selectedThemes.map((t) => t.code).join(", ")}
            </p>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setSelected([])}>
                <X className="size-4" /> Clear
              </Button>
              <Button disabled={selected.length < 2} onClick={() => setMerging(true)}>
                <Merge className="size-4" /> Merge {selected.length >= 2 ? selected.length : ""} themes
              </Button>
            </div>
          </div>
        </div>
      ) : null}
      <MergeThemesDialog
        projectId={project.id}
        themes={selectedThemes}
        open={merging}
        onOpenChange={setMerging}
        onMerged={() => setSelected([])}
      />
    </div>
  );
}
