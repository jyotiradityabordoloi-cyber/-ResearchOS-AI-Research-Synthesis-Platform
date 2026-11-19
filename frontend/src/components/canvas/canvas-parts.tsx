"use client";

import { useDraggable, useDroppable } from "@dnd-kit/core";
import {
  BadgeCheck,
  ChevronRight,
  GripVertical,
  Plus,
  Quote,
  Scale,
  Search,
  ShieldAlert,
  Sparkle,
  Undo2,
} from "lucide-react";
import { useState, type ReactNode } from "react";

import type { Evidence, Observation, Theme } from "@/lib/api";
import { percent } from "@/lib/format";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/components/review/review-controls";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export type DragData =
  | { kind: "observation"; painPointId: string; label: string }
  | { kind: "evidence"; evidenceId: string; themeId: string; painPointId: string | null; label: string };

export interface Assignment {
  theme: Theme;
  evidence: Evidence;
}

export type ObservationFilter = "all" | "unassigned" | "selected" | "contradicting";

// ---------------------------------------------------------------------------
// Small shared pieces
// ---------------------------------------------------------------------------

export function ParticipantTag({ id, className }: { id: string; className?: string }) {
  return (
    <span className={cn("rounded bg-primary/8 px-1.5 py-px font-mono text-[11px] font-medium text-primary", className)}>
      {id || "?"}
    </span>
  );
}

function SeverityDots({ value }: { value: number | null }) {
  if (!value) return null;
  return (
    <span className="flex gap-0.5" aria-label={`Severity ${value} of 5`} title={`Severity ${value}/5`}>
      {Array.from({ length: 5 }).map((_, i) => (
        <span key={i} className={cn("size-1 rounded-full", i < value ? "bg-rose-500/80" : "bg-muted-foreground/20")} />
      ))}
    </span>
  );
}

/** Hover preview of the verbatim quote behind an observation or piece of evidence. */
function QuotePreview({ quote, verified, children }: { quote: string | null; verified: boolean; children: ReactNode }) {
  if (!quote) return <>{children}</>;
  return (
    <Tooltip delayDuration={350}>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right" className="max-w-xs text-left">
        <p className="italic">“{quote}”</p>
        <p className="mt-1 opacity-70">{verified ? "Verified word-for-word in the notes" : "Not verified against the notes"}</p>
      </TooltipContent>
    </Tooltip>
  );
}

// ---------------------------------------------------------------------------
// Left panel: observations
// ---------------------------------------------------------------------------

