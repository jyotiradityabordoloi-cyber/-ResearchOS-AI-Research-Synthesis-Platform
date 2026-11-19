"use client";

import { useCallback, useRef, useState } from "react";

/**
 * Undo/redo for server-persisted edits. Each command knows how to apply itself and
 * how to reverse itself through the API; nothing is only "pretend" undone locally.
 *
 * Redoing a command that creates something (a theme, an evidence row) yields a new
 * server id. Commands therefore refer to ids through `resolve()`, and record any
 * replacement with `remap(oldId, newId)`, so later commands in the stack still point
 * at the right thing.
 */
export interface Command {
  label: string;
  run: (ctx: HistoryContext) => Promise<void>;
  undo: (ctx: HistoryContext) => Promise<void>;
}

export interface HistoryContext {
  resolve: (id: string) => string;
  remap: (from: string, to: string) => void;
}

export function useCommandHistory({ onSettled }: { onSettled: () => Promise<unknown> }) {
  const [undoStack, setUndo] = useState<Command[]>([]);
  const [redoStack, setRedo] = useState<Command[]>([]);
  const [busy, setBusy] = useState(false);
  const ids = useRef(new Map<string, string>());
  const lock = useRef(false);

  const ctx: HistoryContext = {
    resolve: (id) => {
      let current = id;
      for (let hops = 0; ids.current.has(current) && hops < 50; hops++) current = ids.current.get(current)!;
      return current;
    },
    remap: (from, to) => {
      if (from !== to) ids.current.set(from, to);
    },
  };

  const exec = useCallback(
    async (fn: () => Promise<void>) => {
      if (lock.current) throw new Error("Another change is still saving.");
      lock.current = true;
      setBusy(true);
      try {
        await fn();
      } finally {
        await onSettled();
        lock.current = false;
        setBusy(false);
      }
    },
    [onSettled],
  );

  const perform = useCallback(
    async (cmd: Command) => {
      await exec(() => cmd.run(ctx));
      setUndo((s) => [...s.slice(-49), cmd]);
      setRedo([]);
    },
    // ctx only closes over refs
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [exec],
  );

  const undo = useCallback(async () => {
    const cmd = undoStack[undoStack.length - 1];
    if (!cmd) return null;
    try {
      await exec(() => cmd.undo(ctx));
      setUndo((s) => s.slice(0, -1));
      setRedo((s) => [...s, cmd]);
      return cmd;
    } catch (e) {
      // The server refused (the data changed since). Drop the stale step rather than retry forever.
      setUndo((s) => s.slice(0, -1));
      throw e;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [undoStack, exec]);

  const redo = useCallback(async () => {
    const cmd = redoStack[redoStack.length - 1];
    if (!cmd) return null;
    try {
      await exec(() => cmd.run(ctx));
      setRedo((s) => s.slice(0, -1));
      setUndo((s) => [...s, cmd]);
      return cmd;
    } catch (e) {
      setRedo((s) => s.slice(0, -1));
      throw e;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [redoStack, exec]);

  return {
    perform,
    undo,
    redo,
    busy,
    canUndo: undoStack.length > 0 && !busy,
    canRedo: redoStack.length > 0 && !busy,
    nextUndo: undoStack[undoStack.length - 1]?.label,
    nextRedo: redoStack[redoStack.length - 1]?.label,
  };
}
