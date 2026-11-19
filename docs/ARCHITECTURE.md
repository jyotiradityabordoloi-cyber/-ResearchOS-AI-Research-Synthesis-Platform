# ResearchOS — Architecture

## Principles

1. **Free to run.** No paid service is required. The default AI provider is a deterministic,
   clearly-labelled **offline demo mode**. Real AI runs on **Ollama** (local, free) or **Groq**
   (free tier, needs a key).
2. **Evidence first.** Every AI output links back to an interview and a verbatim quote that is
   checked to exist in the source text.
3. **Arithmetic in Python, interpretation in the LLM.** Frequencies, counts, priority scores and
   thresholds are deterministic code. The LLM extracts, names, explains and judges.
4. **Never corrupt research data.** Raw notes are immutable. A synthesis run is computed in memory
   and written in one transaction; failures leave the previous synthesis untouched.
5. **Humans decide.** Sensitive findings need explicit approval; every human edit is audited.

## Components

```
┌────────────────────────────┐   HTTP/JSON   ┌──────────────────────────────────────┐
│ Next.js 16 (port 3010)     │ ────────────▶ │ FastAPI (port 8010, docs at /docs)   │
│ Tailwind 4 + shadcn/ui     │               │  api/routes/   HTTP endpoints        │
│ TanStack Query, Recharts   │ ◀──────────── │  services/     business logic        │
└────────────────────────────┘               │  ai/           providers & engines   │
                                             │  models/       SQLAlchemy 2.0        │
                                             └───────────────┬──────────────────────┘
                                                             │ psycopg 3
                                             ┌───────────────▼──────────────────────┐
                                             │ PostgreSQL 16 + pgvector (port 5434) │
                                             └──────────────────────────────────────┘
   LLM:        demo (default, offline) │ gemini (free tier) │ ollama (local) │ groq (free tier)
   Embeddings: hash (default, 384-d)   │ gemini-embedding-001 (384-d) │ ollama all-minilm (384-d)
```

### Backend layout

| Path | Responsibility |
|---|---|
| `app/api/routes/` | `projects`, `interviews`, `imports`, `synthesis`, `review`, `reports`, `dashboard`, `system` |
| `app/services/parser.py` | Paste/file parsing (labelled text, CSV, JSON); raw block preserved |
| `app/services/validation.py` | Required fields, meaningful content |
| `app/services/importer.py` | Preview + validation report, import, project readiness |
| `app/services/pipeline.py` | Synthesis stages 1–8 (pure computation, no DB) |
| `app/services/synthesis.py` | Run lifecycle, background execution, atomic persistence |
| `app/services/review.py` | Human review: edit, approve, merge, split, move, override |
| `app/services/report.py`, `pdf.py` | Report assembly (stage 9), Markdown and PDF |
| `app/services/repository.py` | Keyword / theme / semantic search with filters |
| `app/ai/providers.py` | `LLMProvider.generate_json(schema)` with retries; Gemini (rate-paced), Ollama, Groq |
| `app/ai/engine.py` | `AIEngine` interface; `LLMEngine` (prompts) and `DemoEngine` (rules) |
| `app/ai/embeddings.py` | `HashEmbedder` (offline), `GeminiEmbedder` and `OllamaEmbedder` |
| `app/ai/schemas.py` | Pydantic schemas every LLM response is validated against |
| `app/ai/lexicon.py` | Sensitive-topic rules (used with every provider) and demo vocabularies |

### Dashboard (research command centre)

`GET /api/dashboard` returns everything the overview page shows, computed from live rows only
(no stored or hard-coded metrics):

| Field | Source |
|---|---|
| KPI totals, `review_counts`, `sensitive_pending` | Projects, interviews, and themes/insights of each project's active run |
| `interview_activity` | Interviews added per UTC day over the last 30 days, valid vs needs fixes |
| `project_progress` | Per project: collect → validate → synthesise → review → report, last activity from the audit log |
| `review_queue` | Proposed themes and insights, sensitive first, then severity, then frequency |
| `top_findings` | Proposed/approved insights ordered by effective priority (manual override wins) |
| `recent_runs`, `recent_activity` | Synthesis runs and the human-review audit log |

