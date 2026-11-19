import { api, type Stance, type Theme } from "@/lib/api";
import type { Command } from "@/lib/command-history";

/**
 * Canvas edits as undoable commands. Each pairs a server call with its exact inverse
 * (see backend app/services/canvas.py). Ids are always passed through `resolve` because
 * a redo can recreate a theme or evidence row under a new id.
 */

/** Drag a piece of evidence from one theme to another. */
export function moveEvidence(evidenceId: string, fromThemeId: string, toThemeId: string, label: string): Command {
  return {
    label,
    run: async (c) => {
      await api.review.moveEvidence(c.resolve(evidenceId), c.resolve(toThemeId));
    },
    undo: async (c) => {
      await api.review.moveEvidence(c.resolve(evidenceId), c.resolve(fromThemeId));
    },
  };
}

/** Drag an observation into a theme (moves it if it already sits in another theme). */
export function attachObservation(painPointId: string, themeId: string, stance: Stance, label: string): Command {
  let evidenceId: string | null = null;
  let movedFrom: string | null = null;
  return {
    label,
    run: async (c) => {
      const r = await api.canvas.attach(c.resolve(themeId), painPointId, stance);
      if (evidenceId) c.remap(evidenceId, r.evidence.id);
      evidenceId = r.evidence.id;
      movedFrom = r.moved_from_theme_id;
    },
    undo: async (c) => {
      if (movedFrom) await api.review.moveEvidence(c.resolve(evidenceId!), c.resolve(movedFrom));
      else await api.canvas.detach(c.resolve(evidenceId!));
    },
  };
}

/** Drop evidence back onto the observation list: it leaves the theme. */
export function detachEvidence(
  evidenceId: string,
  painPointId: string,
  themeId: string,
  stance: Stance,
  label: string,
): Command {
  return {
    label,
    run: async (c) => {
      await api.canvas.detach(c.resolve(evidenceId));
    },
    undo: async (c) => {
      const r = await api.canvas.attach(c.resolve(themeId), painPointId, stance);
      c.remap(c.resolve(evidenceId), r.evidence.id);
    },
  };
}

export function setStance(evidenceId: string, from: Stance, to: Stance, label: string): Command {
  return {
    label,
    run: async (c) => {
      await api.canvas.setStance(c.resolve(evidenceId), to);
    },
    undo: async (c) => {
      await api.canvas.setStance(c.resolve(evidenceId), from);
    },
  };
}

export function editTheme(
  themeId: string,
  field: "name" | "description" | "implication",
  from: string,
  to: string,
  label: string,
): Command {
  return {
    label,
    run: async (c) => {
      await api.review.editTheme(c.resolve(themeId), { [field]: to });
    },
    undo: async (c) => {
      await api.review.editTheme(c.resolve(themeId), { [field]: from });
    },
  };
}

export type NewThemeSeed =
  | { kind: "observation"; painPointId: string }
  | { kind: "evidence"; evidenceId: string; fromThemeId: string };

/** Create a theme, optionally seeded with the item that was dropped on "New theme". */
export function createTheme(
  projectId: string,
  name: string,
  seed: NewThemeSeed | null,
  label: string,
  onCreated?: (id: string) => void,
): Command {
  let themeId: string | null = null;
  let seedEvidence: string | null = null;
  let movedFrom: string | null = null;
  return {
    label,
    run: async (c) => {
      const t = await api.canvas.createTheme(projectId, { name });
      if (themeId) c.remap(themeId, t.id);
      themeId = t.id;
      if (seed?.kind === "observation") {
        const r = await api.canvas.attach(t.id, seed.painPointId, "supporting");
        if (seedEvidence) c.remap(seedEvidence, r.evidence.id);
        seedEvidence = r.evidence.id;
        movedFrom = r.moved_from_theme_id;
      } else if (seed?.kind === "evidence") {
        await api.review.moveEvidence(c.resolve(seed.evidenceId), t.id);
        seedEvidence = seed.evidenceId;
        movedFrom = seed.fromThemeId;
      }
      onCreated?.(t.id);
    },
    undo: async (c) => {
      if (seedEvidence) {
        if (movedFrom) await api.review.moveEvidence(c.resolve(seedEvidence), c.resolve(movedFrom));
        else await api.canvas.detach(c.resolve(seedEvidence));
      }
      await api.canvas.deleteTheme(c.resolve(themeId!));
    },
  };
}

/** Delete a PM-created theme; undo recreates it and puts its observations back. */
export function deleteTheme(projectId: string, theme: Theme, label: string): Command {
  const items = theme.evidence
    .filter((e) => e.pain_point_id)
    .map((e) => ({ evidenceId: e.id, painPointId: e.pain_point_id!, stance: e.stance }));
  return {
    label,
    run: async (c) => {
      await api.canvas.deleteTheme(c.resolve(theme.id));
    },
    undo: async (c) => {
      const t = await api.canvas.createTheme(projectId, { name: theme.name, description: theme.description });
      c.remap(c.resolve(theme.id), t.id);
      for (const item of items) {
        const r = await api.canvas.attach(t.id, item.painPointId, item.stance);
        c.remap(c.resolve(item.evidenceId), r.evidence.id);
      }
    },
  };
}

/** Move selected evidence into a new theme; undo deletes it and the evidence returns. */
export function splitTheme(sourceId: string, evidenceIds: string[], name: string, label: string, onCreated?: (id: string) => void): Command {
  let newId: string | null = null;
  return {
    label,
    run: async (c) => {
      const t = await api.review.split(c.resolve(sourceId), { evidence_ids: evidenceIds.map(c.resolve), name });
      if (newId) c.remap(newId, t.id);
      newId = t.id;
      onCreated?.(t.id);
    },
    undo: async (c) => {
      await api.canvas.deleteTheme(c.resolve(newId!));
    },
  };
}

/** Merge themes into the first one; undo restores every source theme exactly. */
export function mergeThemes(projectId: string, themeIds: string[], name: string | undefined, label: string): Command {
  return {
    label,
    run: async (c) => {
      await api.review.merge(projectId, { theme_ids: themeIds.map(c.resolve), name });
    },
    undo: async (c) => {
      await api.canvas.unmerge(c.resolve(themeIds[0]));
    },
  };
}