export function ObservationPanel({
  observations,
  assignments,
  selectedTheme,
  dragging,
  disabled,
  onSelectTheme,
}: {
  observations: Observation[];
  assignments: Map<string, Assignment>;
  selectedTheme: Theme | null;
  dragging: DragData | null;
  disabled: boolean;
  onSelectTheme: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<ObservationFilter>("all");
  const { setNodeRef, isOver } = useDroppable({ id: "unassign" });
  const canUnassign =
    dragging?.kind === "evidence" ||
    (dragging?.kind === "observation" && assignments.has(dragging.painPointId));

  const counts = {
    all: observations.length,
    unassigned: observations.filter((o) => !assignments.has(o.id)).length,
    contradicting: observations.filter((o) => assignments.get(o.id)?.evidence.stance === "contradicting").length,
    selected: selectedTheme ? observations.filter((o) => assignments.get(o.id)?.theme.id === selectedTheme.id).length : 0,
  };
  const term = q.trim().toLowerCase();
  const shown = observations.filter((o) => {
    const a = assignments.get(o.id);
    if (filter === "unassigned" && a) return false;
    if (filter === "selected" && a?.theme.id !== selectedTheme?.id) return false;
    if (filter === "contradicting" && a?.evidence.stance !== "contradicting") return false;
    if (!term) return true;
    return [o.text, o.quote ?? "", o.participant_id, o.participant_role, o.plan_tier].some((t) => t.toLowerCase().includes(term));
  });

  return (
    <section
      ref={setNodeRef}
      aria-label="Observations"
      className={cn(
        "relative flex min-h-0 flex-col overflow-hidden rounded-xl border bg-muted/30 transition-[border-color,background-color] duration-150",
        canUnassign && "border-dashed border-primary/40",
        canUnassign && isOver && "border-primary bg-primary/5",
      )}
    >
      <header className="space-y-2 border-b bg-background px-3 py-3">
        <div className="flex items-baseline justify-between">
          <h3 className="text-sm font-semibold">Observations</h3>
          <span className="text-xs text-muted-foreground tabular-nums">
            {counts.unassigned} of {counts.all} unassigned
          </span>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search observations"
            className="h-8 bg-background pl-8 text-sm"
            aria-label="Search observations"
          />
        </div>
        <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Filter observations">
          {(
            [
              ["all", "All"],
              ["unassigned", "Unassigned"],
              ["contradicting", "Contradicting"],
              ...(selectedTheme ? ([["selected", selectedTheme.code]] as const) : []),
            ] as [ObservationFilter, string][]
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={filter === value}
              onClick={() => setFilter(value)}
              className={cn(
                "inline-flex h-6 items-center gap-1 rounded-full border px-2 text-xs transition-[color,background-color,border-color,transform] duration-150 ease-out active:scale-[0.97]",
                filter === value ? "border-primary/30 bg-primary/8 font-medium text-primary" : "bg-background text-muted-foreground hover:text-foreground",
              )}
            >
              {label} <span className="tabular-nums opacity-70">{counts[value]}</span>
            </button>
          ))}
        </div>
      </header>

      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2">
        {shown.length ? (
          shown.map((o) => (
            <ObservationCard
              key={o.id}
              o={o}
              assignment={assignments.get(o.id)}
              highlighted={Boolean(selectedTheme && assignments.get(o.id)?.theme.id === selectedTheme.id)}
              disabled={disabled}
              onSelectTheme={onSelectTheme}
            />
          ))
        ) : (
          <p className="px-3 py-8 text-center text-sm text-muted-foreground">
            {observations.length ? "No observations match." : "No observations yet. Run synthesis to extract them."}
          </p>
        )}
      </div>

      {canUnassign ? (
        <div
          className={cn(
            "pointer-events-none absolute inset-x-2 bottom-2 flex items-center justify-center gap-2 rounded-lg border border-dashed border-primary/50 bg-background/95 py-3 text-sm text-primary shadow-sm transition-transform duration-150 ease-out",
            isOver && "scale-[1.02]",
          )}
        >
          <Undo2 className="size-4" /> Drop here to remove from its theme
        </div>
      ) : null}
    </section>
  );
}

