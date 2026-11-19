"use client";

import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  pointerWithin,
  rectIntersection,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronsDownUp, ChevronsUpDown, Layers, Loader2, Merge, Plus, Redo2, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { api, type Evidence, type Observation, type Project, type Theme } from "@/lib/api";
import * as cmd from "@/lib/canvas-commands";
import { useCommandHistory, type Command } from "@/lib/command-history";
import { useMediaQuery, useReducedMotion } from "@/lib/motion";
import { useUrlState } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import {
  Cluster,
  DragPreview,
  NewThemeZone,
  ObservationPanel,
  type Assignment,
  type DragData,
} from "@/components/canvas/canvas-parts";
import { ThemeDetails } from "@/components/canvas/theme-details";
import { EmptyState, ErrorState } from "@/components/common";
import { useReviewRefresh } from "@/components/review/review-controls";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** Pointer position decides the drop target; keyboard dragging falls back to overlap. */
const collision: CollisionDetection = (args) => {
  const hits = pointerWithin(args);
  return hits.length ? hits : rectIntersection(args);
};

/** A drop the server hasn't confirmed yet, shown in place so the UI never snaps back. */
type Pending = { painPointId: string | null; evidenceId: string | null; toThemeId: string | null };

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
const MOD = isMac ? "⌘" : "Ctrl";