Every KPI and chart links to a filtered view. List pages keep their filters in the query string
(`useUrlState` in `frontend/src/lib/url-state.ts`), e.g. `/interviews?status=valid&created_on=2026-11-18`,
`/insights?status=proposed`, `/projects/{id}?tab=themes`. `GET /api/interviews` accepts
`role`, `company_size`, `plan_tier` (case-insensitive exact match) and `created_on` for these links.

### Project cards and interview explorer

- `GET /api/projects` includes `review_total`, `review_done`, `report_count`, `min_participants`
  and `last_activity_at` (latest of `updated_at` and the audit log), computed in
  `services/projects.project_aggregates`, the same numbers the dashboard uses.
- `GET /api/interviews/facets?project_id=` returns distinct roles, company sizes and plan tiers
  with interview counts.
- `GET /api/interviews/{id}/findings` traces an interview forward (`services/interview_findings.py`):
  pain points the active run extracted from it, the live themes that cite it (with stance and
  quotes) and the insights built on those themes. Together with evidence → interview links this
  makes traceability two-way.
- The explorer keeps every filter and the selected interview in the URL
  (`/interviews?plan_tier=Team&interview=<id>`), so evidence anywhere in the app can deep-link to
  its source interview ("Open in interview explorer", participant links on theme evidence).

### Theme exploration canvas

Project → Themes → *Canvas* (`components/canvas/`). Observations are the pain points the active
run extracted (`GET /api/projects/{id}/observations`); a theme's evidence links back to its
observation through `pain_point_id`, so the left panel knows what is assigned where.

Drag-and-drop uses `@dnd-kit/core` (pointer + keyboard sensors). A drop is shown in its new place
immediately and confirmed by the server; frequency and flags are always recomputed in Python.

Undo/redo is a client-side command stack (`lib/command-history.ts`, `lib/canvas-commands.ts`).
Every command pairs a server call with its exact server-side inverse, so undo really changes the
data and is audited like any other edit:

| Action | Endpoint | Inverse |
|---|---|---|
| Drag observation into a theme | `POST /api/themes/{id}/observations` | `DELETE /api/evidence/{id}` (or move back if it was moved) |
| Drag evidence to another theme | `POST /api/evidence/{id}/move` | move back |
| Drop evidence on the observation list | `DELETE /api/evidence/{id}` | re-attach the observation |
| Mark supporting / contradicting | `PATCH /api/evidence/{id}` | set it back |
| Rename / edit description or implication | `PATCH /api/themes/{id}` | previous value |
| New theme (optionally from a dropped item) | `POST /api/projects/{id}/themes` | `DELETE /api/themes/{id}` (PM-created only) |
| Split | `POST /api/themes/{id}/split` | delete the new theme; evidence returns to its source |
| Merge | `POST /api/projects/{id}/themes/merge` | `POST /api/themes/{id}/unmerge`, which restores sources, moved and de-duplicated evidence, wording and statuses from the merge's audit entry |

Redo can recreate a theme or evidence row under a new id; the history keeps an id remap so later
commands still point at the right rows. The history lives for the browser session. Regrouping still
sends an approved theme back to review, and undo does not silently re-approve it (except unmerge,
which restores the exact evidence that was approved). AI themes keep at least one supporting item;
PM-created themes may be emptied and deleted.

### Insight review

`components/insights/insight-review.tsx`, used by the project Insights tab and `/insights`.

- `GET /api/projects/{id}/insights` and `GET /api/insights` add review context in three batched
  queries (`add_context`): theme name, participant count, supporting / contradicting evidence
  counts and the number of reviewer comments.
- `GET /api/insights/{id}/evidence`: the quotes behind an insight (through its theme) with each
  participant's role, company size and plan tier.