function ObservationCard({
  o,
  assignment,
  highlighted,
  disabled,
  onSelectTheme,
}: {
  o: Observation;
  assignment?: Assignment;
  highlighted: boolean;
  disabled: boolean;
  onSelectTheme: (id: string) => void;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `obs:${o.id}`,
    data: { kind: "observation", painPointId: o.id, label: o.participant_id } satisfies DragData,
    disabled,
  });
  const contradicting = assignment?.evidence.stance === "contradicting";
  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      aria-roledescription="draggable observation"
      className={cn(
        "group cursor-grab touch-none rounded-lg border bg-background px-2.5 py-2 text-sm outline-none transition-[border-color,box-shadow,opacity] duration-150 select-none hover:border-foreground/20 hover:shadow-xs focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing",
        highlighted && "border-primary/40 bg-primary/[0.03]",
        isDragging && "opacity-40",
        disabled && "cursor-progress",
      )}
    >
      <div className="mb-1 flex items-center gap-1.5">
        <ParticipantTag id={o.participant_id} />
        <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground">{o.participant_role}</span>
        {o.sensitive_tags.length ? <ShieldAlert className="size-3 shrink-0 text-rose-600" aria-label="Sensitive" /> : null}
        <SeverityDots value={o.severity} />
      </div>
      <p className="line-clamp-3 text-[13px] leading-snug text-pretty">{o.text}</p>
      <div className="mt-1.5 flex items-center gap-1.5">
        {assignment ? (
          <button
            type="button"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => onSelectTheme(assignment.theme.id)}
            className={cn(
              "inline-flex max-w-full min-w-0 items-center gap-1 rounded px-1.5 py-px text-[11px] transition-colors",
              contradicting ? "bg-amber-50 text-amber-800 hover:bg-amber-100" : "bg-muted text-muted-foreground hover:bg-muted-foreground/15 hover:text-foreground",
            )}
          >
            {contradicting ? <Scale className="size-3 shrink-0" /> : null}
            <span className="font-mono">{assignment.theme.code}</span>
            <span className="truncate">{assignment.theme.name}</span>
          </button>
        ) : (
          <span className="inline-flex items-center gap-1 text-[11px] text-amber-700">
            <span className="size-1.5 rounded-full bg-amber-400" /> Unassigned
          </span>
        )}
        {o.quote ? (
          <QuotePreview quote={o.quote} verified={o.quote_verified}>
            <span className="ml-auto inline-flex shrink-0 items-center text-muted-foreground" tabIndex={-1}>
              <Quote className="size-3" />
              {o.quote_verified ? <BadgeCheck className="size-3 text-emerald-600" /> : null}
            </span>
          </QuotePreview>
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Center: theme clusters
// ---------------------------------------------------------------------------

export function Cluster({
  theme,
  observations,
  index,
  selected,
  collapsed,
  checked,
  disabled,
  dragging,
  onSelect,
  onToggle,
  onCheck,
  onRename,
}: {
  theme: Theme;
  observations: Map<string, Observation>;
  index: number;
  selected: boolean;
  collapsed: boolean;
  checked: boolean;
  disabled: boolean;
  dragging: DragData | null;
  onSelect: () => void;
  onToggle: () => void;
  onCheck: (checked: boolean) => void;
  onRename: (name: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `theme:${theme.id}`, disabled: theme.status === "merged" });
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(theme.name);
  const contradicting = theme.evidence.filter((e) => e.stance === "contradicting").length;
  const ownItem =
    (dragging?.kind === "evidence" && dragging.themeId === theme.id) ||
    (dragging?.kind === "observation" && theme.evidence.some((e) => e.pain_point_id === dragging.painPointId));
  const dropTarget = Boolean(dragging) && !ownItem;
  const rejected = theme.status === "rejected";

  const save = () => {
    setEditing(false);
    const name = draft.trim();
    if (name.length >= 3 && name !== theme.name) onRename(name);
    else setDraft(theme.name);
  };

  return (
    <section
      ref={setNodeRef}
      aria-label={`Theme ${theme.code}: ${theme.name}`}
      className={cn(
        "enter rounded-xl border bg-background shadow-xs transition-[border-color,box-shadow,background-color,transform] duration-150 ease-out",
        selected && "border-primary/50 shadow-sm",
        rejected && "opacity-60",
        dropTarget && "border-dashed",
        dropTarget && isOver && "scale-[1.01] border-solid border-primary bg-primary/[0.03] shadow-md ring-2 ring-primary/20",
      )}
      style={{ "--i": index } as React.CSSProperties}
    >
      <header className="flex items-start gap-2 px-3 pt-3 pb-2">
        <input
          type="checkbox"
          className="mt-1 size-3.5 shrink-0 accent-[var(--primary)]"
          checked={checked}
          onChange={(e) => onCheck(e.target.checked)}
          aria-label={`Select ${theme.code} for merging`}
          disabled={rejected}
        />
        <button
          type="button"
          onClick={onToggle}
          className="mt-0.5 rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label={collapsed ? `Expand ${theme.code}` : `Collapse ${theme.code}`}
          aria-expanded={!collapsed}
        >
          <ChevronRight className={cn("size-4 transition-transform duration-200 ease-out-strong", !collapsed && "rotate-90")} />
        </button>
        <div className="min-w-0 flex-1 cursor-pointer" onClick={onSelect}>
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-xs text-muted-foreground">{theme.code}</span>
            {editing ? (
              <input
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={save}
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => {
                  if (e.key === "Enter") save();
                  if (e.key === "Escape") {
                    setDraft(theme.name);
                    setEditing(false);
                  }
                }}
                className="min-w-0 flex-1 rounded border bg-background px-1.5 py-0.5 text-sm font-semibold outline-none focus:ring-2 focus:ring-ring"
                aria-label="Theme name"
              />
            ) : (
              <h4
                className="min-w-0 truncate text-sm font-semibold"
                onDoubleClick={(e) => {
                  e.stopPropagation();
                  if (rejected) return;
                  setDraft(theme.name);
                  setEditing(true);
                }}
                title="Double-click to rename"
              >
                {theme.name}
              </h4>
            )}
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-muted">
              <div className="bar-fill h-full rounded-full bg-primary/70" style={{ width: `${Math.max(theme.frequency * 100, 2)}%` }} />
            </div>
            <span className="shrink-0 text-[11px] text-muted-foreground tabular-nums">
              {theme.participant_count}/{theme.total_participants} · {percent(theme.frequency)}
            </span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-1">
            <StatusBadge status={theme.status} />
            {theme.origin === "manual" ? <Badge variant="outline">PM-created</Badge> : null}
            {theme.requires_approval ? (
              <Badge variant="secondary" className="bg-rose-50 text-rose-700">
                <ShieldAlert /> Sensitive
              </Badge>
            ) : null}
            {theme.is_outlier ? (
              <Badge variant="secondary" className="bg-violet-50 text-violet-700">
                <Sparkle /> 1 participant
              </Badge>
            ) : null}
            {contradicting ? (
              <Badge variant="secondary" className="bg-amber-50 text-amber-800">
                <Scale /> {contradicting} contradicting
              </Badge>
            ) : null}
          </div>
        </div>
      </header>

      {collapsed ? (
        <div className="flex flex-wrap gap-1 px-3 pb-3 pl-[3.25rem]">
          {theme.participant_ids.map((p) => (
            <ParticipantTag key={p} id={p} className="bg-muted text-muted-foreground" />
          ))}
          {!theme.participant_ids.length ? <span className="text-xs text-muted-foreground">No evidence yet</span> : null}
        </div>
      ) : (
        <ul className="reveal space-y-1 px-3 pb-3">
          {theme.evidence.map((e) => (
            <EvidenceChip key={e.id} e={e} theme={theme} observation={e.pain_point_id ? observations.get(e.pain_point_id) : undefined} disabled={disabled || rejected} />
          ))}
          {!theme.evidence.length ? (
            <li className="rounded-lg border border-dashed px-3 py-4 text-center text-xs text-muted-foreground">
              Drag observations here
            </li>
          ) : null}
        </ul>
      )}
    </section>
  );
}

function EvidenceChip({
  e,
  theme,
  observation,
  disabled,
}: {
  e: Evidence;
  theme: Theme;
  observation?: Observation;
  disabled: boolean;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `ev:${e.id}`,
    data: {
      kind: "evidence",
      evidenceId: e.id,
      themeId: theme.id,
      painPointId: e.pain_point_id,
      label: e.participant_id,
    } satisfies DragData,
    disabled: disabled || e.id.startsWith("pending-"),
  });
  const contradicting = e.stance === "contradicting";
  return (
    <li>
      <QuotePreview quote={e.quote} verified={e.quote_verified}>
        <div
          ref={setNodeRef}
          {...listeners}
          {...attributes}
          aria-roledescription="draggable evidence"
          className={cn(
            "group flex cursor-grab touch-none items-start gap-1.5 rounded-md border-l-2 bg-muted/40 py-1.5 pr-2 pl-1.5 text-[13px] outline-none transition-[background-color,opacity] duration-150 select-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing",
            contradicting ? "border-amber-500 bg-amber-50/60 hover:bg-amber-50" : "border-primary/40",
            isDragging && "opacity-40",
            e.id.startsWith("pending-") && "animate-pulse",
          )}
        >
          <GripVertical className="mt-0.5 size-3.5 shrink-0 text-muted-foreground/50 group-hover:text-muted-foreground" />
          <ParticipantTag id={e.participant_id} />
          <span className="line-clamp-2 min-w-0 flex-1 leading-snug">{observation?.text ?? e.quote}</span>
          {contradicting ? <Scale className="mt-0.5 size-3.5 shrink-0 text-amber-600" aria-label="Contradicting" /> : null}
        </div>
      </QuotePreview>
    </li>
  );
}

