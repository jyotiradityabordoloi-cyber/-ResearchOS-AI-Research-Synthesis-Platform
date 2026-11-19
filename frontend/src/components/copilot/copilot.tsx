"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowUp, Bot, CircleAlert, Eraser, Layers, Lightbulb, MessagesSquare, Sparkles, User, X } from "lucide-react";
import { Fragment, Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { api, type CopilotAnswer, type CopilotCitation } from "@/lib/api";
import { useLiveSearchParams } from "@/lib/url-state";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

type Turn =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; answer: CopilotAnswer; projectId: string }
  | { id: number; role: "error"; text: string; question: string };

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/**
 * Contextual research copilot: a right-side panel available on every page. It reads the
 * current project, theme, insight and interview from the URL, sends the question to the
 * backend (which grounds it in that project's data), and renders the answer with
 * clickable citations. It never fabricates an answer locally.
 */
export function Copilot() {
  return (
    <Suspense fallback={null}>
      <CopilotInner />
    </Suspense>
  );
}

function useCopilotContext() {
  const pathname = usePathname();
  const params = useLiveSearchParams();
  const routeProject = pathname.match(/^\/projects\/([0-9a-f-]{36})/)?.[1] ?? null;
  const interviewId = params.get("interview");
  const interview = useQuery({
    queryKey: ["interview", interviewId],
    queryFn: () => api.interviews.get(interviewId!),
    enabled: Boolean(interviewId),
  });
  const queryProject = params.get("project_id");
  return {
    projectId: routeProject ?? interview.data?.project_id ?? (queryProject && queryProject !== "all" ? queryProject : null),
    themeId: routeProject ? params.get("theme") : null,
    insightId: routeProject ? params.get("insight") : null,
    interviewId: interview.data ? interviewId : null,
    interviewLabel: interview.data?.participant_id ?? null,
  };
}

