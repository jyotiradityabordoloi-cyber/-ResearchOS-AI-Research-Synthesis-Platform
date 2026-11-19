"use client";

import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import { ApiError } from "@/lib/api";
import { PROJECT_STATUS_LABEL, SYNTHESIS_STATUS_LABEL } from "@/lib/format";
import { cn } from "@/lib/utils";
import { AnimatedNumber } from "@/components/animated-number";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0 space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight text-balance">{title}</h1>
        {description ? <p className="max-w-2xl text-sm text-muted-foreground text-pretty">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  loading,
  href,
  attention,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon: LucideIcon;
  loading?: boolean;
  /** Makes the whole card a link to the view behind the number. */
  href?: string;
  /** Tints the icon when the number needs someone's attention. */
  attention?: boolean;
}) {
  const body = (
    <Card
      className={cn(
        "h-full gap-3 px-5 py-4 shadow-xs",
        href &&
          "transition-[box-shadow,border-color,transform] duration-150 ease-out group-hover/stat:border-primary/30 group-hover/stat:shadow-md group-active/stat:scale-[0.99]",
      )}
    >
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>{label}</span>
        <span
          className={cn(
            "flex size-7 items-center justify-center rounded-md bg-muted transition-colors",
            attention && "bg-amber-50 text-amber-700",
            href && !attention && "group-hover/stat:bg-primary/10 group-hover/stat:text-primary",
          )}
        >
          <Icon className="size-3.5" />
        </span>
      </div>
      {loading ? (
        <Skeleton className="h-8 w-16" />
      ) : (
        <div className="text-3xl font-semibold tracking-tight tabular-nums">
          {typeof value === "number" ? <AnimatedNumber value={value} /> : value}
        </div>
      )}
      {hint ? <div className="text-xs text-muted-foreground">{hint}</div> : null}
    </Card>
  );
  if (!href) return body;
  return (
    <Link
      href={href}
      className="group/stat rounded-xl focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      aria-label={`${label}: open the filtered view`}
    >
      {body}
    </Link>
  );
}

/** Card with a title row; the shared frame for dashboard and workspace panels. */
export function Panel({
  title,
  description,
  action,
  children,
  className,
  bodyClassName,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <Card className={cn("gap-0 py-0 shadow-xs", className)}>
      <div className="flex items-start justify-between gap-3 border-b px-5 py-3.5">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
          {description ? <p className="mt-0.5 text-xs text-muted-foreground">{description}</p> : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      <div className={cn("p-5", bodyClassName)}>{children}</div>
    </Card>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-14 text-center",
        className,
      )}
    >
      <span className="flex size-10 items-center justify-center rounded-full bg-muted">
        <Icon className="size-5 text-muted-foreground" />
      </span>
      <div className="space-y-1">
        <p className="font-medium">{title}</p>
        {description ? <p className="mx-auto max-w-md text-sm text-muted-foreground text-pretty">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof ApiError || error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div className="flex flex-col items-start gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-5 text-sm sm:flex-row sm:items-center">
      <AlertTriangle className="size-5 shrink-0 text-destructive" />
      <p className="flex-1 text-destructive">{message}</p>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="size-3.5" /> Retry
        </Button>
      ) : null}
    </div>
  );
}

const PROJECT_TONE: Record<string, string> = {
  draft: "bg-muted text-muted-foreground",
  collecting: "bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-300",
  in_review: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  completed: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
};

const SYNTH_TONE: Record<string, string> = {
  not_started: "bg-muted text-muted-foreground",
  running: "bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-300",
  completed: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  failed: "bg-destructive/10 text-destructive",
};

export function ProjectStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="secondary" className={PROJECT_TONE[status]}>
      {PROJECT_STATUS_LABEL[status] ?? status}
    </Badge>
  );
}

export function SynthesisStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="secondary" className={SYNTH_TONE[status]}>
      {SYNTHESIS_STATUS_LABEL[status] ?? status}
    </Badge>
  );
}

export function ValidationBadge({ status }: { status: string }) {
  if (status === "valid")
    return (
      <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
        Valid
      </Badge>
    );
  if (status === "invalid") return <Badge variant="destructive">Needs fixes</Badge>;
  return <Badge variant="secondary">Pending</Badge>;
}
