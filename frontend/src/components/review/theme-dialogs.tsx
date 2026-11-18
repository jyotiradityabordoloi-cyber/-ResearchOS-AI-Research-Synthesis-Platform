"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { api, type Theme } from "@/lib/api";
import { useReviewRefresh } from "@/components/review/review-controls";
import { Button } from "@/components/ui/button";
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
import { Textarea } from "@/components/ui/textarea";

type DialogProps = { theme: Theme; open: boolean; onOpenChange: (o: boolean) => void };

export function EditThemeDialog({ theme, open, onOpenChange }: DialogProps) {
  const refresh = useReviewRefresh(theme.project_id);
  const [name, setName] = useState(theme.name);
  const [description, setDescription] = useState(theme.description);
  const [implication, setImplication] = useState(theme.implication);
  const [strategic, setStrategic] = useState(theme.strategic_flag);
  const [comment, setComment] = useState("");

  const save = useMutation({
    mutationFn: () => {
      const data: Parameters<typeof api.review.editTheme>[1] = {};
      if (name.trim() !== theme.name) data.name = name.trim();
      if (description !== theme.description) data.description = description;
      if (implication !== theme.implication) data.implication = implication;
      if (strategic !== theme.strategic_flag) data.strategic_flag = strategic;
      if (!Object.keys(data).length) return Promise.resolve(theme);
      return api.review.editTheme(theme.id, { ...data, comment: comment || undefined });
    },
    onSuccess: () => {
      refresh();
      toast.success("Theme updated");
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (o) {
          setName(theme.name);
          setDescription(theme.description);
          setImplication(theme.implication);
          setStrategic(theme.strategic_flag);
        }
        onOpenChange(o);
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>Edit {theme.code}</DialogTitle>
            <DialogDescription>Changes are logged. Participant counts are always computed from evidence.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="t-name">Theme name</Label>
            <Input id="t-name" value={name} onChange={(e) => setName(e.target.value)} minLength={3} required />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="t-desc">Description</Label>
            <Textarea id="t-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="t-impl">Product implication</Label>
            <Textarea id="t-impl" rows={3} value={implication} onChange={(e) => setImplication(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-[var(--primary)]"
              checked={strategic}
              onChange={(e) => setStrategic(e.target.checked)}
            />
            Flag as strategically important
          </label>
          <div className="grid gap-2">
            <Label htmlFor="t-comment">Note for the change history (optional)</Label>
            <Input id="t-comment" value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={save.isPending}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function SplitThemeDialog({ theme, open, onOpenChange }: DialogProps) {
  const refresh = useReviewRefresh(theme.project_id);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const supporting = theme.evidence.filter((e) => e.stance === "supporting");
  const remaining = supporting.filter((e) => !picked.has(e.id)).length;

  const split = useMutation({
    mutationFn: () =>
      api.review.split(theme.id, { evidence_ids: [...picked], name: name.trim(), description: description.trim() }),
    onSuccess: (t) => {
      refresh();
      toast.success(`Created ${t.code}: ${t.name}`);
      onOpenChange(false);
      setPicked(new Set());
      setName("");
      setDescription("");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            split.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>Split {theme.code}</DialogTitle>
            <DialogDescription>
              Select the evidence that belongs to a different problem. It moves into a new theme; counts are recalculated.
            </DialogDescription>
          </DialogHeader>
          <ul className="divide-y rounded-lg border">
            {theme.evidence.map((e) => (
              <li key={e.id}>
                <label className="flex cursor-pointer items-start gap-3 px-3 py-2.5 text-sm hover:bg-muted/40">
                  <input
                    type="checkbox"
                    className="mt-1 size-4 accent-[var(--primary)]"
                    checked={picked.has(e.id)}
                    onChange={(ev) =>
                      setPicked((prev) => {
                        const next = new Set(prev);
                        if (ev.target.checked) next.add(e.id);
                        else next.delete(e.id);
                        return next;
                      })
                    }
                  />
                  <span className="min-w-0">
                    <span className="font-medium">{e.participant_id}</span>
                    {e.stance === "contradicting" ? <span className="text-amber-700"> · contradicting</span> : null}
                    <span className="block text-muted-foreground">{e.note || e.quote}</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <div className="grid gap-2">
            <Label htmlFor="s-name">New theme name</Label>
            <Input id="s-name" value={name} onChange={(e) => setName(e.target.value)} minLength={3} required />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="s-desc">Description (optional)</Label>
            <Textarea id="s-desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          {picked.size && remaining === 0 ? (
            <p className="text-sm text-destructive">Leave at least one supporting item in {theme.code}.</p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!picked.size || remaining === 0 || name.trim().length < 3 || split.isPending}>
              Split into new theme
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function MergeThemesDialog({
  projectId,
  themes,
  open,
  onOpenChange,
  onMerged,
}: {
  projectId: string;
  themes: Theme[];
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onMerged: () => void;
}) {
  const refresh = useReviewRefresh(projectId);
  const [targetId, setTargetId] = useState<string>("");
  const [name, setName] = useState("");
  const [comment, setComment] = useState("");
  const target = themes.find((t) => t.id === targetId) ?? themes[0];
  const participants = new Set(themes.flatMap((t) => t.participant_ids.map((p) => p.toLowerCase())));

  const merge = useMutation({
    mutationFn: () =>
      api.review.merge(projectId, {
        theme_ids: [target.id, ...themes.filter((t) => t.id !== target.id).map((t) => t.id)],
        name: name.trim() || undefined,
        comment: comment || undefined,
      }),
    onSuccess: (t) => {
      refresh();
      toast.success(`Merged into ${t.code}`);
      onOpenChange(false);
      onMerged();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!target) return null;
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (o) {
          setTargetId(themes[0]?.id ?? "");
          setName("");
        }
        onOpenChange(o);
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            merge.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>Merge {themes.length} themes</DialogTitle>
            <DialogDescription>
              All evidence moves into one theme. Participants are counted once: {participants.size} unique participant(s).
            </DialogDescription>
          </DialogHeader>
          <fieldset className="grid gap-2">
            <legend className="mb-1 text-sm font-medium">Keep which theme?</legend>
            {themes.map((t) => (
              <label key={t.id} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="merge-target"
                  className="size-4 accent-[var(--primary)]"
                  checked={target.id === t.id}
                  onChange={() => setTargetId(t.id)}
                />
                <span className="font-mono text-xs text-muted-foreground">{t.code}</span> {t.name}
              </label>
            ))}
          </fieldset>
          <div className="grid gap-2">
            <Label htmlFor="m-name">New name (optional)</Label>
            <Input id="m-name" value={name} placeholder={target.name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="m-comment">Why merge? (optional)</Label>
            <Input id="m-comment" value={comment} onChange={(e) => setComment(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={merge.isPending}>
              Merge
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