- `GET /api/insights/{id}/history` and `POST /api/insights/{id}/comments`: reviewer comments are
  `review_comment` entries in the audit log, shown in one thread with decisions.
- `POST /api/insights/{id}/sensitive`: flag pricing / churn / competitive switching by hand with
  a reason. Tags are only ever added (detected sensitivity can't be switched off) and an approved
  insight goes back to review, because sensitive approval needs an explicit acknowledgement.
- Filters (`priority`, `status`, `sensitive`) and the open card (`insight`) live in the URL, so the
  dashboard, interview explorer and chart can open one specific insight.

### Research copilot

`POST /api/projects/{id}/copilot` (`services/copilot.py`, UI in `components/copilot/copilot.tsx`).

- **Context, not memory.** Each question builds a context from the database: objectives, target
  segments, participant coverage by role / size / plan, live themes with real participant counts,
  up to 60 quotes (selected theme first, then contradictions, then verified quotes) with each
  participant's segment, top insights, and the selected interview. Every item has a key: `T3`,
  `E12`, `I2`, `P`. The UI sends the theme / insight / interview the user is looking at.
- **Citations are checked.** The model must cite keys; the server keeps only single keys that
  exist in the context (`[T1-T9]` ranges and invented keys are removed) and returns each
  citation's quote, participant and link target. The model's own citation list is ignored.
- **Honest modes.** `mode` is `ai` (written by the model), `demo` (AI_PROVIDER=demo: fixed rules
  over the same data, e.g. contradictions, segment views, theme comparison, coverage gaps,
  strongest verified quotes, keyword lookup) or `fallback` (the provider failed; same rules plus a
  notice with the error). The UI labels each answer; nothing is generated in the browser.
- **Interactive budget.** `COPILOT_TIMEOUT_SECONDS` (30) and `COPILOT_MAX_RETRIES` (2) keep a waiting
  person from sitting through synthesis-style retries; on Gemini a timeout also switches to
  `GEMINI_FALLBACK_MODEL`. The answer reports the model that actually replied.
- Privacy: in AI mode the question and the project's quotes go to the configured provider, which
  the panel states under the input box.

### Report builder

`/projects/{id}/reports/new` (`components/views/report-builder-view.tsx`).

- `POST /api/projects/{id}/reports/preview` builds a report exactly as `POST /api/projects/{id}/reports`
  would save it, without saving: `{ title, content, markdown }`. Both accept `options`:
  `sections` (subset of `summary` + the 11 standard sections, always rendered in standard order),
  `excluded_theme_ids` and `executive_summary`.
- Leaving a theme out also drops its insights, and the theme is named in Limitations and in
  `excluded.by_choice`, so a report never silently omits a finding. Sensitive findings still need
  approval (they can be approved from the builder); options can't force them in. An approved report
  with every approved theme excluded is refused.
- Without a custom summary, `summarize()` assembles one from the report's own numbers (no AI).
  `summary.edited` records whether the team wrote their own; the audit entry records the sections,
  left-out themes and whether the summary was edited.
- Markdown, PDF and the web view render `included_sections` in order: the executive summary leads
  unnumbered, the remaining sections are numbered 1..n. Reports saved before the builder have no
  `included_sections` and render the original eleven.

### Frontend design system

- Tokens live in `frontend/src/app/globals.css`: indigo primary, neutral surfaces, chart palette and
  three motion curves (`--ease-out-strong`, `--ease-in-out-strong`, `--ease-drawer`).
- Shared building blocks in `components/common.tsx`: `PageHeader`, `Panel` (titled card),
  `StatCard` (count-up number, optional link), `EmptyState`, `ErrorState`, status badges.
- Motion helpers: `.enter` (staggered entrance via `@starting-style`), `.reveal`, `.bar-fill`, `.dock`;
  `useChartAnimation()` and `AnimatedNumber` respect `prefers-reduced-motion`.

## Data model

| Table | Purpose |
|---|---|
| `users` | Team members (single default user in this MVP) |
| `research_projects` | Objectives, segments, status, synthesis status, `active_run_id` |
| `interviews` | Structured fields + immutable `raw_content`, validation result |
| `synthesis_runs` | Status, stage, provider, warnings, stats, error |
| `pain_points` | Atomic pain per interview: quote, verification, severity, tags, `vector(384)` |
| `themes` | Clustered findings: participants, frequency, confidence, flags, status, `vector(384)` |
| `theme_evidence` | Theme ↔ interview ↔ quote, `supporting` or `contradicting` |
| `insights` | Severity, strategic relevance, score, manual override, comment, status, `vector(384)` |
| `human_reviews` | Append-only audit log with before/after JSON |
| `research_reports` | Markdown + structured JSON, draft or approved |

Embeddings use HNSW cosine indexes. "Live" findings are those in a project's active run plus manual
items; themes from older runs are kept for history but read-only.

## Data flow

```
Paste / upload ─▶ parse ─▶ validation report ─▶ PM fixes ─▶ save (raw notes immutable)
                                                                  │
                                    readiness check (≥ 5 valid participants, or exploratory)
                                                                  ▼
 1 extract ─▶ 2 embed ─▶ 3 similarity + per-participant dedupe ─▶ 4 cluster + name
 ─▶ 5 verify quotes ─▶ 6 frequency (Python) ─▶ 7 insights ─▶ 8 contradictions / outliers / sensitivity
                                                                  │  one transaction
                                                                  ▼
             human review (approve, merge, split, move, override; all audited)
                                                                  ▼
              report (draft / approved) ─▶ Markdown / PDF       repository search
```

## Synthesis stages

| # | Stage | Engine | Notes |
|---|---|---|---|
| 1 | Extraction | LLM → `ExtractionResult` | Positive statements are not pain points |
| 2 | Embeddings | Embedder | 384-d, normalised |
| 3 | Similarity | numpy | Near-duplicates from the same participant collapse (≥ 0.9) |
| 4 | Clustering | Python + LLM | Average-linkage agglomerative into small, precise clusters → the LLM groups clusters that describe the same problem (it sees numbered clusters of text only; Python validates the partition) → the LLM names each theme; a theme it rates as incoherent is re-split more tightly |
| 5 | Evidence validation | Python | Quote must appear verbatim in the interview |
| 6 | Frequency | Python | Unique participants ÷ total participants |
| 7 | Insights | LLM → `InsightDraft` | Severity and strategic relevance judged separately from frequency |
| 8 | Contradictions & outliers | LLM + Python | Top-3 similar non-supporting interviews checked; singletons flagged |
| 9 | Report | Python | 11 sections from reviewed data |

LLM calls retry on malformed JSON (feeding back the validation error) and transient transport
errors (timeouts, 429, 5xx). Other 4xx errors fail fast.

## Reliability

- Synthesis runs execute in the API process (background task). On startup, any run left `running`
  by a restart is marked failed; nothing was committed, so nothing is lost.
- Concurrent runs for a project are refused (409). Runs older than 30 minutes are treated as abandoned.
- Unhandled errors return a generic JSON 500 and are logged server-side.
- Docker: non-root users, health checks, `restart: unless-stopped`; frontend waits for a healthy API.

## Known limitations

- **No authentication.** Single-workspace MVP with one default user; put it behind a VPN or add auth before
  exposing it.
- **In-process jobs.** Long runs on slow local models keep one API worker busy; a job queue would be the next step.
- **Demo mode** is rule-based: good for trying the workflow, not for real research.
- **Small local models** (e.g. 3B) can produce weaker theme names and need more retries than larger models.
- **PDF export** uses a built-in Latin-1 font: curly quotes become straight, non-Latin text becomes `?`.

## Ports

| Service | Host port |
|---|---|
| Web | 3010 |
| API | 8010 (OpenAPI docs at `/docs`) |
| Postgres | 5434 |
