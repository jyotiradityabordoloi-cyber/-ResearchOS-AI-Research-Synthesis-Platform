# ResearchOS

AI-assisted user research synthesis for small product teams. Import interview notes, validate
them, cluster pain points into evidence-backed themes, review and prioritise the findings, generate
a report, and keep everything searchable after the presentation is over.

AI assists; people decide. Every quote is verified against the original notes, counts are computed
in code, sensitive findings need a human sign-off, and every human edit is logged.

**Free to run.** No paid service is needed: an offline demo mode works out of the box, and real AI
runs on local [Ollama](https://ollama.com) or Groq's free tier.

- [Architecture and data flow](docs/ARCHITECTURE.md)
- [Acceptance checklist](docs/ACCEPTANCE.md): every requirement mapped to the app and a test

## Features

| Area | What you can do |
|---|---|
| **Projects** | Objectives, target segments, interview count, synthesis status, change history |
| **Import** | Paste notes or upload `.txt` `.md` `.csv` `.json`; tolerant parser keeps the original text |
| **Validation** | Report before saving: missing Participant ID / Pain / Behavior, filler text, repeated participants, < 5 participants; fix in place |
| **AI synthesis** | 8-stage pipeline: extract → embed → dedupe → cluster → verify quotes → frequency → insights → contradictions & outliers |
| **Themes** | Participant frequency, severity, confidence, verified quotes, contradicting evidence, outlier / sensitive / low-confidence flags |
| **Human review** | Rename, edit, merge, split, move evidence, approve / reject; sensitive findings need acknowledgement + reason |
| **Prioritisation** | Frequency vs impact chart; severity, strategic relevance and confidence kept separate; manual override with reason |
| **Reports** | 11-section draft or approved report; Markdown and PDF export; unapproved sensitive findings withheld |
| **Repository** | Search all projects by keyword, theme name or meaning; filter by project, role, company size, plan tier |

## Quick start (Docker)

```bash
cp .env.example .env        # optional: defaults to the offline demo mode
docker compose up -d --build
```

| Service | URL |
|---|---|
| Web app | http://localhost:3010 |
| API + OpenAPI docs | http://localhost:8010/docs |
| Postgres + pgvector | localhost:5434 (`researchos` / `researchos`) |

### Try it with the sample data

1. **Research Projects → New project.**
2. **Interviews → Import notes**, then paste [samples/interviews-consistent.md](samples/interviews-consistent.md)
   (8 interviews) and [samples/interviews-edge-cases.md](samples/interviews-edge-cases.md).
   Try [samples/interviews-inconsistent.txt](samples/interviews-inconsistent.txt) to see validation fail.
3. **Themes → Run synthesis.** Expand a theme's evidence to see verified quotes and contradictions.
4. Approve, merge or split themes; override priorities on the **Insights** tab.
5. **Reports → Generate draft** or **approved report**, then export Markdown or PDF.
6. Search everything from **Research Repository**.

## AI providers

Set in `.env` and restart the backend. Settings in the app shows what is active.

| `AI_PROVIDER` | Cost | Setup |
|---|---|---|
| `demo` (default) | free, offline | Nothing. Rule-based and deterministic, labelled "demo" everywhere. Good for trying the workflow. |
| `ollama` | free, local | Install Ollama, `ollama pull qwen2.5:3b` (or a larger model for better themes). |
| `groq` | free tier | Set `GROQ_API_KEY`. |

| `EMBEDDING_PROVIDER` | Notes |
|---|---|
| `hash` (default) | Offline; matches words plus a small topic vocabulary. |
| `ollama` | `ollama pull all-minilm` (384-d). Real semantic similarity for clustering and search. |

**Tested with a real local model.** The full pipeline was run on the 12 sample interviews with
Ollama `qwen2.5:3b` (hash embeddings) on a laptop CPU: 67 model calls, all returning valid JSON on
the first try, 11 themes in about 28 minutes. That run shaped three guardrails that apply to every
provider:

| Problem seen with a small model | Guardrail | Before → after |
|---|---|---|
| Often returned no quote | Fall back to the closest sentence from the participant's own notes (still verbatim) | 15 → 6 of 23 pain points without a quote |
| Tagged most themes as pricing / churn | AI tags kept only if the interview text supports them; never tagged from AI-written names | 9 → 3 of 11 themes flagged sensitive |
| Called complaints "contradictions" | Counter-evidence must express a positive experience | 4 → 2 contradictions |

Expect better theme names and grouping from larger models (e.g. `qwen2.5:7b`) and from
`EMBEDDING_PROVIDER=ollama` with `all-minilm`. A CPU-only machine is slow; Groq's free tier is much
faster if your data may leave your machine.

From Docker, the backend reaches Ollama on the host at `host.docker.internal:11434` (already configured).

## Tests

Backend tests run against a real Postgres + pgvector database (`researchos_test`, created by
`backend/db/init.sql`):

```bash
docker compose up -d db
cd backend
pip install -r requirements-dev.txt
pytest                              # all tests
pytest tests/test_acceptance.py -v  # the brief's 7 scenarios + 10 acceptance criteria
```

Frontend checks:

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run build
```

## Local development

```bash
docker compose up -d db                          # Postgres + pgvector only

cd backend
python -m venv .venv && .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8010

cd ../frontend
npm install
npm run dev -- -p 3010
```

## Project layout

```
backend/            FastAPI, SQLAlchemy, Alembic migrations, pytest suite
  app/ai/           LLM providers, engines (LLM + demo), embeddings, output schemas
  app/services/     parser, validation, import, pipeline, synthesis, review, report, PDF, repository
  app/api/routes/   HTTP endpoints
frontend/           Next.js 16, Tailwind, shadcn/ui, TanStack Query, Recharts
samples/            Test datasets for the brief's scenarios
docs/               Architecture and acceptance checklist
```

## Limitations

- **No authentication**: single-workspace MVP with one default user. Don't expose it to the internet as is.
- **Synthesis runs in the API process.** Slow local models keep a worker busy; a job queue is the next step.
- **Demo mode is not real AI.** Use Ollama or Groq for real research.
- **PDF export** uses a built-in Latin-1 font (curly quotes become straight; non-Latin text becomes `?`).

## Troubleshooting (Windows)

- `python -m venv` fails with `No module named 'pip._internal.utils'`: the folder path is too long
  (260 chars). Keep the project in a short path such as `D:\ResearchOS`.
- Docker freezes or builds fail: check free space on the drive holding Docker's disk image
  (Settings → Resources → Advanced → Disk image location).
- Docker Desktop says "file cannot be accessed by the system" on start: quit Docker, delete or rename
  `%LOCALAPPDATA%\Docker\run`, start it again.
