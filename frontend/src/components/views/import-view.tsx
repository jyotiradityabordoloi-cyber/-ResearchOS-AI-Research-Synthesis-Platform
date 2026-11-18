"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardPaste,
  FileUp,
  Loader2,
  RotateCcw,
  ScanSearch,
  Upload,
  X,
} from "lucide-react";
import { useCallback, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { api, type ImportItem, type ImportPreview, type InterviewFields, type ValidationIssue } from "@/lib/api";
import { ErrorState, PageHeader } from "@/components/common";
import { ReviewCard, type ReviewItem } from "@/components/interviews/review-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

const TEMPLATE = `Participant ID: P01
Participant Role: Product Manager
Company Size: 50-200
Plan Tier: Pro
Pain: What hurts, in the participant's words where possible.
Behavior: What they do today to cope with it.
Verbatim Quote: "An exact quote from the interview."

---
Participant ID: P02
Participant Role:
Company Size:
Plan Tier:
Pain:
Behavior:
Verbatim Quote:
`;
const ACCEPT = ".txt,.md,.markdown,.csv,.json";

type Filter = "all" | "invalid" | "valid";

function toReviewItems(preview: ImportPreview): ReviewItem[] {
  const stamp = Date.now();
  return preview.items.map((p) => ({
    key: `${stamp}-${p.index}`,
    preview: p,
    fields: { ...p.fields },
    status: p.status,
    issues: p.issues.filter((i) => !p.context_issues.some((c) => c.field === i.field && c.message === i.message)),
    validating: false,
  }));
}

function toImportItem(item: ReviewItem): ImportItem {
  return {
    fields: item.fields,
    parsed_fields: item.preview.fields,
    raw_content: item.preview.raw_content,
    source: item.preview.source,
    source_filename: item.preview.source_filename,
  };
}

export function ImportView() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const project = useQuery({ queryKey: ["project", id], queryFn: () => api.projects.get(id) });

  const [mode, setMode] = useState<"paste" | "upload">("paste");
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [savedCount, setSavedCount] = useState(0);
  const [filter, setFilter] = useState<Filter>("all");

  const check = useMutation({
    mutationFn: () => (mode === "paste" ? api.imports.previewText(id, text) : api.imports.previewFiles(id, files)),
    onSuccess: (data) => {
      setPreview(data);
      setItems(toReviewItems(data));
      setSavedCount(0);
      // Default to "all": with a status filter, a card would vanish mid-edit as it becomes valid.
      setFilter("all");
      if (!data.items.length && !data.file_errors.length) toast.warning("No interviews found in the input.");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const invalidate = useCallback(() => {
    for (const key of [["project", id], ["projects"], ["interviews"], ["dashboard"], ["audit", id], ["validation", id]])
      qc.invalidateQueries({ queryKey: key });
  }, [qc, id]);

  const save = useMutation({
    mutationFn: (batch: ReviewItem[]) => api.imports.save(id, batch.map(toImportItem)),
    onSuccess: (result, batch) => {
      const savedKeys = new Set(batch.filter((_, i) => !result.skipped.some((s) => s.index === i)).map((b) => b.key));
      setItems((prev) => prev.filter((it) => !savedKeys.has(it.key)));
      setSavedCount((n) => n + result.created.length);
      invalidate();
      if (result.created.length) toast.success(`Saved ${result.created.length} interview(s)`);
      if (result.skipped.length) toast.warning(`${result.skipped.length} skipped: ${result.skipped[0].reason}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const update = (key: string, patch: Partial<ReviewItem>) =>
    setItems((prev) => prev.map((it) => (it.key === key ? { ...it, ...patch } : it)));

  const counts = useMemo(
    () => ({
      valid: items.filter((i) => i.status === "valid").length,
      invalid: items.filter((i) => i.status === "invalid").length,
      validating: items.some((i) => i.validating),
    }),
    [items],
  );
  const visible = items.filter((i) => filter === "all" || i.status === filter);

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      return [...prev, ...Array.from(list).filter((f) => !names.has(f.name))];
    });
  };

  const reset = () => {
    setPreview(null);
    setItems([]);
    setSavedCount(0);
  };

  if (project.error) return <ErrorState error={project.error} onRetry={() => project.refetch()} />;
  if (project.isPending) return <Skeleton className="h-96 w-full" />;
  const p = project.data;
  const canCheck = mode === "paste" ? text.trim().length > 0 : files.length > 0;

  return (
    <div className="space-y-6 pb-24">
      <Link
        href={`/projects/${p.id}`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" /> {p.name}
      </Link>
      <PageHeader
        title="Import interviews"
        description="Paste notes or upload files. Every interview is checked before anything is saved, and you can fix problems here."
      />

      {!preview ? (
        <Card className="shadow-xs">
          <CardContent>
            <Tabs value={mode} onValueChange={(v) => setMode(v as "paste" | "upload")} className="gap-4">
              <TabsList>
                <TabsTrigger value="paste">
                  <ClipboardPaste className="size-4" /> Paste notes
                </TabsTrigger>
                <TabsTrigger value="upload">
                  <FileUp className="size-4" /> Upload files
                </TabsTrigger>
              </TabsList>

              <TabsContent value="paste" className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
                  <p>
                    One interview per block, separated by <code className="rounded bg-muted px-1">---</code> or a new{" "}
                    <code className="rounded bg-muted px-1">Participant ID:</code> line.
                  </p>
                  <Button variant="outline" size="sm" onClick={() => setText((t) => (t.trim() ? `${t}\n\n---\n` : "") + TEMPLATE)}>
                    Insert template
                  </Button>
                </div>
                <Textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={16}
                  className="font-mono text-xs"
                  placeholder={TEMPLATE}
                  aria-label="Interview notes"
                />
              </TabsContent>

              <TabsContent value="upload" className="space-y-3">
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => fileInput.current?.click()}
                  onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && fileInput.current?.click()}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragging(false);
                    addFiles(e.dataTransfer.files);
                  }}
                  className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors ${
                    dragging ? "border-primary bg-primary/5" : "hover:bg-muted/40"
                  }`}
                >
                  <Upload className="size-6 text-muted-foreground" />
                  <p className="font-medium">Drop files here or click to choose</p>
                  <p className="text-sm text-muted-foreground">
                    .txt, .md, .csv or .json · up to 20 files · 2 MB each
                  </p>
                  <input
                    ref={fileInput}
                    type="file"
                    accept={ACCEPT}
                    multiple
                    hidden
                    onChange={(e) => {
                      addFiles(e.target.files);
                      e.target.value = "";
                    }}
                  />
                </div>
                {files.length ? (
                  <ul className="divide-y rounded-lg border text-sm">
                    {files.map((f) => (
                      <li key={f.name} className="flex items-center justify-between gap-2 px-3 py-2">
                        <span className="truncate">{f.name}</span>
                        <span className="flex items-center gap-2 text-xs text-muted-foreground">
                          {(f.size / 1024).toFixed(1)} KB
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-7"
                            aria-label={`Remove ${f.name}`}
                            onClick={() => setFiles((prev) => prev.filter((x) => x.name !== f.name))}
                          >
                            <X className="size-3.5" />
                          </Button>
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}
                <p className="text-xs text-muted-foreground">
                  CSV needs a header row (e.g. Participant ID, Pain, Behavior). JSON should be a list of objects.
                </p>
              </TabsContent>
            </Tabs>
            <div className="mt-4 flex justify-end">
              <Button onClick={() => check.mutate()} disabled={!canCheck || check.isPending}>
                {check.isPending ? <Loader2 className="size-4 animate-spin" /> : <ScanSearch className="size-4" />}
                Check notes
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card className="shadow-xs">
            <CardHeader>
              <CardTitle>Validation report</CardTitle>
              <CardDescription>
                {preview.summary.total} interview(s) found
                {savedCount ? ` · ${savedCount} saved` : ""}. Nothing is saved until you choose to.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-3 gap-3 text-center sm:max-w-md">
                <Metric label="Ready" value={counts.valid} tone="text-emerald-600" />
                <Metric label="Need fixes" value={counts.invalid} tone={counts.invalid ? "text-destructive" : ""} />
                <Metric label="Saved" value={savedCount} />
              </div>
              {preview.file_errors.length ? (
                <Alert variant="destructive">
                  <AlertTriangle />
                  <AlertTitle>Some files could not be read</AlertTitle>
                  <AlertDescription>
                    <ul className="list-disc pl-4">
                      {preview.file_errors.map((e) => (
                        <li key={e.filename}>
                          <span className="font-medium">{e.filename}</span>: {e.message}
                        </li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              ) : null}
              {!preview.summary.sample_sufficient ? (
                <Alert className="border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
                  <AlertTriangle />
                  <AlertTitle>Sample too small for standard synthesis</AlertTitle>
                  <AlertDescription className="text-amber-800 dark:text-amber-300">
                    After this import the project would have {preview.summary.valid_participants_after_import} valid
                    participant(s); at least {preview.summary.min_required} are needed.
                  </AlertDescription>
                </Alert>
              ) : null}
              {preview.summary.duplicate_participants.length ? (
                <p className="text-sm text-muted-foreground">
                  Repeated participant IDs in this import: {preview.summary.duplicate_participants.join(", ")}. They are
                  kept but counted once.
                </p>
              ) : null}
            </CardContent>
          </Card>

          {items.length ? (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                {(["all", "invalid", "valid"] as Filter[]).map((f) => (
                  <Button
                    key={f}
                    size="sm"
                    variant={filter === f ? "secondary" : "ghost"}
                    onClick={() => setFilter(f)}
                    aria-pressed={filter === f}
                  >
                    {f === "all" ? `All (${items.length})` : f === "invalid" ? `Need fixes (${counts.invalid})` : `Ready (${counts.valid})`}
                  </Button>
                ))}
              </div>
              {visible.map((item) => (
                <ReviewCard
                  key={item.key}
                  item={item}
                  saving={save.isPending}
                  onChange={(fields: InterviewFields) => update(item.key, { fields, validating: true })}
                  onValidated={(status, issues: ValidationIssue[]) => update(item.key, { status, issues, validating: false })}
                  onSave={() => save.mutate([item])}
                  onRemove={() => setItems((prev) => prev.filter((x) => x.key !== item.key))}
                />
              ))}
              {!visible.length ? (
                <p className="py-6 text-center text-sm text-muted-foreground">Nothing in this filter.</p>
              ) : null}
            </div>
          ) : (
            <Card className="items-center gap-3 py-10 text-center shadow-xs">
              <CheckCircle2 className="size-8 text-emerald-600" />
              <p className="font-medium">{savedCount ? `All done: ${savedCount} interview(s) saved.` : "Nothing left to review."}</p>
              <div className="flex gap-2">
                <Button variant="outline" onClick={reset}>
                  Import more
                </Button>
                <Button asChild>
                  <Link href={`/projects/${p.id}`}>Back to project</Link>
                </Button>
              </div>
            </Card>
          )}

          {items.length ? (
            <div className="fixed inset-x-0 bottom-0 z-20 border-t bg-background/95 backdrop-blur lg:left-64">
              <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-10">
                <p className="text-sm text-muted-foreground">
                  {counts.invalid
                    ? `${counts.invalid} interview(s) need fixes and won't be saved until corrected.`
                    : "All interviews are ready."}
                </p>
                <div className="flex gap-2">
                  <Button variant="ghost" onClick={reset}>
                    <RotateCcw className="size-4" /> Start over
                  </Button>
                  <Button
                    onClick={() => save.mutate(items.filter((i) => i.status === "valid"))}
                    disabled={!counts.valid || counts.validating || save.isPending}
                  >
                    {save.isPending ? <Loader2 className="size-4 animate-spin" /> : null}
                    Save {counts.valid} ready interview{counts.valid === 1 ? "" : "s"}
                  </Button>
                </div>
              </div>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function Metric({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-lg border px-3 py-2">
      <div className={`text-2xl font-semibold tabular-nums ${tone}`}>{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
