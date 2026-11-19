"use client";

import Link from "next/link";
import { ArrowUpRight, BadgeCheck, Check, Scale, Scissors, ShieldAlert, Sparkle, Trash2, X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { api, type Evidence, type Observation, type Theme } from "@/lib/api";
import { percent } from "@/lib/format";
import { cn } from "@/lib/utils";
import { DecisionButtons, StatusBadge } from "@/components/review/review-controls";
import { ParticipantTag } from "@/components/canvas/canvas-parts";
import { EditableText } from "@/components/editable-text";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * The selected theme: numbers kept apart (participants, frequency, severity, confidence),
 * the participant IDs, the AI-suggested implication, and every quote, with contradicting
 * evidence surfaced in its own section. Edits here go through the canvas history.
 */
export function ThemeDetails({
  theme,
  observations,
  disabled,
  onClose,
  onEdit,
  onToggleStance,
  onSplit,
  onDelete,
  onDecided,
}: {
  theme: Theme;
  observations: Map<string, Observation>;
  disabled: boolean;
  onClose?: () => void;
  onEdit: (field: "name" | "description" | "implication", value: string) => void;
  onToggleStance: (e: Evidence) => void;
  onSplit: (evidenceIds: string[], name: string) => void;
  onDelete: () => void;
  onDecided: () => Promise<unknown>;
}) {
  const [picked, setPicked] = useState<string[]>([]);
  const [splitName, setSplitName] = useState("");
  const supporting = theme.evidence.filter((e) => e.stance === "supporting");
  const contradicting = theme.evidence.filter((e) => e.stance === "contradicting");
  const people = new Map<string, string>();
  for (const e of supporting) if (!people.has(e.participant_id)) people.set(e.participant_id, e.interview_id);
  const rejected = theme.status === "rejected";

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="space-y-2 border-b px-4 pt-3 pb-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-xs text-muted-foreground">{theme.code}</span>
            <StatusBadge status={theme.status} />
            {theme.origin === "manual" ? <Badge variant="outline">PM-created</Badge> : null}
          </div>
          {onClose ? (
            <Button variant="ghost" size="icon" className="size-7" onClick={onClose} aria-label="Close theme details">
              <X />
            </Button>
          ) : null}
        </div>
        <EditableText
          value={theme.name}
          disabled={disabled || rejected}
          minLength={3}
          onSave={(v) => onEdit("name", v)}
          render={(v) => <h3 className="text-base leading-snug font-semibold text-balance">{v}</h3>}
          label="theme name"
        />
        <DecisionButtons
          status={theme.status}
          sensitiveTags={theme.sensitive_tags}
          requiresApproval={theme.requires_approval}
          onDecide={async (payload) => {
            await api.review.reviewTheme(theme.id, payload);
            await onDecided();
          }}
          size="xs"
        />
      </header>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
        <dl className="grid grid-cols-4 gap-2 text-center">
          <Metric label="Participants" value={`${theme.participant_count}/${theme.total_participants}`} />
          <Metric label="Frequency" value={percent(theme.frequency)} />
          <Metric label="Severity" value={`${theme.severity}/5`} />
          <Metric label="Confidence" value={percent(theme.confidence)} hint={theme.origin === "manual" ? "PM-created themes start at a neutral 50%" : undefined} />
        </dl>

        <div className="flex flex-wrap gap-1">
          {theme.requires_approval ? (
            <Badge variant="secondary" className="bg-rose-50 text-rose-700">
              <ShieldAlert /> Sensitive: {theme.sensitive_tags.join(", ").replaceAll("_", " ")}
            </Badge>
          ) : null}
          {theme.is_outlier ? (
            <Badge variant="secondary" className="bg-violet-50 text-violet-700">
              <Sparkle /> Single participant
            </Badge>
          ) : null}
          {theme.evidence_status === "insufficient" ? <Badge variant="outline">No verified quote yet</Badge> : null}
        </div>

        <Block title="Participants">
          {people.size ? (
            <div className="flex flex-wrap gap-1">
              {[...people].map(([p, interviewId]) => (
                <Link key={p} href={`/interviews?interview=${interviewId}`} title="Open this interview">
                  <ParticipantTag id={p} className="transition-colors hover:bg-primary hover:text-primary-foreground" />
                </Link>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground italic">No supporting participants yet.</p>
          )}
        </Block>

        <Block title="Description">
          <EditableText
            value={theme.description}
            multiline
            disabled={disabled || rejected}
            onSave={(v) => onEdit("description", v)}
            render={(v) => <p className="text-sm text-pretty">{v || <span className="text-muted-foreground italic">No description.</span>}</p>}
            label="description"
          />
        </Block>

        <Block title="Implication" hint={theme.human_edited ? "Edited by a person" : "AI-suggested, review before sharing"}>
          <EditableText
            value={theme.implication}
            multiline
            disabled={disabled || rejected}
            onSave={(v) => onEdit("implication", v)}
            render={(v) => <p className="text-sm text-pretty">{v || <span className="text-muted-foreground italic">No implication yet.</span>}</p>}
            label="implication"
          />
        </Block>

        <Block title={`Supporting evidence (${supporting.length})`}>
          <EvidenceList
            items={supporting}
            observations={observations}
            picked={picked}
            onPick={setPicked}
            disabled={disabled || rejected}
            onToggleStance={onToggleStance}
          />
        </Block>

        <Block
          title={`Contradicting evidence (${contradicting.length})`}
          hint={contradicting.length ? "Participants whose notes go against this theme. They are not counted in its frequency." : undefined}
          tone={contradicting.length ? "amber" : undefined}
        >
          {contradicting.length ? (
            <EvidenceList
              items={contradicting}
              observations={observations}
              picked={picked}
              onPick={setPicked}
              disabled={disabled || rejected}
              onToggleStance={onToggleStance}
            />
          ) : (
            <p className="text-sm text-muted-foreground italic">None found. Mark a quote as contradicting if it argues against the theme.</p>
          )}
        </Block>
      </div>

      {picked.length ? (
        <footer className="dock space-y-2 border-t bg-muted/40 px-4 py-3">
          <p className="text-xs text-muted-foreground">
            Split {picked.length} item{picked.length === 1 ? "" : "s"} into a new theme
          </p>
          <form
            className="flex gap-2"
            onSubmit={(ev) => {
              ev.preventDefault();
              onSplit(picked, splitName.trim());
              setPicked([]);
              setSplitName("");
            }}
          >
            <Input
              value={splitName}
              onChange={(e) => setSplitName(e.target.value)}
              placeholder="New theme name"
              className="h-8 bg-background"
              minLength={3}
              required
              aria-label="New theme name"
            />
            <Button type="submit" size="sm" disabled={disabled || splitName.trim().length < 3}>
              <Scissors /> Split
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setPicked([])}>
              Cancel
            </Button>
          </form>
        </footer>
      ) : theme.origin === "manual" ? (
        <footer className="border-t px-4 py-2.5">
          <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-destructive" onClick={onDelete} disabled={disabled}>
            <Trash2 /> Delete this theme
          </Button>
        </footer>
      ) : null}
    </div>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg bg-muted/50 px-1 py-2" title={hint}>
      <dt className="text-[10px] tracking-wide text-muted-foreground uppercase">{label}</dt>
      <dd className="text-sm font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function Block({ title, hint, tone, children }: { title: string; hint?: string; tone?: "amber"; children: ReactNode }) {
  return (
    <section className={cn("space-y-2", tone === "amber" && "rounded-lg border border-amber-200 bg-amber-50/50 p-3")}>
      <div>
        <h4 className={cn("text-xs font-medium tracking-wide uppercase", tone === "amber" ? "text-amber-800" : "text-muted-foreground")}>
          {tone === "amber" ? <Scale className="mr-1 inline size-3" /> : null}
          {title}
        </h4>
        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      </div>
      {children}
    </section>
  );
}

function EvidenceList({
  items,
  observations,
  picked,
  onPick,
  disabled,
  onToggleStance,
}: {
  items: Evidence[];
  observations: Map<string, Observation>;
  picked: string[];
  onPick: (ids: string[]) => void;
  disabled: boolean;
  onToggleStance: (e: Evidence) => void;
}) {
  return (
    <ul className="space-y-2">
      {items.map((e) => {
        const obs = e.pain_point_id ? observations.get(e.pain_point_id) : undefined;
        const isPicked = picked.includes(e.id);
        return (
          <li key={e.id} className={cn("group rounded-lg border bg-background p-2.5 text-sm transition-colors", isPicked && "border-primary/40 bg-primary/[0.03]")}>
            <div className="flex items-center gap-1.5">
              <input
                type="checkbox"
                className="size-3.5 accent-[var(--primary)]"
                checked={isPicked}
                disabled={disabled}
                onChange={(ev) => onPick(ev.target.checked ? [...picked, e.id] : picked.filter((id) => id !== e.id))}
                aria-label={`Select ${e.participant_id}'s evidence to split`}
              />
              <ParticipantTag id={e.participant_id} />
              {e.quote_verified ? (
                <span className="inline-flex items-center gap-0.5 text-[11px] text-emerald-700">
                  <BadgeCheck className="size-3" /> verified
                </span>
              ) : (
                <span className="text-[11px] text-muted-foreground">summary, no verbatim quote</span>
              )}
              <div className="ml-auto flex items-center gap-0.5 opacity-60 transition-opacity group-hover:opacity-100">
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-6"
                  disabled={disabled}
                  onClick={() => onToggleStance(e)}
                  title={e.stance === "supporting" ? "Mark as contradicting" : "Mark as supporting"}
                  aria-label={e.stance === "supporting" ? "Mark as contradicting" : "Mark as supporting"}
                >
                  {e.stance === "supporting" ? <Scale className="size-3.5" /> : <Check className="size-3.5" />}
                </Button>
                <Button asChild variant="ghost" size="icon" className="size-6">
                  <Link href={`/interviews?interview=${e.interview_id}`} aria-label="Open the source interview" title="Open the source interview">
                    <ArrowUpRight className="size-3.5" />
                  </Link>
                </Button>
              </div>
            </div>
            {obs ? <p className="mt-1.5 text-[13px] text-pretty">{obs.text}</p> : null}
            <blockquote className={cn("mt-1 border-l-2 pl-2 text-[13px] text-muted-foreground italic", e.stance === "contradicting" ? "border-amber-500" : "border-primary/40")}>
              “{e.quote}”
            </blockquote>
            {e.note && e.note.trim() !== obs?.text.trim() && e.note.trim() !== e.quote.trim() ? (
              <p className="mt-1 text-xs text-muted-foreground">{e.note}</p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
