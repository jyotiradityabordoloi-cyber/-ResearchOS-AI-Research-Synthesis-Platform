"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Lightbulb, Plus } from "lucide-react";
import { useState } from "react";
import {
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { toast } from "sonner";

import { api, type Insight, type PriorityBand, type Theme } from "@/lib/api";
import { percent } from "@/lib/format";
import { useChartAnimation } from "@/lib/motion";
import { EmptyState, ErrorState } from "@/components/common";
import { InsightReview } from "@/components/insights/insight-review";
import { useReviewRefresh } from "@/components/review/review-controls";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

const BAND_COLOR: Record<PriorityBand, string> = {
  high: "var(--chart-4)",
  medium: "var(--chart-3)",
  low: "var(--chart-5)",
};

type Point = { id: string; x: number; y: number; z: number; title: string; code: string | null; band: PriorityBand };

function PointTooltip({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  const p = active ? payload?.[0]?.payload : undefined;
  if (!p) return null;
  return (
    <div className="max-w-64 rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="font-medium">
        {p.code ? `${p.code} · ` : ""}
        {p.title}
      </p>
      <p className="text-muted-foreground">
        Frequency {percent(p.x)} · impact {p.y.toFixed(1)}/5 · confidence {percent(p.z)}
      </p>
    </div>
  );
}

function FrequencyImpactChart({ insights, onPick }: { insights: Insight[]; onPick: (id: string) => void }) {
  const chartMotion = useChartAnimation();
  const groups = (["high", "medium", "low"] as PriorityBand[]).map((band) => ({
    band,
    points: insights
      .filter((i) => i.effective_priority === band && i.status !== "rejected")
      .map<Point>((i) => ({
        id: i.id,
        x: i.frequency,
        y: (i.severity + i.strategic_relevance) / 2,
        z: Math.max(0.1, i.confidence),
        title: i.title,
        code: i.theme_code,
        band,
      })),
  }));
  return (
    <Card className="shadow-xs">
      <CardHeader>
        <CardTitle>Frequency vs impact</CardTitle>
        <CardDescription>
          How many people mention it (across) is separate from how much it matters (up: average of severity and strategic
          relevance). Dot size is evidence confidence. Click a dot to open that insight.
        </CardDescription>
      </CardHeader>
      <CardContent className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ left: -10, right: 16, top: 8, bottom: 8 }}>
            <CartesianGrid stroke="var(--border)" />
            <XAxis
              type="number"
              dataKey="x"
              domain={[0, 1]}
              tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
              fontSize={12}
              name="Frequency"
            />
            <YAxis type="number" dataKey="y" domain={[1, 5]} ticks={[1, 2, 3, 4, 5]} fontSize={12} name="Impact" />
            <ZAxis type="number" dataKey="z" range={[60, 260]} />
            <ReferenceLine x={0.5} stroke="var(--border)" strokeDasharray="4 4" />
            <ReferenceLine y={3} stroke="var(--border)" strokeDasharray="4 4" />
            <Tooltip content={<PointTooltip />} />
            {groups.map((g) => (
              <Scatter
                key={g.band}
                data={g.points}
                fill={BAND_COLOR[g.band]}
                fillOpacity={0.85}
                className="cursor-pointer"
                onClick={(d: unknown) => {
                  const id = (d as { payload?: Point }).payload?.id;
                  if (id) onPick(id);
                }}
                {...chartMotion}
              />
            ))}
          </ScatterChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function EditInsightDialog({
  insight,
  open,
  onOpenChange,
}: {
  insight: Insight;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const refresh = useReviewRefresh(insight.project_id);
  const [form, setForm] = useState({
    title: insight.title,
    implication: insight.implication,
    severity: insight.severity,
    strategic: insight.strategic_relevance,
    override: (insight.priority_override ?? "auto") as PriorityBand | "auto",
    reason: insight.override_reason ?? "",
    comment: insight.pm_comment ?? "",
    flag: insight.strategic_flag,
  });
  const save = useMutation({
    mutationFn: () => {
      const data: Parameters<typeof api.review.editInsight>[1] = {};
      if (form.title.trim() !== insight.title) data.title = form.title.trim();
      if (form.implication !== insight.implication) data.implication = form.implication;
      if (form.severity !== insight.severity) data.severity = form.severity;
      if (form.strategic !== insight.strategic_relevance) data.strategic_relevance = form.strategic;
      const override = form.override === "auto" ? null : form.override;
      if (override !== insight.priority_override || (override && form.reason !== (insight.override_reason ?? ""))) {
        data.priority_override = override;
        if (override) data.override_reason = form.reason.trim();
      }
      if (form.comment !== (insight.pm_comment ?? "")) data.pm_comment = form.comment || null;
      if (form.flag !== insight.strategic_flag) data.strategic_flag = form.flag;
      if (!Object.keys(data).length) return Promise.resolve(insight);
      return api.review.editInsight(insight.id, data);
    },
    onSuccess: () => {
      refresh();
      toast.success("Insight updated");
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));
  const needsReason = form.override !== "auto" && !form.reason.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>Edit insight</DialogTitle>
            <DialogDescription>
              Frequency ({percent(insight.frequency)}) comes from the evidence and can&apos;t be edited. Computed priority:{" "}
              {insight.computed_priority}.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="i-title">Title</Label>
            <Input id="i-title" value={form.title} onChange={(e) => set("title", e.target.value)} minLength={3} required />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="i-impl">Product implication</Label>
            <Textarea id="i-impl" rows={3} value={form.implication} onChange={(e) => set("implication", e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <ScoreInput label="Severity" value={form.severity} onChange={(v) => set("severity", v)} />
            <ScoreInput label="Strategic relevance" value={form.strategic} onChange={(v) => set("strategic", v)} />
          </div>
          <div className="grid gap-2">
            <Label>Priority</Label>
            <Select value={form.override} onValueChange={(v) => set("override", v as PriorityBand | "auto")}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Automatic ({insight.computed_priority})</SelectItem>
                <SelectItem value="high">Manual: High</SelectItem>
                <SelectItem value="medium">Manual: Medium</SelectItem>
                <SelectItem value="low">Manual: Low</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {form.override !== "auto" ? (
            <div className="grid gap-2">
              <Label htmlFor="i-reason">Reason for override (required)</Label>
              <Input id="i-reason" value={form.reason} onChange={(e) => set("reason", e.target.value)} />
            </div>
          ) : null}
          <div className="grid gap-2">
            <Label htmlFor="i-comment">PM comment</Label>
            <Textarea id="i-comment" rows={2} value={form.comment} onChange={(e) => set("comment", e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-[var(--primary)]"
              checked={form.flag}
              onChange={(e) => set("flag", e.target.checked)}
            />
            Flag as strategically important
          </label>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={needsReason || save.isPending}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ScoreInput({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <fieldset className="grid gap-2">
      <legend className="text-sm font-medium">{label}</legend>
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <Button
            key={n}
            type="button"
            size="icon"
            variant={n === value ? "default" : "outline"}
            className="size-8"
            onClick={() => onChange(n)}
            aria-pressed={n === value}
          >
            {n}
          </Button>
        ))}
      </div>
    </fieldset>
  );
}

function AddInsightDialog({ projectId, themes }: { projectId: string; themes: Theme[] }) {
  const refresh = useReviewRefresh(projectId);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", statement: "", implication: "", theme: "none", severity: 3, strategic: 3 });
  const create = useMutation({
    mutationFn: () =>
      api.review.createInsight(projectId, {
        title: form.title.trim(),
        statement: form.statement.trim(),
        implication: form.implication.trim(),
        theme_id: form.theme === "none" ? undefined : form.theme,
        severity: form.severity,
        strategic_relevance: form.strategic,
      }),
    onSuccess: (i) => {
      refresh();
      toast.success(i.requires_approval ? "Insight added; it needs approval (sensitive topic)" : "Insight added");
      setOpen(false);
      setForm({ title: "", statement: "", implication: "", theme: "none", severity: 3, strategic: 3 });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }));
  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        <Plus className="size-4" /> Add insight
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-lg">
          <form
            className="grid gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <DialogHeader>
              <DialogTitle>Add your own insight</DialogTitle>
              <DialogDescription>
                Manual insights are marked as PM-written. Link a theme to inherit its frequency and evidence.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-2">
              <Label htmlFor="n-title">Insight</Label>
              <Input id="n-title" value={form.title} onChange={(e) => set("title", e.target.value)} minLength={3} required />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="n-stmt">What we learned</Label>
              <Textarea id="n-stmt" rows={2} value={form.statement} onChange={(e) => set("statement", e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="n-impl">Product implication</Label>
              <Textarea id="n-impl" rows={2} value={form.implication} onChange={(e) => set("implication", e.target.value)} />
            </div>
            <div className="grid gap-2">
              <Label>Linked theme</Label>
              <Select value={form.theme} onValueChange={(v) => set("theme", v)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No theme (frequency 0%)</SelectItem>
                  {themes.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.code} · {t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <ScoreInput label="Severity" value={form.severity} onChange={(v) => set("severity", v)} />
              <ScoreInput label="Strategic relevance" value={form.strategic} onChange={(v) => set("strategic", v)} />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={form.title.trim().length < 3 || create.isPending}>
                Add insight
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

/**
 * Insight review with the shared scores dialog. Used by the project Insights tab and the
 * cross-project Insights page.
 */
export function InsightReviewPanel({
  insights,
  showProject = false,
  focus,
}: {
  insights: Insight[];
  showProject?: boolean;
  focus?: { id: string } | null;
}) {
  const [editing, setEditing] = useState<Insight | null>(null);
  return (
    <>
      <InsightReview insights={insights} showProject={showProject} onEditScores={setEditing} focus={focus} />
      {editing ? (
        <EditInsightDialog
          key={editing.id}
          insight={editing}
          open
          onOpenChange={(o) => {
            if (!o) setEditing(null);
          }}
        />
      ) : null}
    </>
  );
}

/** Project-level prioritisation view (Module E). */
export function InsightsBoard({ projectId }: { projectId: string }) {
  const insights = useQuery({ queryKey: ["insights", projectId], queryFn: () => api.synthesis.insights(projectId) });
  const themes = useQuery({ queryKey: ["themes", projectId, { showRejected: false }], queryFn: () => api.synthesis.themes(projectId) });
  const [focus, setFocus] = useState<{ id: string } | null>(null);
  if (insights.error) return <ErrorState error={insights.error} onRetry={() => insights.refetch()} />;
  if (insights.isPending) return <Skeleton className="h-64 w-full" />;
  const data = insights.data;
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-2xl text-sm text-muted-foreground">
          Priority is suggested from frequency, severity, strategic relevance and confidence. Override it when you know
          better; overrides are marked and the computed value stays visible.
        </p>
        <AddInsightDialog projectId={projectId} themes={themes.data ?? []} />
      </div>
      {data.length ? (
        <>
          <FrequencyImpactChart insights={data} onPick={(id) => setFocus({ id })} />
          <InsightReviewPanel insights={data} focus={focus} />
        </>
      ) : (
        <EmptyState
          icon={Lightbulb}
          title="No insights yet"
          description="Insights are generated from themes when you run synthesis. You can also add your own."
        />
      )}
    </div>
  );
}
