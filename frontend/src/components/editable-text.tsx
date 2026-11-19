"use client";

import { Pencil } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

/** Read-only text with a hover pencil that turns it into an input; Enter or Save commits. */
export function EditableText({
  value,
  onSave,
  render,
  multiline,
  disabled,
  minLength = 0,
  label,
}: {
  value: string;
  onSave: (value: string) => void;
  render: (value: string) => ReactNode;
  multiline?: boolean;
  disabled?: boolean;
  minLength?: number;
  label: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  if (!editing)
    return (
      <div className="group relative pr-7">
        {render(value)}
        {!disabled ? (
          <Button
            variant="ghost"
            size="icon"
            className="absolute top-0 right-0 size-6 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
            onClick={() => {
              setDraft(value);
              setEditing(true);
            }}
            aria-label={`Edit ${label}`}
          >
            <Pencil className="size-3.5" />
          </Button>
        ) : null}
      </div>
    );
  const ok = draft.trim().length >= minLength && draft.trim() !== value.trim();
  const commit = () => {
    if (ok) onSave(draft.trim());
    setEditing(false);
  };
  return (
    <div className="space-y-2">
      {multiline ? (
        <Textarea autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} rows={4} aria-label={label} />
      ) : (
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") commit();
            if (e.key === "Escape") setEditing(false);
          }}
          aria-label={label}
        />
      )}
      <div className="flex gap-2">
        <Button size="xs" onClick={commit} disabled={!ok}>
          Save
        </Button>
        <Button size="xs" variant="ghost" onClick={() => setEditing(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
