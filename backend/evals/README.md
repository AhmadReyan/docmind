# Retrieval evaluation harness

This directory contains DocMind's retrieval quality gate: a golden set of 15
questions over the three seed documents in `backend/seed_data/`, and a runner
that exercises the *real* pipeline — the app's own extraction, chunking,
embedding provider, and the hybrid `retrieve()` function — against a real
pgvector Postgres.

## Running it

From `backend/` (requires Docker for the disposable database):

```bash
python -m evals.run_eval
python -m evals.run_eval --top-k 5 --min-hit-rate 0.8
python -m evals.run_eval --summary "$GITHUB_STEP_SUMMARY"   # CI
```

| Flag | Default | Meaning |
|---|---|---|
| `--top-k` | `5` | Chunks retrieved per question |
| `--min-hit-rate` | `0.0` | Exit with code 1 if `hit_rate@k` is below this — the CI gate |
| `--summary` | — | Append a markdown results table to this path (e.g. `$GITHUB_STEP_SUMMARY`) |

Environment:

- `EVAL_DATABASE_URL` — use an existing pgvector Postgres instead of starting
  a testcontainer (migrations are applied to it).
- `EMBEDDING_PROVIDER` — which embedding provider to evaluate (default
  `local`, i.e. fastembed; no API key needed).

## Metrics

- **hit@k** — a case counts as a *hit* if any of the top-k retrieved chunks
  (a) belongs to the case's `expected_document` **and** (b) contains at least
  one `answer_keyword` (case-insensitive, whitespace-normalized). This checks
  that retrieval surfaced content that could actually ground the answer, not
  just anything from the right file.
- **hit_rate@k** — fraction of cases that are hits. This is the CI-gated
  number.
- **MRR** (mean reciprocal rank) — average of `1/rank` of the first hit chunk
  (0 for misses). Sensitive to *ordering*: two runs with the same hit rate can
  differ in MRR if one puts the grounding chunk at rank 1 and the other at
  rank 5.

## The golden set

`golden_set.json` is a list of cases:

```json
{
  "id": "aurora-pto-days",
  "question": "How many PTO days do employees at Aurora Dynamics get each year?",
  "expected_document": "aurora-employee-handbook.md",
  "answer_keywords": ["24 days", "pto", "2 days per month"]
}
```

The 15 cases are deliberately mixed:

- **Easy lookups** — question wording closely matches the source text;
  lexical (FTS) retrieval alone should handle these.
- **Paraphrased questions** — no meaningful keyword overlap with the source
  phrasing (e.g. "change their login credentials" vs. "password rotation").
  These only pass through semantic (vector) retrieval and are the reason the
  hybrid design exists.
- **Cross-section questions** (2) — the answer spans two sections of one
  document; tests that retrieval doesn't collapse onto a single passage.

### Adding a case

1. Make sure the fact **literally exists** in one seed document — the harness
   matches keywords against chunk text, so paraphrased keywords will never
   hit.
2. Pick 3–6 lowercase `answer_keywords` that a good answer's source content
   must contain. Prefer distinctive numbers and phrases (`"$499"`,
   `"800 ms"`), avoid words that appear in every document.
3. Keep keywords short enough not to straddle chunk boundaries; a case needs
   only *one* keyword to match, so include several from the same passage.
4. Run `python -m evals.run_eval` locally and check the new case's rank.

If you edit a seed document, re-run the eval: keyword drift (rewording a fact)
is the most common way to silently break a case.

## Sample output

```
case                        hit  rank  expected document
--------------------------  ---- ----- ------------------------------
aurora-pto-days             yes  1     aurora-employee-handbook.md
aurora-401k-match           yes  1     aurora-employee-handbook.md
aurora-password-paraphrase  yes  2     aurora-employee-handbook.md
...
solaris-methodology         yes  1     solaris-research-notes.txt

hit_rate@5: 0.933   MRR: 0.867   cases: 15
```

## Design notes

- The harness ingests documents by calling the app's ingestion building
  blocks directly (extract → chunk → embed → insert) rather than going
  through the HTTP API, so it measures retrieval quality in isolation from
  auth/upload plumbing.
- It creates a throwaway eval user per run, so results are unaffected by (and
  do not pollute) other data in the target database.
- `retrieve()` is called with the exact signature pinned in
  `docs/api-contract.md`; if that contract changes, this harness is the
  second consumer that must be updated.
