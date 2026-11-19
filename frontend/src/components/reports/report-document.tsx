"use client";

import { ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";

import type { ReportContent, ReportSectionKey } from "@/lib/api";
import { formatDate, percent } from "@/lib/format";
import { cn } from "@/lib/utils";
import { OriginalNotesButton } from "@/components/interviews/original-notes-dialog";
import { Badge } from "@/components/ui/badge";

const DEFAULT_ORDER: ReportSectionKey[] = [
  "objective",
  "participants",
  "methodology",
  "themes",
  "frequency",
  "quotes",
  "contradictions",
  "outliers",
  "implications",
  "next_steps",
  "limitations",
];

export const DEFAULT_TITLES: Record<ReportSectionKey, string> = {
  summary: "Executive summary",
  objective: "Research objective",
  participants: "Participant overview",
  methodology: "Research methodology",
  themes: "Top recurring themes",
  frequency: "Participant frequency",
  quotes: "Supporting quotes",
  contradictions: "Contradictory findings",
  outliers: "High-impact outliers",
  implications: "Product implications",
  next_steps: "Recommended next steps",
  limitations: "Limitations",
};

const PRIORITY_STYLE: Record<string, string> = {
  high: "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
  medium: "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  low: "bg-muted text-muted-foreground",
};

function Section({ n, title, children }: { n?: number; title: string; children: ReactNode }) {
  return (
    <section className="space-y-3 border-t pt-6 first:border-0 first:pt-0 print:break-inside-avoid-page">
      <h2 className="text-lg font-semibold tracking-tight">
        {n !== undefined ? <span className="mr-2 text-muted-foreground tabular-nums">{n}.</span> : null}
        {title}
      </h2>
      {children}
    </section>
  );
}

function Muted({ children }: { children: ReactNode }) {
  return <p className="text-sm text-muted-foreground italic">{children}</p>;
}

function Dist({ label, data }: { label: string; data: Record<string, number> }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(data).map(([k, v]) => (
          <Badge key={k} variant="outline">
            {k} <span className="text-muted-foreground">{v}</span>
          </Badge>
        ))}
      </div>
    </div>
  );
}

function Quote({ text, who, interviewId, tone = "primary" }: { text: string; who: string; interviewId: string; tone?: "primary" | "amber" }) {
  return (
    <figure className={cn("border-l-2 pl-3", tone === "amber" ? "border-amber-500" : "border-primary/50")}>
      <blockquote className="text-sm">“{text}”</blockquote>
      <figcaption className="flex items-center gap-2 text-xs text-muted-foreground">
        — {who} <OriginalNotesButton interviewId={interviewId} highlight={text} />
      </figcaption>
    </figure>
  );
}

