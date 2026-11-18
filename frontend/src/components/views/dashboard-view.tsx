"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Activity, ClipboardCheck, FolderKanban, Layers, MessagesSquare } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "@/lib/api";
import { useChartAnimation } from "@/lib/motion";
import { timeAgo } from "@/lib/format";
import { EmptyState, ErrorState, PageHeader, StatCard } from "@/components/common";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function DashboardView() {
  const chartMotion = useChartAnimation();
  const { data, error, isPending, refetch } = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });

  const chartData =
    data?.per_project.map((p) => ({
      name: p.project_name.length > 18 ? `${p.project_name.slice(0, 17)}…` : p.project_name,
      Valid: p.valid_interviews,
      "Needs fixes": p.interviews - p.valid_interviews,
    })) ?? [];

  return (
    <div className="space-y-8">
      <PageHeader
        title="Dashboard"
        description="Where your research stands across every project."
        actions={<CreateProjectDialog />}
      />

      {error ? <ErrorState error={error} onRetry={() => refetch()} /> : null}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Research projects" value={data?.total_projects} icon={FolderKanban} loading={isPending} />
        <StatCard
          label="Interviews"
          value={data?.total_interviews}
          hint={data ? `${data.valid_interviews} valid` : undefined}
          icon={MessagesSquare}
          loading={isPending}
        />
        <StatCard label="Themes identified" value={data?.themes_identified} icon={Layers} loading={isPending} />
        <StatCard
          label="Pending human reviews"
          value={data?.pending_reviews}
          icon={ClipboardCheck}
          loading={isPending}
        />
      </div>

      {data && data.total_projects === 0 ? (
        <EmptyState
          icon={FolderKanban}
          title="No research projects yet"
          description="Create a project, add your interview notes, and ResearchOS will help you synthesise them into evidence-backed themes."
          action={<CreateProjectDialog />}
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-5">
          <Card className="shadow-xs lg:col-span-3">
            <CardHeader>
              <CardTitle>Interviews by project</CardTitle>
              <CardDescription>Valid interviews are ready for synthesis.</CardDescription>
            </CardHeader>
            <CardContent className="h-72">
              {isPending ? (
                <Skeleton className="h-full w-full" />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ left: -20, right: 8, top: 8 }}>
                    <CartesianGrid vertical={false} stroke="var(--border)" />
                    <XAxis dataKey="name" tickLine={false} axisLine={false} fontSize={12} interval={0} />
                    <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={12} />
                    <Tooltip
                      cursor={{ fill: "var(--muted)" }}
                      contentStyle={{
                        borderRadius: 8,
                        border: "1px solid var(--border)",
                        background: "var(--popover)",
                        fontSize: 12,
                      }}
                    />
                    <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="Valid" stackId="a" fill="var(--chart-1)" radius={[0, 0, 0, 0]} maxBarSize={44} {...chartMotion} />
                    <Bar dataKey="Needs fixes" stackId="a" fill="var(--chart-4)" radius={[4, 4, 0, 0]} maxBarSize={44} {...chartMotion} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          <Card className="shadow-xs lg:col-span-2">
            <CardHeader>
              <CardTitle>Recent activity</CardTitle>
              <CardDescription>Every human and AI action is logged.</CardDescription>
            </CardHeader>
            <CardContent>
              {isPending ? (
                <div className="space-y-3">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : data && data.recent_activity.length > 0 ? (
                <ol className="space-y-4">
                  {data.recent_activity.slice(0, 8).map((a, i) => (
                    <li key={`${a.kind}-${a.at}-${i}`} className="flex gap-3 text-sm">
                      <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-muted">
                        <Activity className="size-3.5 text-muted-foreground" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="font-medium">
                          {a.title}
                          {a.detail ? <span className="font-normal text-muted-foreground"> · {a.detail}</span> : null}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {a.project_id ? (
                            <Link href={`/projects/${a.project_id}`} className="hover:text-foreground hover:underline">
                              {a.project_name ?? "Deleted project"}
                            </Link>
                          ) : null}
                          {" · "}
                          {timeAgo(a.at)}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-muted-foreground">No activity yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
