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
