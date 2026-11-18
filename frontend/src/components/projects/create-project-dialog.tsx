"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

/** Splits a textarea into one entry per line (commas also accepted for segments). */
export function splitLines(value: string, allowCommas = false): string[] {
  return value
    .split(allowCommas ? /[\n,]/ : /\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function CreateProjectDialog({ trigger }: { trigger?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [objectives, setObjectives] = useState("");
  const [segments, setSegments] = useState("");
  const router = useRouter();
  const qc = useQueryClient();

  const create = useMutation({
    mutationFn: api.projects.create,
    onSuccess: (project) => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      toast.success("Research project created");
      setOpen(false);
      setName("");
      setDescription("");
      setObjectives("");
      setSegments("");
      router.push(`/projects/${project.id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button>
            <Plus className="size-4" /> New project
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <form
          className="grid gap-5"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate({
              name,
              description,
              objectives: splitLines(objectives),
              target_segments: splitLines(segments, true),
            });
          }}
        >
          <DialogHeader>
            <DialogTitle>New research project</DialogTitle>
            <DialogDescription>Define what you want to learn and who you are talking to.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="project-name">Name</Label>
            <Input
              id="project-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Q1 onboarding research"
              required
              maxLength={200}
              autoFocus
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="project-description">Context</Label>
            <Textarea
              id="project-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Why this research, and what decision it informs."
              rows={2}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="project-objectives">Objectives</Label>
            <Textarea
              id="project-objectives"
              value={objectives}
              onChange={(e) => setObjectives(e.target.value)}
              placeholder={"One per line, e.g.\nUnderstand why trials don't convert"}
              rows={3}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="project-segments">Target user segments</Label>
            <Input
              id="project-segments"
              value={segments}
              onChange={(e) => setSegments(e.target.value)}
              placeholder="SMB, Mid-market, Enterprise"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending || !name.trim()}>
              {create.isPending ? "Creating…" : "Create project"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
