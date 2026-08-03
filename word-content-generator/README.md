# word-content-generator

Game-agnostic word-category content platform: generates, validates, reviews,
localizes, and compiles word-association categories, with an interactive web UI.

Absorbed from `bubble-word-tools` (core pipeline) and patterned on
`word-solitaire-levels` (web app shape). Games consume compiled outputs via
per-game format adapters (`bubble`, `ws`).

## Setup

    python3 -m pip install -e ".[web,dev]"
    export ANTHROPIC_API_KEY=...

## Web UI

    wcg-serve            # http://localhost:8000
    # Generate tab: type a topic -> pick one of the suggested categories ->
    # it is saved as approved instantly (English only); translations are
    # backfilled in the background and pushed to the sheet when done.
    # Anything left untranslated (failed locale, server closed mid-run) is
    # swept automatically at startup and every 15 minutes after
    # (WCG_SWEEP_MINUTES to change; costs nothing when nothing is missing).
    # Pool tab: browse the category pool, newest picks first.

## Shared pool spreadsheet

Every pick is also pushed to the shared Google Sheet (newest rows on top):
https://docs.google.com/spreadsheets/d/1qW17E9iSseOB3V3jj97PqWCqVy0M6ws_r-HqVJthXO0/edit

The push needs `config/sheet.json` (gitignored — ask a teammate for the
webhook URL + token, or see `docs/sheet-webhook-setup.md` to deploy from
scratch). Re-sync anytime with `python3 -m wcg sheet-push` (safe to rerun —
existing rows are skipped).

## Deploying (Coolify / Docker)

The repo ships a `Dockerfile` (serves on port 8000). In Coolify:

1. **+ New resource → Public Repository** (or your GitHub app) →
   `chardonnay-partners/word-content-generator`, branch `main`,
   build pack **Dockerfile**.
2. **Environment variables:**
   - `ANTHROPIC_API_KEY` — required for suggesting + translating
   - `SHEET_WEBHOOK_URL` + `SHEET_TOKEN` — the values from
     `config/sheet.json` (used when that gitignored file is absent,
     as in a container)
3. **Persistent storage:** add a volume mounted at `/app/data` —
   picks made in the deployed instance survive redeploys. On first
   boot it is seeded from the repo's committed pool.
4. Port **8000**; keep it at a **single instance** (two replicas would
   race on the data volume and double-translate).

Anyone with the URL can generate categories on your API key — keep the
deployment on your private network or behind Coolify's auth if that
matters.

## CLI

    python3 -m wcg generate --theme animals --count 20
    python3 -m wcg generate --theme all
    python3 -m wcg generate --parents --count 10
    python3 -m wcg validate
    python3 -m wcg review export
    python3 -m wcg review import reports/review.csv
    python3 -m wcg localize --locale fr
    python3 -m wcg compile --format bubble
    python3 -m wcg compile --format ws --locale en,es
    python3 -m wcg stats
    python3 -m wcg sheet-push

Categories live in `data/categories/` (one JSON file each, committed).
`reports/` and `output/` are generated and gitignored.

Design specs: `docs/superpowers/specs/`

## Tests

    python3 -m pytest
