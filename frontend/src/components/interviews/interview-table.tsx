"use client";

import Link from "next/link";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Pencil, Trash2 } from "lucide-react";
import { Fragment, useState } from "react";
import { toast } from "sonner";

import { api, type Interview } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ValidationBadge } from "@/components/common";
import { InterviewFormDialog } from "@/components/interviews/interview-form-dialog";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export function InterviewTable({ interviews, showProject = false }: { interviews: Interview[]; showProject?: boolean }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: api.interviews.remove,
    onSuccess: () => {
      qc.invalidateQueries();
      toast.success("Interview deleted");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="overflow-hidden rounded-xl border bg-background">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40 hover:bg-muted/40">
            <TableHead className="w-8" />
            <TableHead>Participant</TableHead>
            {showProject ? <TableHead>Project</TableHead> : null}
            <TableHead className="hidden md:table-cell">Role · Size · Plan</TableHead>
            <TableHead className="hidden lg:table-cell">Pain</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="w-24 text-right">
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {interviews.map((iv) => {
            const open = expanded === iv.id;
            const errors = iv.validation_errors.filter((e) => e.severity === "error");
            return (
              <Fragment key={iv.id}>
                <TableRow className="align-top">
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-7"
                      onClick={() => setExpanded(open ? null : iv.id)}
                      aria-label={open ? "Collapse interview" : "Expand interview"}
                      aria-expanded={open}
                    >
                      <ChevronRight className={cn("size-4 transition-transform duration-200 ease-out-strong", open && "rotate-90")} />
                    </Button>
                  </TableCell>
                  <TableCell className="font-medium">
                    {iv.participant_id || <span className="text-destructive">Missing ID</span>}
                    <div className="text-xs font-normal text-muted-foreground">{timeAgo(iv.created_at)}</div>
                  </TableCell>
                  {showProject ? (
                    <TableCell>
                      <Link href={`/projects/${iv.project_id}`} className="hover:underline">
                        {iv.project_name}
                      </Link>
                    </TableCell>
                  ) : null}
                  <TableCell className="hidden text-muted-foreground md:table-cell">
                    {[iv.participant_role, iv.company_size, iv.plan_tier].filter(Boolean).join(" · ") || "—"}
                  </TableCell>
                  <TableCell className="hidden max-w-md lg:table-cell">
                    <p className="line-clamp-2 whitespace-normal text-muted-foreground">{iv.pain || "—"}</p>
                  </TableCell>
                  <TableCell>
                    <ValidationBadge status={iv.validation_status} />
                    {errors.length > 0 ? (
                      <div className="mt-1 text-xs text-destructive">{errors.length} issue(s)</div>
                    ) : null}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <InterviewFormDialog
                        projectId={iv.project_id}
                        interview={iv}
                        trigger={
                          <Button variant="ghost" size="icon" className="size-8" aria-label="Correct interview">
                            <Pencil className="size-3.5" />
                          </Button>
                        }
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8 text-muted-foreground hover:text-destructive"
                        aria-label="Delete interview"
                        disabled={remove.isPending}
                        onClick={() => {
                          if (confirm(`Delete interview ${iv.participant_id || ""}? This is logged and cannot be undone.`))
                            remove.mutate(iv.id);
                        }}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
                {open ? (
                  <TableRow className="bg-muted/20 hover:bg-muted/20">
                    <TableCell />
                    <TableCell colSpan={showProject ? 6 : 5} className="whitespace-normal">
                      <div className="reveal grid gap-4 py-2 lg:grid-cols-2">
                        <div className="space-y-3 text-sm">
                          {iv.validation_errors.length > 0 ? (
                            <ul className="space-y-1">
                              {iv.validation_errors.map((e) => (
                                <li
                                  key={`${e.field}-${e.message}`}
                                  className={e.severity === "error" ? "text-destructive" : "text-amber-700 dark:text-amber-400"}
                                >
                                  {e.severity === "error" ? "Error" : "Warning"}: {e.message}
                                </li>
                              ))}
                            </ul>
                          ) : null}
                          <Field label="Pain" value={iv.pain} />
                          <Field label="Behavior" value={iv.behavior} />
                          <Field label="Verbatim quote" value={iv.verbatim_quote} quote />
                        </div>
                        <div>
                          <p className="mb-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                            Original notes (read-only)
                          </p>
                          <pre className="max-h-64 overflow-auto rounded-lg border bg-background p-3 font-mono text-xs whitespace-pre-wrap">
                            {iv.raw_content}
                          </pre>
                        </div>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : null}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

function Field({ label, value, quote }: { label: string; value: string; quote?: boolean }) {
  return (
    <div>
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
      {value ? (
        <p className={quote ? "border-l-2 border-primary/40 pl-3 italic" : ""}>{quote ? `“${value}”` : value}</p>
      ) : (
        <p className="text-muted-foreground">—</p>
      )}
    </div>
  );
}
