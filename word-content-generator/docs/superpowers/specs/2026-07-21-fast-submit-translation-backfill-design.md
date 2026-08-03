# Fast submit + translation backfill

**Date:** 2026-07-21
**Status:** approved (auto-backfill + manual button, per user)

## Problem

`/api/select` translates every pick into 7 locales synchronously (one LLM call
each) before responding — 30-60+ seconds per pick. The user wants to find and
add categories fast; translations can arrive later.

## Design

### 1. Fast submit (`/api/select`)

Selecting a variant saves the category with English only, appends English-only
rows to `data/localization.csv` (translation columns blank), and pushes those
rows to the Google Sheet. No LLM calls in the request path — submit drops to
~1 second. The response no longer carries per-locale warnings; sheet warnings
stay.

### 2. Backfill core (`wcg/core/backfill.py`)

`run_backfill(store, llm, settings, csv_path, sheet_config, only_ids=None)`:

- Finds approved categories missing any non-en locale (name or any word).
  `only_ids` restricts the sweep (used by the auto path).
- Localizes each gap via the existing `localize_category` (which already
  skips complete locales), saving after each category.
- Rewrites the matching rows of `localization.csv` in place (keys that are
  missing from the file are appended).
- Pushes the refreshed rows to the sheet with a new `updateRows` action.
- Returns `{"localized": [...], "failed": [[cid, locale, reason], ...],
  "warnings": [...]}`. LLM failures never abort the sweep.

### 3. Auto trigger

After `/api/select` responds, a FastAPI `BackgroundTasks` task runs
`run_backfill` scoped to the just-picked category id. Failures are printed to
the server log; the manual button is the repair path.

### 4. Manual button + endpoint

- `POST /api/localize-missing` runs the full sweep and returns its result.
  503 when `ANTHROPIC_API_KEY` is unset.
- `/api/stats` gains `missing_translations` (count of approved categories
  missing at least one locale).
- The web UI shows a "Translate missing (N)" button (hidden when N=0),
  refreshed on load and after each pick/sweep.

### 5. Sheet webhook `updateRows` action

Apps Script addition: `{action: "updateRows", rows: [...]}` — for each row
whose Key exists in column A, fill **only blank cells** (never overwrites a
teammate's manual edit). Rows with unknown keys are reported back, not
inserted. Requires a one-time redeploy (Manage deployments → New version).
Old deployments treat the payload as an insert and skip existing keys —
harmless, translations just stay pending until redeploy.

`push_rows` gains an optional `action` parameter; `sheet.py` gains
`update_csv_rows` for the in-place CSV rewrite (header-checked like
`append_rows`).

### 6. Testing

- `test_web.py`: select no longer localizes inline but the background task
  fills translations (TestClient runs background tasks synchronously);
  new endpoint tests for `/api/localize-missing`.
- `test_sheet.py`: `update_csv_rows` replace/append behavior; `push_rows`
  action payload.
- `test_stats.py`: `missing_translations`.

## Error handling

- LLM errors per locale are collected, not raised; category keeps whatever
  locales succeeded (same as today).
- Sheet/CSV errors surface as warnings (manual path) or log lines (auto path).
- Re-running the sweep is idempotent: complete locales are skipped, CSV rows
  are replaced by key, sheet updates fill blanks only.