export function ReportDocument({ c }: { c: ReportContent }) {
  const s = c.sections;
  const p = s.participants;
  const order = c.included_sections ?? DEFAULT_ORDER;
  // The executive summary leads unnumbered; the other sections count 1, 2, 3...
  const numbers = new Map<ReportSectionKey, number>(order.filter((k) => k !== "summary").map((k, i) => [k, i + 1]));
  const blocks: Record<ReportSectionKey, ReactNode> = {
    summary: c.summary ? (
      <div className="space-y-1.5">
        <p className="text-[15px] leading-relaxed whitespace-pre-line text-pretty">{c.summary.text}</p>
        {!c.summary.edited ? <p className="text-xs text-muted-foreground">Assembled from the report&apos;s own numbers.</p> : null}
      </div>
    ) : null,
    objective: (
      <>
        {s.objective.objectives.length ? (
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {s.objective.objectives.map((o) => (
              <li key={o}>{o}</li>
            ))}
          </ul>
        ) : (
          <Muted>No objectives recorded.</Muted>
        )}
        {s.objective.context ? <p className="text-sm text-muted-foreground">{s.objective.context}</p> : null}
      </>
    ),
    participants: (
      <>
        <p className="text-sm">
          <span className="text-2xl font-semibold tabular-nums">{p.unique_participants}</span> unique participants ·{" "}
          {p.valid_interviews} valid of {p.total_interviews} interviews
        </p>
        <div className="grid gap-4 sm:grid-cols-3">
          <Dist label="Roles" data={p.roles} />
          <Dist label="Company size" data={p.company_sizes} />
          <Dist label="Plan tier" data={p.plan_tiers} />
        </div>
        {p.target_segments.length ? (
          <p className="text-sm text-muted-foreground">Target segments: {p.target_segments.join(", ")}</p>
        ) : null}
      </>
    ),
    methodology: (
      <>
        <ul className="list-disc space-y-1.5 pl-5 text-sm">
          {s.methodology.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      </>
    ),
    themes: (
      <>
        {s.themes.length ? (
          <div className="space-y-5">
            {s.themes.map((th) => (
              <div key={th.id} className="space-y-1.5">
                <h3 className="font-semibold">
                  <span className="mr-1.5 font-mono text-xs text-muted-foreground">{th.code}</span>
                  {th.name}
                  {!th.reviewed ? <Badge variant="outline" className="ml-2">Unreviewed</Badge> : null}
                  {th.strategic_flag ? <Badge variant="secondary" className="ml-2">Strategic</Badge> : null}
                </h3>
                <p className="text-sm">{th.description}</p>
                <p className="text-xs text-muted-foreground">
                  {th.participant_count} of {th.total_participants} participants ({percent(th.frequency)}):{" "}
                  {th.participant_ids.join(", ")} · severity {th.severity}/5 · confidence {percent(th.confidence)}
                </p>
                {th.implication ? (
                  <p className="text-sm">
                    <span className="font-medium">Implication: </span>
                    {th.implication}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <Muted>No recurring themes in this report.</Muted>
        )}
      </>
    ),
    frequency: (
      <>
        <div className="space-y-2">
          {s.frequency.map((f) => (
            <div key={f.code} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 text-sm">
              <span className="truncate">
                <span className="mr-1.5 font-mono text-xs text-muted-foreground">{f.code}</span>
                {f.name}
                {f.is_outlier ? <span className="text-muted-foreground"> (outlier)</span> : null}
              </span>
              <span className="tabular-nums text-muted-foreground">
                {f.participant_count} of {f.total_participants} · {percent(f.frequency)}
              </span>
              <div className="col-span-2 h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="bar-fill h-full rounded-full bg-primary" style={{ width: `${Math.max(2, f.frequency * 100)}%` }} />
              </div>
            </div>
          ))}
        </div>
      </>
    ),
    quotes: (
      <>
        <div className="space-y-5">
          {s.quotes.map((q) => (
            <div key={q.code} className="space-y-2">
              <h3 className="text-sm font-semibold">
                <span className="mr-1.5 font-mono text-xs text-muted-foreground">{q.code}</span>
                {q.name}
              </h3>
              {q.quotes.length ? (
                q.quotes.map((x) => <Quote key={x.interview_id + x.quote} text={x.quote} who={x.participant_id} interviewId={x.interview_id} />)
              ) : (
                <Muted>No verified quote available.</Muted>
              )}
            </div>
          ))}
        </div>
      </>
    ),
    contradictions: (
      <>
        {s.contradictions.length ? (
          <div className="space-y-4">
            {s.contradictions.map((x, i) => (
              <div key={i} className="space-y-1.5">
                <p className="text-sm font-medium">
                  <span className="mr-1.5 font-mono text-xs text-muted-foreground">{x.code}</span>
                  {x.name}
                </p>
                {x.quote ? <Quote text={x.quote} who={x.participant_id} interviewId={x.interview_id} tone="amber" /> : null}
                {x.note ? <p className="text-xs text-muted-foreground">{x.note}</p> : null}
              </div>
            ))}
          </div>
        ) : (
          <Muted>No contradicting evidence was found.</Muted>
        )}
      </>
    ),
    outliers: (
      <>
        {s.outliers.length ? (
          <ul className="space-y-3">
            {s.outliers.map((o) => (
              <li key={o.id} className="text-sm">
                <span className="font-medium">{o.name}</span>{" "}
                <Badge variant="secondary" className={o.severity >= 4 ? "bg-violet-50 text-violet-700" : ""}>
                  {o.severity >= 4 ? "High-impact" : "Single participant"} · severity {o.severity}/5
                </Badge>
                <p className="text-muted-foreground">
                  {o.participant_ids.join(", ")}: {o.description}
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <Muted>No single-participant findings.</Muted>
        )}
      </>
    ),
    implications: (
      <>
        {s.implications.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b">
                  <th className="py-2 pr-3 font-medium">Priority</th>
                  <th className="py-2 pr-3 font-medium">Insight & implication</th>
                  <th className="py-2 pr-3 text-right font-medium">Freq.</th>
                  <th className="py-2 pr-3 text-right font-medium">Severity</th>
                  <th className="py-2 text-right font-medium">Strategic</th>
                </tr>
              </thead>
              <tbody>
                {s.implications.map((x, i) => (
                  <tr key={i} className="border-b align-top last:border-0">
                    <td className="py-2 pr-3">
                      <Badge variant="secondary" className={cn("capitalize", PRIORITY_STYLE[x.priority])}>
                        {x.priority}
                      </Badge>
                      {x.overridden ? (
                        <p className="mt-1 text-[11px] text-muted-foreground" title={x.override_reason ?? ""}>
                          manual · was {x.computed_priority}
                        </p>
                      ) : null}
                    </td>
                    <td className="py-2 pr-3">
                      <p className="font-medium">
                        {x.theme_code ? <span className="mr-1.5 font-mono text-xs text-muted-foreground">{x.theme_code}</span> : null}
                        {x.title}
                      </p>
                      <p className="text-muted-foreground">{x.implication || x.statement}</p>
                      {x.pm_comment ? <p className="text-xs text-sky-700 dark:text-sky-400">PM: {x.pm_comment}</p> : null}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">{percent(x.frequency)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{x.severity}/5</td>
                    <td className="py-2 text-right tabular-nums">{x.strategic_relevance}/5</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Muted>No implications included.</Muted>
        )}
      </>
    ),
    next_steps: (
      <>
        <ol className="list-decimal space-y-1.5 pl-5 text-sm">
          {s.next_steps.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ol>
      </>
    ),
    limitations: (
      <>
        <ul className="list-disc space-y-1.5 pl-5 text-sm">
          {s.limitations.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      </>
    ),
  };
  return (
    <article className="space-y-6 rounded-xl border bg-background p-6 shadow-xs sm:p-10">
      <header className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {c.kind === "approved" ? (
            <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
              Approved report
            </Badge>
          ) : (
            <Badge variant="outline">Draft: not all findings reviewed</Badge>
          )}
          {c.run.is_demo ? (
            <Badge variant="secondary" className="bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
              Offline demo mode
            </Badge>
          ) : null}
        </div>
        <p className="text-sm text-muted-foreground">
          {c.project.name} · generated {formatDate(c.generated_at)} · {c.run.provider} ({c.run.model})
        </p>
        {c.excluded.sensitive_pending.length ? (
          <p className="flex items-start gap-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:bg-rose-950 dark:text-rose-300">
            <ShieldAlert className="mt-0.5 size-4 shrink-0" />
            {c.excluded.sensitive_pending.length} sensitive finding(s) withheld until approved:{" "}
            {c.excluded.sensitive_pending.map((x) => `${x.code} ${x.name}`).join("; ")}
          </p>
        ) : null}
        {c.excluded.by_choice?.length ? (
          <p className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
            Left out by the team: {c.excluded.by_choice.map((x) => `${x.code} ${x.name}`).join("; ")}
          </p>
        ) : null}
      </header>

      {order.map((key) => (
        <Section key={key} n={numbers.get(key)} title={c.section_labels?.[key] ?? DEFAULT_TITLES[key]}>
          {blocks[key]}
        </Section>
      ))}
    </article>
  );
}