function CopilotInner() {
  const [open, setOpen] = useState(false);
  const route = useCopilotContext();
  const projects = useQuery({ queryKey: ["projects", {}], queryFn: () => api.projects.list() });
  const ai = useQuery({ queryKey: ["ai-settings"], queryFn: api.aiSettings, staleTime: 60_000 });
  const [picked, setPicked] = useState<string | null>(null);
  // Which focus the user dismissed; a different theme/interview/insight is used again.
  const [cleared, setCleared] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const nextId = useRef(1);
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  const synthesised = (projects.data ?? []).filter((p) => p.synthesis_status === "completed" || p.theme_count > 0);
  const projectId =
    route.projectId ?? picked ?? [...synthesised].sort((a, b) => (b.last_activity_at ?? "").localeCompare(a.last_activity_at ?? ""))[0]?.id ?? null;
  const project = projects.data?.find((p) => p.id === projectId);

  const themes = useQuery({
    queryKey: ["themes", projectId, { showRejected: false }],
    queryFn: () => api.synthesis.themes(projectId!),
    enabled: Boolean(projectId) && open,
  });
  const insight = useQuery({
    queryKey: ["insights", projectId],
    queryFn: () => api.synthesis.insights(projectId!),
    enabled: Boolean(projectId && route.insightId) && open,
  });
  const focusInsight = insight.data?.find((i) => i.id === route.insightId);
  const themeId = route.themeId ?? focusInsight?.theme_id ?? null;
  const theme = themes.data?.find((t) => t.id === themeId);

  const focusKey = [themeId, route.interviewId, route.insightId].join("|");
  const useFocus = cleared !== focusKey;
  const clearFocus = () => setCleared(focusKey);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const ask = useMutation({
    mutationFn: (question: string) => {
      const history = turns
        .filter((t) => t.role !== "error")
        .slice(-6)
        .map((t) => (t.role === "user" ? { role: "user" as const, content: t.text } : { role: "assistant" as const, content: (t as Extract<Turn, { role: "assistant" }>).answer.answer }));
      return api.copilot.ask(projectId!, {
        question,
        theme_id: useFocus && themeId ? themeId : undefined,
        insight_id: useFocus && route.insightId ? route.insightId : undefined,
        interview_id: useFocus && route.interviewId ? route.interviewId : undefined,
        history,
      });
    },
    onSuccess: (answer) => setTurns((t) => [...t, { id: nextId.current++, role: "assistant", answer, projectId: projectId! }]),
    onError: (e: Error, question) =>
      setTurns((t) => [...t, { id: nextId.current++, role: "error", text: e.message, question }]),
  });

  const send = (question: string) => {
    const q = question.trim();
    if (!q || !projectId || ask.isPending) return;
    setTurns((t) => [...t, { id: nextId.current++, role: "user", text: q }]);
    setText("");
    ask.mutate(q);
  };

  const suggestions = useMemo(() => {
    const t = useFocus ? theme : undefined;
    const others = (themes.data ?? []).filter((x) => x.id !== t?.id);
    return [
      t ? `Why is ${t.code} “${t.name}” important?` : "Why is the top theme important?",
      t ? `Show contradictory evidence for ${t.code}.` : "Show contradictory evidence.",
      "What do enterprise users think?",
      t && others[0] ? `Compare ${t.code} and ${others[0].code}.` : "Compare two themes.",
      "Identify missing research coverage.",
      t ? `Summarize the strongest evidence for ${t.code}.` : "Summarize the strongest evidence.",
    ];
  }, [theme, themes.data, useFocus]);

  const llm = ai.data?.llm;
  const demo = llm?.is_demo ?? false;

  return (
    <>
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed right-5 bottom-5 z-40 inline-flex h-11 items-center gap-2 rounded-full bg-primary pr-4 pl-3.5 text-sm font-medium text-primary-foreground shadow-lg transition-[transform,box-shadow] duration-150 ease-out hover:shadow-xl active:scale-[0.97]"
          aria-label="Open research copilot"
        >
          <Sparkles className="size-4" /> Ask copilot
          <kbd className="hidden rounded bg-primary-foreground/15 px-1.5 py-px font-sans text-[10px] sm:inline">{isMac ? "⌘J" : "Ctrl J"}</kbd>
        </button>
      ) : null}

      <aside
        aria-label="Research copilot"
        aria-hidden={!open}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
        inert={!open}
        className={cn(
          "copilot-panel fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l bg-background shadow-2xl sm:w-[420px]",
          open ? "translate-x-0" : "pointer-events-none translate-x-full",
        )}
      >
        <header className="space-y-2.5 border-b px-4 py-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Sparkles className="size-4" />
              </span>
              <div>
                <h2 className="text-sm font-semibold">Research copilot</h2>
                <p className="text-[11px] text-muted-foreground">
                  {llm ? (demo ? "Demo mode: rule-based answers, no AI model" : `${llm.name} · ${llm.model}`) : "Checking AI provider…"}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-0.5">
              {turns.length ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button variant="ghost" size="icon" className="size-7" onClick={() => setTurns([])} aria-label="Clear conversation">
                      <Eraser className="size-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Clear conversation</TooltipContent>
                </Tooltip>
              ) : null}
              <Button variant="ghost" size="icon" className="size-7" onClick={() => setOpen(false)} aria-label="Close copilot">
                <X />
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {route.projectId ? (
              <Badge variant="secondary" className="max-w-full truncate">
                {project?.name ?? "This project"}
              </Badge>
            ) : (
              <Select value={projectId ?? ""} onValueChange={(v) => setPicked(v)}>
                <SelectTrigger size="sm" className="h-7 max-w-60 text-xs" aria-label="Project to ask about">
                  <SelectValue placeholder="Choose a project" />
                </SelectTrigger>
                <SelectContent>
                  {(projects.data ?? []).map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {theme && useFocus ? (
              <ContextChip icon={Layers} label={`${theme.code} ${theme.name}`} onClear={clearFocus} />
            ) : null}
            {route.interviewLabel && useFocus ? (
              <ContextChip icon={MessagesSquare} label={`Interview ${route.interviewLabel}`} onClear={clearFocus} />
            ) : null}
            {focusInsight && useFocus ? (
              <ContextChip icon={Lightbulb} label={focusInsight.title} onClear={clearFocus} />
            ) : null}
          </div>
        </header>

        <div ref={scroller} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
          {!projectId ? (
            <p className="py-10 text-center text-sm text-muted-foreground">Create and synthesise a project to ask questions about it.</p>
          ) : turns.length === 0 ? (
            <div className="space-y-4 py-2">
              <p className="text-sm text-muted-foreground text-pretty">
                Ask about this project&apos;s themes, quotes and insights. Answers cite their sources so you can check every claim.
              </p>
              <Suggestions items={suggestions} onPick={send} disabled={ask.isPending} />
            </div>
          ) : (
            turns.map((t) =>
              t.role === "user" ? (
                <UserBubble key={t.id} text={t.text} />
              ) : t.role === "error" ? (
                <div key={t.id} className="enter rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-sm">
                  <p className="flex items-center gap-1.5 font-medium text-destructive">
                    <CircleAlert className="size-4" /> The copilot couldn&apos;t answer
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">{t.text}</p>
                  <Button size="xs" variant="outline" className="mt-2" onClick={() => send(t.question)}>
                    Try again
                  </Button>
                </div>
              ) : (
                <AssistantMessage key={t.id} answer={t.answer} projectId={t.projectId} onNavigate={() => setOpen(window.innerWidth >= 1280)} />
              ),
            )
          )}
          {ask.isPending ? <Thinking provider={demo ? null : llm?.name ?? null} /> : null}
          {turns.length > 0 && !ask.isPending ? (
            <Suggestions
              items={suggestions.filter((q) => !turns.some((t) => t.role === "user" && t.text === q)).slice(0, 3)}
              onPick={send}
              compact
            />
          ) : null}
        </div>

        <form
          className="space-y-1.5 border-t px-3 py-3"
          onSubmit={(e) => {
            e.preventDefault();
            send(text);
          }}
        >
          <div className="relative">
            <Textarea
              ref={input}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(text);
                }
              }}
              rows={2}
              maxLength={1000}
              placeholder={projectId ? "Ask about themes, segments, evidence…" : "Choose a project first"}
              disabled={!projectId}
              className="resize-none pr-11 text-sm"
              aria-label="Ask the copilot"
            />
            <Button
              type="submit"
              size="icon"
              className="absolute right-2 bottom-2 size-7 rounded-full"
              disabled={!text.trim() || !projectId || ask.isPending}
              aria-label="Send question"
            >
              <ArrowUp className="size-4" />
            </Button>
          </div>
          <p className="px-1 text-[11px] text-muted-foreground">
            {demo
              ? "Demo mode answers come from fixed rules over your data. Connect a provider in Settings for open questions."
              : `Your question and this project's quotes are sent to ${llm?.name ?? "the AI provider"}. Check citations before sharing.`}
          </p>
        </form>
      </aside>
    </>
  );
}