export function NewThemeZone({ dragging, onCreateEmpty }: { dragging: DragData | null; onCreateEmpty: () => void }) {
  const { setNodeRef, isOver } = useDroppable({ id: "new-theme" });
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground transition-[border-color,background-color,transform] duration-150 ease-out",
        dragging && "border-primary/40 text-primary",
        dragging && isOver && "scale-[1.01] border-primary bg-primary/5",
      )}
    >
      <Plus className="size-5" />
      {dragging ? (
        <p>Drop to start a new theme</p>
      ) : (
        <>
          <p>Drag an observation here to start a new theme</p>
          <button type="button" onClick={onCreateEmpty} className="text-xs font-medium text-primary hover:underline">
            or create an empty theme
          </button>
        </>
      )}
    </div>
  );
}

/** What follows the pointer while dragging. */
export function DragPreview({ data, observation }: { data: DragData; observation?: Observation }) {
  return (
    <div className="w-64 rotate-[1.5deg] cursor-grabbing rounded-lg border border-primary/40 bg-background px-2.5 py-2 text-sm shadow-lg">
      <div className="mb-1 flex items-center gap-1.5">
        <ParticipantTag id={data.label} />
        <span className="text-[11px] text-muted-foreground">{data.kind === "evidence" ? "Evidence" : "Observation"}</span>
      </div>
      <p className="line-clamp-2 text-[13px] leading-snug">{observation?.text ?? "Moving evidence"}</p>
    </div>
  );
}
