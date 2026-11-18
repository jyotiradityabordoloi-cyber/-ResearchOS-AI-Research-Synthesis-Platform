# Acceptance checklist

How each requirement from the brief is met, where it lives, and which automated test proves it.
Run the whole suite with:

```bash
docker compose up -d db
cd backend && pytest tests/test_acceptance.py -v
```

## Final acceptance criteria

| # | A user can… | In the app | Test |
|---|---|---|---|
| 1 | Create a research project | Research Projects → **New project** | `test_final_acceptance_criteria_end_to_end` |
| 2 | Import at least 8 interview notes | Project → Interviews → **Import notes** (paste or upload `.txt/.md/.csv/.json`) | same, plus `test_phase2_import.py` |
| 3 | Validate interview structure | Import screen validation report; Overview → **Synthesis readiness** | same, plus `test_spec_2_…` |
| 4 | Run AI-powered theme clustering | Themes → **Run synthesis** | same, plus `test_phase3_synthesis.py` |
| 5 | See participant frequency and supporting quotes | Themes: frequency chart, theme cards, evidence | `test_spec_1_…` |
| 6 | Review contradictory evidence | Theme card evidence: Supporting vs Contradicting | `test_spec_3_…` |
| 7 | Flag high-impact outliers | "High-impact outlier" badge; report section 8 | `test_spec_4_…` |
| 8 | Edit and approve insights | Theme ⋯ menu, Approve / Reject, Insights → Edit / override | same, plus `test_phase4_review.py` |
| 9 | Generate a research report | Reports tab → **Generate draft / approved**, export Markdown or PDF | same, plus `test_phase5_reports_repository.py` |
| 10 | Search previously generated insights | Research Repository: keyword, theme, semantic + filters | same |

## Test scenarios from the brief

| Test | Expected | Result | Test function |
|---|---|---|---|
| 1. Eight consistent notes | 4–6 themes, participant frequency, supporting quotes | ✅ 5 themes from `samples/interviews-consistent.md`, every theme has verified quotes | `test_spec_1_eight_consistent_interviews_give_reasonable_themes` |
| 2. Inconsistent format | Validation failure, no synthesis | ✅ 4 of 5 interviews fail; synthesis refused (422), no run created | `test_spec_2_inconsistent_format_fails_validation_and_blocks_synthesis` |
| 3. Contradictory interview | Supporting and opposing evidence visible | ✅ P09's positive setup experience shown against the data-connection theme | `test_spec_3_contradictory_interview_shows_both_sides` |
| 4. Single-participant high-impact insight | Flagged as outlier, not discarded | ✅ P10's SOC 2 blocker kept, severity ≥ 4, in report section 8 | `test_spec_4_single_participant_high_impact_is_flagged_not_discarded` |
| 5. Duplicate pain points, same participant | Participant counted once | ✅ duplicates merged; frequency uses unique participants | `test_spec_5_duplicate_pain_points_count_participant_once` |
| 6. AI provider failure | Error handling, no corrupted data | ✅ late failure and unreachable provider both leave the previous synthesis, reports and interviews intact | `test_spec_6_provider_failure_handled_without_corrupting_data` |
| 7. Sensitive business themes | Pricing / churn / competitive switching need approval | ✅ excluded from approved reports until signed off with acknowledgement + reason | `test_spec_7_sensitive_themes_need_human_approval` |

## Human fallback rules

| Rule | Behaviour | Where |
|---|---|---|
| A. < 5 interviews | Warning in import + readiness; standard synthesis refused unless run as exploratory (`force`) | `services/importer.py`, `services/synthesis.py` |
| B. < 3 themes from 8+ interviews | Run warning "notes may be inconsistent… review" | `services/pipeline.py` |
| C. Theme from one participant | Kept, flagged; high-impact if severity ≥ 4 | `services/pipeline.py` |
| D. Pricing, churn, competitive switching | Approval needs acknowledgement + reason; never in reports until approved | `services/review.py`, `services/report.py` |
| E. Contradictory evidence | Shown beside supporting evidence; report section 7 | `services/pipeline.py` |
| F. Low-confidence clustering | Flagged; PM can merge, split or move evidence | `services/review.py` |

## Other guarantees

- **No fabricated quotes or participants.** The AI never receives or returns participant IDs. Every quote is
  checked word-for-word against the original notes; unverified quotes are discarded and counted.
- **Arithmetic in code.** Frequencies, counts and priority scores are computed in Python.
- **Raw notes are immutable.** Corrections change structured fields only; every change is in the audit log.
- **Atomic synthesis.** Results are written in one transaction; failed or interrupted runs change nothing.
- **Every human action is audited** with before/after values (project Overview → Change history).

## Live AI check

The pipeline was also run against a real local model (Ollama `qwen2.5:3b`, hash embeddings) on the
12 sample interviews: valid JSON on every call, no fabricated quotes. The guardrails it led to
(quote fallback from notes, grounded sensitive tags, complaint-vs-contradiction check) are covered by
`tests/test_llm_guardrails.py`. See the README's "AI providers" section for numbers and caveats.