function ContextChip({ icon: Icon, label, onClear }: { icon: typeof Layers; label: string; onClear: () => void }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1 rounded-md border bg-primary/5 py-0.5 pr-0.5 pl-1.5 text-primary">
      <Icon className="size-3 shrink-0" />
      <span className="max-w-48 truncate">{label}</span>
      <button type="button" onClick={onClear} className="rounded p-0.5 hover:bg-primary/10" aria-label={`Stop using ${label} as context`}>
        <X className="size-3" />
      </button>
    </span>
  );
}

function Suggestions({ items, onPick, disabled, compact }: { items: string[]; onPick: (q: string) => void; disabled?: boolean; compact?: boolean }) {
  return (
    <div className={cn("flex flex-col gap-1.5", compact && "border-t pt-3")}>
      {compact ? <p className="text-[11px] text-muted-foreground">Try next</p> : null}
      {items.map((q) => (
        <button
          key={q}
          type="button"
          disabled={disabled}
          onClick={() => onPick(q)}
          className="rounded-lg border bg-background px-3 py-2 text-left text-sm transition-[border-color,background-color,transform] duration-150 ease-out hover:border-primary/30 hover:bg-primary/5 active:scale-[0.99] disabled:opacity-50"
        >
          {q}
        </button>
      ))}
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="enter flex justify-end gap-2">
      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-3 py-2 text-sm text-primary-foreground text-pretty">{text}</p>
      <span className="mt-1 flex size-6 shrink-0 items-center justify-center rounded-full bg-muted">
        <User className="size-3.5 text-muted-foreground" />
      </span>
    </div>
  );
}

function Thinking({ provider }: { provider: string | null }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
      <span className="flex size-6 items-center justify-center rounded-full bg-primary/10">
        <Bot className="size-3.5 animate-pulse text-primary" />
      </span>
      {provider ? `Reading the evidence and asking ${provider}…` : "Looking through your data…"}
      {seconds > 2 ? <span className="tabular-nums">{seconds}s</span> : null}
    </div>
  );
}

const MODE: Record<CopilotAnswer["mode"], { label: string; className: string }> = {
  ai: { label: "AI answer", className: "bg-primary/10 text-primary" },
  demo: { label: "Demo mode · rule-based", className: "bg-amber-50 text-amber-800" },
  fallback: { label: "AI unavailable · rule-based", className: "bg-amber-50 text-amber-800" },
};

