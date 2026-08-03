# Word Content Generator — Design (Milestone 1: Migration + Web UI)

**Date:** 2026-07-15
**Status:** Approved
**Repo:** `word-content-generator` (this repo; GitHub remote to be attached later by the user)

## Purpose

A game-agnostic word-category content platform. It consolidates:

- the **bubble-word-tools** core (category model, pool store, validation, LLM generation, localization, compile adapters — fully built and tested, 71 tests), and
- the **word-solitaire-levels** web pattern (FastAPI + static single-page UI, later also its level-generation ideas).

Games (Bubble Word, Word Solitaire, future titles) consume compiled outputs via per-game format adapters. The platform itself carries no game branding.

Milestone 1 = migrate the core under a new game-agnostic package + ship the interactive web UI. Google Sheets sync and level-generation tooling are later milestones.

## Decisions Carried From bubble-word-tools (unchanged)

The category data model, storage, validation, localization, and compile behavior are exactly as specified in `docs/superpowers/specs/2026-07-14-category-generator-design.md` (migrated into this repo's docs). In brief: one JSON file per category (`data/categories/<id>.json`), items are words (locale→text dicts, `en` canonical) or `ref`s to other categories (graph, cycle-checked), status `draft/approved/rejected`, 4–5 items per category, internationally understandable words preferred, difficulty 1–3 (1 = internationally transparent), compile ordered easiest-first.

## New Decisions (this milestone)

- **Name/identity:** repo `word-content-generator`, Python package `wcg`, CLI `python -m wcg`.
- **bubble-word-tools is absorbed:** code, the existing category data (20 animals drafts), and docs move here; the old repo stays as a frozen archive.
- **Web UI ships in this milestone**; all UI copy in English.
- **Selection = approval:** a category chosen in the web propose flow is saved directly as `approved` (the human choice is the review) and is **auto-localized at selection time** into all configured locales (`settings.locales`).
- **CSV review flow stays** for batch CLI generation; the web flow is the interactive alternative, not a replacement.
- **Google Sheets: out of scope** for this milestone (next milestone; leaning git-JSON-as-source-of-truth with Sheets as synced mirror, to be designed then).

## Repo Layout

```
word-content-generator/
  wcg/
    core/
      models.py        # Category/Item (moved verbatim from bwtools)
      store.py         # CategoryStore
      llm.py           # Claude API client
      localize.py      # localization engine (moved from commands/localize.py)
      validation.py    # validate_pool/Issue/write_report (moved from commands/validate.py)
      propose.py       # NEW: topic → N candidate categories (stateless)
    games/
      bubble.py        # compile adapter (was formats/game.py) — rich format
      ws.py            # compile adapter (was formats/ws.py) — word-solitaire flat list
    commands/          # CLI: generate, validate, review, localize, compile, stats
    web/
      app.py           # FastAPI endpoints
      static/          # single-page UI (two tabs), vanilla JS/CSS, English
    __main__.py        # CLI entry (same subcommands as bwtools)
  config/
    settings.json      # model, item_min/max, locales, max_llm_retries, propose_variants
    themes.json        # theme seeds for batch generation
  data/categories/     # pool (committed; 20 animals drafts migrate in)
  docs/superpowers/…   # this spec + migrated bwtools spec/plan (historical)
  tests/               # all 71 bwtools tests migrate (imports renamed) + new web/propose tests
```

Module moves are mechanical renames (`bwtools` → `wcg`, `formats/` → `games/`, validation/localization logic pulled from command modules into `core/` so web and CLI share them; the command modules become thin wrappers).

## Web Application

FastAPI (`wcg.web.app`), launched via `wcg-serve` console script (uvicorn, port 8000). Serves the static UI at `/` and a JSON API under `/api`. Follows the word-solitaire-levels pattern (self-contained static page, no build step, no external CDN).

### Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/api/health` | health check |
| POST | `/api/propose` | `{topic: str}` → `{variants: [{name, theme, difficulty, words: [str]}]}` — `propose_variants` (default 3) candidate categories for the topic; stateless, nothing written; existing pool names/words included in the prompt as dedup context; the LLM assigns each variant a theme from `config/themes.json` (fallback `other`); invalid LLM variants are dropped (never repaired), so fewer than N may return |
| POST | `/api/select` | `{variant: {...}}` → validates, assigns a unique kebab-case id (slugified from the name; on collision append `-2`, `-3`, …), localizes name+words into all configured locales, saves as `approved`; returns the saved category. On localization failure the category is still saved (approved, en-only) and the response carries a warning — the pool never loses a human-approved pick |
| GET  | `/api/categories` | pool listing with `status`/`theme` query filters |
| GET  | `/api/stats` | pool summary (existing compute_stats) |

### UI (two tabs, English)

- **Generate tab:** a topic input + "Suggest" button → up to 3 variant cards (name, words, difficulty, theme) → "Pick this one" on a card calls select and shows the saved result (with which locales were filled); "Suggest again" re-proposes. While a request runs, the form is disabled with a spinner.
- **Pool tab:** table of categories (name, theme, status, difficulty, item count, words preview), client-side filter by theme/status, stats summary line on top. Read-only in this milestone.

### Concurrency & errors

- Single-user tool; no auth in this milestone (localhost / trusted deploy).
- API errors return JSON `{error: str}` with 4xx/5xx; the UI surfaces them inline.
- `ANTHROPIC_API_KEY` missing → `/api/propose` returns 503 with a clear message; `/api/select` still saves the pick as approved en-only with a "localization skipped" warning (a human-approved pick is never lost); the rest of the app works.
- File writes go through the existing atomic store; a select that fails validation writes nothing.

## CLI

Unchanged behavior, renamed entry: `python -m wcg generate|validate|review|localize|compile|stats`. `compile --format bubble|ws` (`game` renamed to `bubble`).

## Testing

- All existing tests migrate with renamed imports; behavior tests must pass unchanged (proves the migration didn't alter semantics).
- New: `core/propose.py` unit tests (FakeLlm — variant parsing, dedup context in prompt, invalid-variant dropping), web API tests via FastAPI TestClient (propose/select/categories happy paths + validation failure + missing-API-key 503), select-time localization tests (success, LLM failure → saved en-only with warning).

## Migration & Archive

- Code moves by copy into the new repo (fresh git history here; bubble-word-tools keeps its own history as the archive).
- `data/categories/` (20 animals drafts) and `config/` copy over as-is.
- bubble-word-tools gets a final README note: "superseded by word-content-generator".
- When the user creates the GitHub repo: `git remote add origin … && git push -u origin main`.

## v1 (Milestone 1) Acceptance Criteria

1. `python -m wcg` full CLI pipeline works as bwtools did (all migrated tests pass).
2. `wcg-serve` → in the browser: type a topic (e.g. "planets") → get up to 3 variants → pick one → it lands in `data/categories/` as `approved` with all configured locales filled → visible in the Pool tab.
3. `python -m wcg compile --format bubble` and `--format ws` emit outputs including web-selected categories.

## Out of Scope (Milestone 1)

- Google Sheets sync (next milestone).
- Level generation (word-solitaire-levels logic; later milestone).
- Showing/editing translations in the UI; UI locale switching.
- Auth/multi-user; hosted deployment config (Dockerfile/Coolify can be added when the remote exists).
- Image tooling (schema slot only, as before).