export function ThemeCanvas({ project }: { project: Project }) {
  const qc = useQueryClient();
  const refresh = useReviewRefresh(project.id);
  const reduced = useReducedMotion();
  const wide = useMediaQuery("(min-width: 80rem)");

  const themesQ = useQuery({
    queryKey: ["themes", project.id, { canvas: true }],
    queryFn: () => api.synthesis.themes(project.id, true),
  });
  const obsQ = useQuery({ queryKey: ["observations", project.id], queryFn: () => api.canvas.observations(project.id) });

  const [selectedId, setSelectedId] = useUrlState("theme", "");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [checked, setChecked] = useState<string[]>([]);
  const [showRejected, setShowRejected] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [dragging, setDragging] = useState<DragData | null>(null);
  const [creating, setCreating] = useState<{ seed: cmd.NewThemeSeed | null; name: string } | null>(null);
  const [merging, setMerging] = useState<{ name: string } | null>(null);

  const settle = useCallback(async () => {
    refresh();
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["themes", project.id] }),
      qc.invalidateQueries({ queryKey: ["observations", project.id] }),
      qc.invalidateQueries({ queryKey: ["interview-findings"] }),
    ]);
    setPending(null);
  }, [qc, project.id, refresh]);
  const history = useCommandHistory({ onSettled: settle });

  const observations = useMemo(() => obsQ.data ?? [], [obsQ.data]);
  const obsById = useMemo(() => new Map(observations.map((o) => [o.id, o])), [observations]);
  const themes = useMemo(() => applyPending(themesQ.data ?? [], pending, obsById), [themesQ.data, pending, obsById]);
  const assignments = useMemo(() => {
    const m = new Map<string, Assignment>();
    for (const t of themes) for (const e of t.evidence) if (e.pain_point_id) m.set(e.pain_point_id, { theme: t, evidence: e });
    return m;
  }, [themes]);
  const visible = themes.filter((t) => showRejected || t.status !== "rejected");
  const selected = themes.find((t) => t.id === selectedId) ?? null;
  const rejectedCount = themes.filter((t) => t.status === "rejected").length;

  // --- running commands -------------------------------------------------------

  // Toast buttons fire after later renders, so they call through a ref to the latest handlers.
  const actions = useRef({ undo: async () => {}, redo: async () => {} });
  const undo = async () => {
    try {
      const done = await history.undo();
      if (done) toast(`Undone: ${done.label}`, { action: { label: "Redo", onClick: () => void actions.current.redo() } });
    } catch (e) {
      toast.error(`Couldn't undo: ${(e as Error).message}`);
    }
  };
  const redo = async () => {
    try {
      const done = await history.redo();
      if (done) toast(`Redone: ${done.label}`, { action: { label: "Undo", onClick: () => void actions.current.undo() } });
    } catch (e) {
      toast.error(`Couldn't redo: ${(e as Error).message}`);
    }
  };
  useEffect(() => {
    actions.current = { undo, redo };
  });

  const perform = async (command: Command, optimistic?: Pending) => {
    if (optimistic) setPending(optimistic);
    try {
      await history.perform(command);
      toast.success(command.label, { action: { label: "Undo", onClick: () => void actions.current.undo() } });
    } catch (e) {
      setPending(null);
      toast.error((e as Error).message);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return;
      if (!(e.metaKey || e.ctrlKey)) return;
      const key = e.key.toLowerCase();
      if (key === "z" && !e.shiftKey) {
        e.preventDefault();
        void actions.current.undo();
      } else if ((key === "z" && e.shiftKey) || key === "y") {
        e.preventDefault();
        void actions.current.redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // --- drag and drop ----------------------------------------------------------

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  );
  const themeName = (id: string) => themes.find((t) => t.id === id)?.code ?? "theme";

  const onDragStart = (e: DragStartEvent) => setDragging(e.active.data.current as DragData);
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    setDragging(null);
    if (!over || history.busy) return;
    const d = active.data.current as DragData;
    const target = String(over.id);
    const current = d.kind === "evidence" ? themes.find((t) => t.id === d.themeId)?.evidence.find((e) => e.id === d.evidenceId) : assignments.get(d.painPointId)?.evidence;
    const currentTheme = d.kind === "evidence" ? d.themeId : assignments.get(d.painPointId)?.theme.id;

    if (target === "new-theme") {
      const obs = d.painPointId ? obsById.get(d.painPointId) : undefined;
      const seed: cmd.NewThemeSeed =
        d.kind === "observation" ? { kind: "observation", painPointId: d.painPointId } : { kind: "evidence", evidenceId: d.evidenceId, fromThemeId: d.themeId };
      setCreating({ seed, name: suggestName(obs?.text ?? current?.quote ?? "") });
      return;
    }
    if (target === "unassign") {
      if (!current || !currentTheme) return;
      if (!current.pain_point_id) {
        toast.info("Quotes added by hand can't be unassigned. Move them to another theme instead.");
        return;
      }
      void perform(
        cmd.detachEvidence(current.id, current.pain_point_id, currentTheme, current.stance, `Removed ${d.label} from ${themeName(currentTheme)}`),
        { painPointId: current.pain_point_id, evidenceId: current.id, toThemeId: null },
      );
      return;
    }
    if (target.startsWith("theme:")) {
      const to = target.slice("theme:".length);
      if (to === currentTheme) return;
      if (d.kind === "evidence") {
        void perform(cmd.moveEvidence(d.evidenceId, d.themeId, to, `Moved ${d.label} to ${themeName(to)}`), {
          painPointId: d.painPointId,
          evidenceId: d.evidenceId,
          toThemeId: to,
        });
      } else {
        void perform(
          cmd.attachObservation(d.painPointId, to, "supporting", `${currentTheme ? "Moved" : "Added"} ${d.label} to ${themeName(to)}`),
          { painPointId: d.painPointId, evidenceId: current?.id ?? null, toThemeId: to },
        );
      }
    }
  };

  // --- actions from panels ----------------------------------------------------

  const edit = (t: Theme, field: "name" | "description" | "implication", value: string) =>
    void perform(cmd.editTheme(t.id, field, t[field], value, field === "name" ? `Renamed ${t.code} to "${value}"` : `Edited ${t.code} ${field}`));
  const toggleStance = (t: Theme, e: Evidence) => {
    const to = e.stance === "supporting" ? "contradicting" : "supporting";
    void perform(cmd.setStance(e.id, e.stance, to, `Marked ${e.participant_id} as ${to} in ${t.code}`));
  };

  if (themesQ.error || obsQ.error) {
    return <ErrorState error={themesQ.error ?? obsQ.error} onRetry={() => void settle()} />;
  }
  if (themesQ.isPending || obsQ.isPending) {
    return (
      <div className="grid gap-4 md:grid-cols-[260px_minmax(0,1fr)] xl:grid-cols-[280px_minmax(0,1fr)_340px]">
        <Skeleton className="h-[480px]" />
        <Skeleton className="h-[480px]" />
        <Skeleton className="hidden h-[480px] xl:block" />
      </div>
    );
  }
  if (!themes.length && !observations.length) {
    return (
      <EmptyState
        icon={Layers}
        title="Nothing on the canvas yet"
        description="Run synthesis to extract observations from valid interviews and group them into themes you can rearrange here."
      />
    );
  }

  const details = selected ? (
    <ThemeDetails
      key={selected.id}
      theme={selected}
      observations={obsById}
      disabled={history.busy}
      onClose={wide ? undefined : () => setSelectedId("")}
      onEdit={(field, value) => edit(selected, field, value)}
      onToggleStance={(e) => toggleStance(selected, e)}
      onSplit={(ids, name) =>
        void perform(cmd.splitTheme(selected.id, ids, name, `Split ${ids.length} item(s) from ${selected.code} into "${name}"`, setSelectedId))
      }
      onDelete={() => {
        setSelectedId("");
        void perform(cmd.deleteTheme(project.id, selected, `Deleted ${selected.code} "${selected.name}"`));
      }}
      onDecided={settle}
    />
  ) : null;

  return (
    <DndContext sensors={sensors} collisionDetection={collision} onDragStart={onDragStart} onDragEnd={onDragEnd} onDragCancel={() => setDragging(null)}>
      <div className="space-y-3">
        <Toolbar
          themes={visible.length}
          observations={observations.length}
          unassigned={observations.filter((o) => !assignments.has(o.id)).length}
          busy={history.busy}
          canUndo={history.canUndo}
          canRedo={history.canRedo}
          nextUndo={history.nextUndo}
          nextRedo={history.nextRedo}
          onUndo={undo}
          onRedo={redo}
          allCollapsed={visible.length > 0 && visible.every((t) => collapsed.has(t.id))}
          onToggleAll={() =>
            setCollapsed((c) => (visible.every((t) => c.has(t.id)) ? new Set() : new Set(visible.map((t) => t.id))))
          }
          rejectedCount={rejectedCount}
          showRejected={showRejected}
          onShowRejected={setShowRejected}
          onNewTheme={() => setCreating({ seed: null, name: "" })}
        />

        <div className="grid gap-4 md:h-[calc(100svh-15rem)] md:min-h-[560px] md:grid-cols-[250px_minmax(0,1fr)] xl:grid-cols-[280px_minmax(0,1fr)_340px]">
          <ObservationPanel
            observations={observations}
            assignments={assignments}
            selectedTheme={selected}
            dragging={dragging}
            disabled={history.busy}
            onSelectTheme={setSelectedId}
          />

          <section aria-label="Theme clusters" className="min-h-0 space-y-3 overflow-y-auto rounded-xl md:pr-1">
            {visible.map((t, i) => (
              <Cluster
                key={t.id}
                theme={t}
                observations={obsById}
                index={i}
                selected={t.id === selectedId}
                collapsed={collapsed.has(t.id)}
                checked={checked.includes(t.id)}
                disabled={history.busy}
                dragging={dragging}
                onSelect={() => setSelectedId(t.id === selectedId && wide ? "" : t.id)}
                onToggle={() =>
                  setCollapsed((c) => {
                    const next = new Set(c);
                    if (next.has(t.id)) next.delete(t.id);
                    else next.add(t.id);
                    return next;
                  })
                }
                onCheck={(on) => setChecked((prev) => (on ? [...prev, t.id] : prev.filter((id) => id !== t.id)))}
                onRename={(name) => edit(t, "name", name)}
              />
            ))}
            <NewThemeZone dragging={dragging} onCreateEmpty={() => setCreating({ seed: null, name: "" })} />
          </section>

          {wide ? (
            <aside aria-label="Theme details" className="min-h-0 overflow-hidden rounded-xl border bg-background shadow-xs">
              {details ?? (
                <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center">
                  <Layers className="size-6 text-muted-foreground" />
                  <p className="font-medium">Select a theme</p>
                  <p className="text-sm text-muted-foreground text-pretty">
                    See its participants, every supporting and contradicting quote, and the AI-suggested implication.
                  </p>
                </div>
              )}
            </aside>
          ) : null}
        </div>
      </div>

      {!wide ? (
        <Sheet open={Boolean(selected)} onOpenChange={(open) => !open && setSelectedId("")}>
          <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-md [&>button:last-child]:hidden">
            <SheetTitle className="sr-only">Theme {selected?.code}</SheetTitle>
            {details}
          </SheetContent>
        </Sheet>
      ) : null}

      <DragOverlay dropAnimation={reduced ? null : { duration: 200, easing: "cubic-bezier(0.23, 1, 0.32, 1)" }}>
        {dragging ? <DragPreview data={dragging} observation={dragging.painPointId ? obsById.get(dragging.painPointId) : undefined} /> : null}
      </DragOverlay>

      {checked.length ? (
        <div className="dock fixed inset-x-0 bottom-0 z-20 border-t bg-background/95 backdrop-blur lg:left-64">
          <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-10">
            <p className="text-sm">
              {checked.length} selected: {checked.map((id) => themes.find((t) => t.id === id)?.code).join(", ")}
              {checked.length >= 2 ? <span className="text-muted-foreground"> · merges into {themes.find((t) => t.id === checked[0])?.code}</span> : null}
            </p>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setChecked([])}>
                <X /> Clear
              </Button>
              <Button
                disabled={checked.length < 2 || history.busy}
                onClick={() => setMerging({ name: themes.find((t) => t.id === checked[0])?.name ?? "" })}
              >
                <Merge /> Merge {checked.length >= 2 ? checked.length : ""} themes
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <NameDialog
        open={Boolean(creating)}
        title="New theme"
        description={
          creating?.seed ? "The item you dropped becomes its first evidence. Frequency is counted from evidence, never typed in." : "Create an empty theme, then drag observations into it."
        }
        initial={creating?.name ?? ""}
        submitLabel="Create theme"
        onClose={() => setCreating(null)}
        onSubmit={(name) => {
          const seed = creating?.seed ?? null;
          setCreating(null);
          void perform(cmd.createTheme(project.id, name, seed, `Created theme "${name}"`, setSelectedId));
        }}
      />
      <NameDialog
        open={Boolean(merging)}
        title={`Merge ${checked.length} themes`}
        description={`Evidence moves into ${themes.find((t) => t.id === checked[0])?.code}; participants are counted once. Undo restores every theme exactly.`}
        initial={merging?.name ?? ""}
        submitLabel="Merge"
        onClose={() => setMerging(null)}
        onSubmit={(name) => {
          const ids = [...checked];
          setMerging(null);
          setChecked([]);
          setSelectedId(ids[0]);
          void perform(cmd.mergeThemes(project.id, ids, name, `Merged ${ids.map((id) => themes.find((t) => t.id === id)?.code).join(" + ")}`));
        }}
      />
    </DndContext>
  );
}

function suggestName(text: string) {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > 60 ? `${clean.slice(0, 57).replace(/\s\S*$/, "")}…` : clean;
}

/** Show an unconfirmed drop in its new place until the server answers. */
function applyPending(themes: Theme[], p: Pending | null, obs: Map<string, Observation>): Theme[] {
  if (!p) return themes;
  let moving: Evidence | undefined;
  const without = themes.map((t) => {
    const hit = t.evidence.find((e) => (p.evidenceId && e.id === p.evidenceId) || (p.painPointId && e.pain_point_id === p.painPointId));
    if (!hit) return t;
    moving = hit;
    return { ...t, evidence: t.evidence.filter((e) => e !== hit) };
  });
  if (!p.toThemeId) return without;
  const o = p.painPointId ? obs.get(p.painPointId) : undefined;
  const item: Evidence | undefined =
    moving ??
    (o && {
      id: `pending-${o.id}`,
      interview_id: o.interview_id,
      pain_point_id: o.id,
      participant_id: o.participant_id,
      quote: o.quote ?? o.text,
      quote_verified: o.quote_verified,
      source_field: null,
      stance: "supporting",
      note: "",
    });
  if (!item) return without;
  return without.map((t) => (t.id === p.toThemeId ? { ...t, evidence: [...t.evidence, item] } : t));
}

function Toolbar(props: {
  themes: number;
  observations: number;
  unassigned: number;
  busy: boolean;
  canUndo: boolean;
  canRedo: boolean;
  nextUndo?: string;
  nextRedo?: string;
  onUndo: () => void;
  onRedo: () => void;
  allCollapsed: boolean;
  onToggleAll: () => void;
  rejectedCount: number;
  showRejected: boolean;
  onShowRejected: (v: boolean) => void;
  onNewTheme: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>
          <span className="font-medium text-foreground tabular-nums">{props.themes}</span> themes ·{" "}
          <span className="font-medium text-foreground tabular-nums">{props.observations}</span> observations
          {props.unassigned ? <span className="text-amber-700"> · {props.unassigned} unassigned</span> : null}
        </span>
        {props.busy ? (
          <span className="inline-flex items-center gap-1 text-xs">
            <Loader2 className="size-3 animate-spin" /> Saving…
          </span>
        ) : null}
      </p>
      <div className="flex flex-wrap items-center gap-1">
        <IconAction label={props.nextUndo ? `Undo: ${props.nextUndo}` : "Nothing to undo"} shortcut={`${MOD}+Z`} disabled={!props.canUndo} onClick={props.onUndo}>
          <Undo2 />
        </IconAction>
        <IconAction label={props.nextRedo ? `Redo: ${props.nextRedo}` : "Nothing to redo"} shortcut={`${MOD}+Shift+Z`} disabled={!props.canRedo} onClick={props.onRedo}>
          <Redo2 />
        </IconAction>
        <IconAction label={props.allCollapsed ? "Expand all themes" : "Collapse all themes"} onClick={props.onToggleAll}>
          {props.allCollapsed ? <ChevronsUpDown /> : <ChevronsDownUp />}
        </IconAction>
        {props.rejectedCount ? (
          <label className="ml-1 flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              className="size-3.5 accent-[var(--primary)]"
              checked={props.showRejected}
              onChange={(e) => props.onShowRejected(e.target.checked)}
            />
            Rejected ({props.rejectedCount})
          </label>
        ) : null}
        <Button size="sm" variant="outline" className="ml-1" onClick={props.onNewTheme} disabled={props.busy}>
          <Plus /> New theme
        </Button>
      </div>
    </div>
  );
}

function IconAction({
  label,
  shortcut,
  disabled,
  onClick,
  children,
}: {
  label: string;
  shortcut?: string;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {/* span keeps the tooltip working while the button is disabled */}
        <span tabIndex={disabled ? 0 : -1}>
          <Button variant="ghost" size="icon" className="size-8" onClick={onClick} disabled={disabled} aria-label={label}>
            {children}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {label}
        {shortcut ? <span className={cn("ml-2 opacity-60")}>{shortcut}</span> : null}
      </TooltipContent>
    </Tooltip>
  );
}

function NameDialog({
  open,
  title,
  description,
  initial,
  submitLabel,
  onClose,
  onSubmit,
}: {
  open: boolean;
  title: string;
  description: string;
  initial: string;
  submitLabel: string;
  onClose: () => void;
  onSubmit: (name: string) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        {open ? <NameForm title={title} description={description} initial={initial} submitLabel={submitLabel} onClose={onClose} onSubmit={onSubmit} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function NameForm({
  title,
  description,
  initial,
  submitLabel,
  onClose,
  onSubmit,
}: {
  title: string;
  description: string;
  initial: string;
  submitLabel: string;
  onClose: () => void;
  onSubmit: (name: string) => void;
}) {
  const [name, setName] = useState(initial);
  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (name.trim().length >= 3) onSubmit(name.trim());
      }}
    >
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>
      <div className="grid gap-2">
        <Label htmlFor="canvas-theme-name">Theme name</Label>
        <Input id="canvas-theme-name" autoFocus value={name} onChange={(e) => setName(e.target.value)} minLength={3} maxLength={300} required />
      </div>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={name.trim().length < 3}>
          {submitLabel}
        </Button>
      </DialogFooter>
    </form>
  );
}