function AssistantMessage({ answer, projectId, onNavigate }: { answer: CopilotAnswer; projectId: string; onNavigate: () => void }) {
  const byKey = new Map(answer.citations.map((c) => [c.key, c]));
  return (
    <div className="enter flex gap-2">
      <span className="mt-1 flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <Sparkles className="size-3.5 text-primary" />
      </span>
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary" className={MODE[answer.mode].className}>
            {MODE[answer.mode].label}
          </Badge>
          {answer.mode === "ai" ? <span className="text-[11px] text-muted-foreground">{answer.model}</span> : null}
        </div>
        {answer.notice ? <p className="rounded-md bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900">{answer.notice}</p> : null}
        <RichAnswer text={answer.answer} citations={byKey} projectId={projectId} onNavigate={onNavigate} />
        {answer.citations.length ? (
          <details className="group rounded-lg border bg-muted/30 text-xs">
            <summary className="cursor-pointer list-none px-2.5 py-1.5 text-muted-foreground select-none hover:text-foreground">
              {answer.citations.length} source{answer.citations.length === 1 ? "" : "s"}
            </summary>
            <ul className="space-y-1.5 border-t px-2.5 py-2">
              {answer.citations.map((c) => (
                <li key={c.key} className="flex gap-1.5">
                  <CitationLink c={c} projectId={projectId} onNavigate={onNavigate} />
                  <span className="min-w-0 text-muted-foreground">
                    {c.quote ? `“${c.quote}”` : c.label}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>
    </div>
  );
}

function citationHref(c: CopilotCitation, projectId: string) {
  if (c.kind === "theme" && c.theme_id) return `/projects/${projectId}?tab=themes&theme=${c.theme_id}`;
  if (c.kind === "insight" && c.insight_id) return `/projects/${projectId}?tab=insights&insight=${c.insight_id}`;
  if (c.interview_id) return `/interviews?interview=${c.interview_id}`;
  return `/projects/${projectId}`;
}

function CitationLink({ c, projectId, onNavigate }: { c: CopilotCitation; projectId: string; onNavigate: () => void }) {
  const router = useRouter();
  const tone =
    c.kind === "theme"
      ? "bg-primary/10 text-primary"
      : c.stance === "contradicting"
        ? "bg-amber-100 text-amber-800"
        : c.kind === "insight"
          ? "bg-sky-50 text-sky-700"
          : "bg-muted text-foreground";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={citationHref(c, projectId)}
          onClick={(e) => {
            e.preventDefault();
            onNavigate();
            router.push(citationHref(c, projectId));
          }}
          className={cn("inline-flex h-4.5 shrink-0 items-center rounded px-1 align-baseline font-mono text-[10px] font-medium transition-opacity hover:opacity-80", tone)}
        >
          {c.key}
        </Link>
      </TooltipTrigger>
      <TooltipContent side="left" className="max-w-72">
        <p className="font-medium">{c.label}</p>
        {c.quote ? <p className="mt-0.5 italic opacity-80">“{c.quote}”</p> : null}
        <p className="mt-0.5 opacity-60">Click to open</p>
      </TooltipContent>
    </Tooltip>
  );
}

/** Paragraphs, "- " bullets, **bold** and [T2]/[E5] citation chips. No HTML is ever injected. */
function RichAnswer({
  text,
  citations,
  projectId,
  onNavigate,
}: {
  text: string;
  citations: Map<string, CopilotCitation>;
  projectId: string;
  onNavigate: () => void;
}) {
  const inline = (s: string): ReactNode[] =>
    s.split(/(\[(?:T\d+|E\d+|I\d+|P)\]|\*\*[^*]+\*\*)/g).map((part, i) => {
      const cite = part.match(/^\[(T\d+|E\d+|I\d+|P)\]$/);
      if (cite) {
        const c = citations.get(cite[1]);
        return c ? (
          <Fragment key={i}>
            {" "}
            <CitationLink c={c} projectId={projectId} onNavigate={onNavigate} />
          </Fragment>
        ) : null;
      }
      if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
      return <Fragment key={i}>{part}</Fragment>;
    });

  const blocks = text.trim().split(/\n{2,}/);
  return (
    <div className="space-y-2 text-sm leading-relaxed text-pretty">
      {blocks.map((block, b) => {
        const lines = block.split("\n");
        const bullets = lines.filter((l) => /^\s*[-•*]\s+/.test(l));
        if (bullets.length && bullets.length >= lines.length - 1) {
          const head = lines.length > bullets.length ? lines[0] : null;
          return (
            <div key={b} className="space-y-1">
              {head ? <p>{inline(head)}</p> : null}
              <ul className="list-disc space-y-1 pl-4 marker:text-muted-foreground">
                {bullets.map((l, i) => (
                  <li key={i}>{inline(l.replace(/^\s*[-•*]\s+/, ""))}</li>
                ))}
              </ul>
            </div>
          );
        }
        return (
          <p key={b}>
            {lines.map((l, i) => (
              <Fragment key={i}>
                {i ? <br /> : null}
                {inline(l)}
              </Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
