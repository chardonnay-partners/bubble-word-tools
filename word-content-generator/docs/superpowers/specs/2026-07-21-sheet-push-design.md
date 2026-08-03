# Push picks to the shared Google Sheet — design

Date: 2026-07-21
Status: approved by user

## Goal

When a word-set variant is picked in the web UI, its localization rows are
automatically pushed to the shared "pool" Google Spreadsheet
(`1qW17E9iSseOB3V3jj97PqWCqVy0M6ws_r-HqVJthXO0`, tab **Word Content**) so other
people see them, inserted at the **top** (row 2, below the header). New picks
also appear at the **top of the web UI Pool tab** (newest first). Existing local
picks missing from the sheet (16 rows) get backfilled.

## Decisions (user-confirmed)

- New rows go to the top of the Google Sheet tab AND newest-first in the web UI
  Pool tab.
- Auth via an **Apps Script web-app webhook** deployed on the spreadsheet by the
  user (no Google Cloud project, no keys on disk). A shared secret token guards
  the endpoint.
- Backfill the missing local rows once the webhook is live.
- Push is **inline** in `/api/select` (the request already spends ~10s on
  localization). Failures append to the response `warnings` and never block the
  save; `data/localization.csv` remains the local source of record.

## Components

### 1. Apps Script webhook (manual, one-time)

`docs/sheet-webhook-setup.md` documents the steps and contains paste-ready
code. Behavior of `doPost`:

- Reject requests whose JSON `token` doesn't match the script's `TOKEN` const.
- Accept `{token, rows: [[key, en, fr, ...], ...]}` — same column order as
  `localization.csv`.
- **Idempotent:** read column A, skip any row whose Key already exists.
- Insert remaining rows as one block before row 2 of the "Word Content" tab,
  preserving order (category row first, then its items).
- Wrap in `LockService` to serialize concurrent pushes.
- Respond `{inserted: n, skipped: m}` as JSON.

### 2. Config: `config/sheet.json` (gitignored)

```json
{"webhook_url": "https://script.google.com/macros/s/…/exec", "token": "…"}
```

Loaded by `create_app` (and the CLI command) if present. Missing file ⇒ push is
skipped and `/api/select` adds a `sheet: push not configured` warning.

### 3. `wcg/core/sheet.py`

- Extract `build_rows(category, locales)` from `append_rows` (which now uses
  it) so the select flow and the push share row construction.
- New `push_rows(rows, url, token)` — stdlib `urllib.request`, JSON POST,
  20s timeout. Raises `SheetPushError` (new) on HTTP/network errors, non-JSON
  replies, or an `error` field in the reply. Returns the parsed response dict.

### 4. `/api/select` in `wcg/web/app.py`

After the CSV append: if sheet config is loaded, `push_rows(...)`; catch
`SheetPushError` into `warnings` (prefix `sheet:`). Category gains a
`created` UTC ISO-8601 timestamp before saving.

### 5. `Category.created` (models.py, optional field)

Optional string field; validated if present (non-empty string), emitted by
`to_dict` only when set. Old category files without it keep loading unchanged.

### 6. Newest-first Pool tab

`/api/categories` sorts by (`created` desc, `id` asc) — categories with a
timestamp (new picks) come first, newest on top; legacy ones follow
alphabetically. No client change needed beyond what the server returns.

### 7. Backfill / repair: `wcg sheet-push` CLI command

Reads all of `data/localization.csv` (skip header) and pushes every row to the
webhook in one batch. Server-side dedupe means only missing keys get inserted —
run once to backfill the 16 rows, rerun anytime to repair drift. Prints
`inserted`/`skipped` counts; clear error if `config/sheet.json` is absent.

## Error handling

- Push failures never block a pick: category file + CSV are written first.
- Webhook is idempotent, so any failed push is recoverable via `wcg sheet-push`.
- Header mismatch protection stays in `append_rows` (unchanged).

## Testing

- `tests/test_sheet.py`: `build_rows` output shape; `push_rows` success /
  token-error / network-error via a mocked `urllib` opener.
- `tests/test_web.py`: select with sheet configured (push called with the CSV
  rows), push failure ⇒ warning present + category still saved, no config ⇒
  "not configured" warning; `/api/categories` order (created desc first).
- CLI command test following existing command-test style.

## Out of scope

- Pushing edits/deletions (sheet is append-only from this tool).
- Any change to the 88k existing sheet rows.
- Retry queues / background jobs.