"use client";

import { useQuery } from "@tanstack/react-query";
import { Brain, CheckCircle2, CircleAlert, Database, Waypoints } from "lucide-react";

import { api, API_URL, type ProviderStatus } from "@/lib/api";
import { ErrorState, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

function ProviderCard({ title, icon: Icon, status }: { title: string; icon: typeof Brain; status: ProviderStatus }) {
  return (
    <Card className="shadow-xs">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon className="size-4" /> {title}
        </CardTitle>
        <CardDescription>
          {status.name} · <span className="font-mono">{status.model}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex flex-wrap gap-2">
          {status.available ? (
            <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
              <CheckCircle2 /> Available
            </Badge>
          ) : (
            <Badge variant="destructive">
              <CircleAlert /> Unavailable
            </Badge>
          )}
          {status.is_demo ? (
            <Badge variant="secondary" className="bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
              Local demo mode
            </Badge>
          ) : null}
        </div>
        <p className="text-muted-foreground">{status.detail}</p>
      </CardContent>
    </Card>
  );
}

export function SettingsView() {
  const ai = useQuery({ queryKey: ["ai-settings"], queryFn: api.aiSettings });
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="AI providers are configured with environment variables on the backend so they can be swapped without code changes."
      />
      {ai.error ? <ErrorState error={ai.error} onRetry={() => ai.refetch()} /> : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {ai.data ? (
          <>
            <ProviderCard title="Language model" icon={Brain} status={ai.data.llm} />
            <ProviderCard title="Embeddings" icon={Waypoints} status={ai.data.embeddings} />
          </>
        ) : ai.isPending ? (
          <>
            <Skeleton className="h-44" />
            <Skeleton className="h-44" />
          </>
        ) : null}
        <Card className="shadow-xs">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="size-4" /> Backend
            </CardTitle>
            <CardDescription className="font-mono">{API_URL}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {health.data ? (
              <>
                <p>
                  Database: <span className="font-medium">{health.data.database}</span>
                </p>
                <p>
                  pgvector: <span className="font-medium">{health.data.pgvector ?? "not installed"}</span>
                </p>
              </>
            ) : health.error ? (
              <p className="text-destructive">{(health.error as Error).message}</p>
            ) : (
              <Skeleton className="h-10" />
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="shadow-xs">
        <CardHeader>
          <CardTitle>Switching providers</CardTitle>
          <CardDescription>Everything here is free. Set these in the repository&apos;s <code>.env</code> and restart the backend.</CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-lg border bg-muted/40 p-4 font-mono text-xs leading-relaxed">
{`# Local, free, private (recommended)
AI_PROVIDER=ollama
OLLAMA_MODEL=qwen2.5:3b
EMBEDDING_PROVIDER=ollama
OLLAMA_EMBED_MODEL=all-minilm      # ollama pull all-minilm

# Hosted free tier
AI_PROVIDER=groq
GROQ_API_KEY=gsk_...

# Offline demo (default)
AI_PROVIDER=demo
EMBEDDING_PROVIDER=hash`}
          </pre>
          {ai.data ? (
            <p className="mt-3 text-sm text-muted-foreground">
              Standard synthesis requires at least {ai.data.min_interviews_for_synthesis} valid participants.
            </p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
