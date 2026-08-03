# Bubble Word Tools

Tooling for the **Bubble Words** puzzle game, served as **one web app with tabs**.

## Run (unified app)

The [`word-content-generator/`](word-content-generator/) FastAPI server hosts both
tools behind a shared tab bar:

```bash
cd word-content-generator
python3 -m pip install -e ".[web]"
export ANTHROPIC_API_KEY=...        # only needed for the Word Content tab's LLM features
wcg-serve                           # http://localhost:8000
```

Open <http://localhost:8000>:

- **Level Generator** tab (default) — the [`level-generator/`](level-generator/) tool,
  fully client-side.
- **Word Content** tab — the Word Content generator (LLM category suggestions, pool,
  localization, Google-Sheet sync).

The server mounts the Level Generator at `/levels/`, the Word Content UI at `/word/`,
and the API at `/api/*`; `/` is the tab shell.

## Tools

- **[`level-generator/`](level-generator/)** — browser tool to generate and hand-edit
  levels. Emits JSON that byte-matches the game's `Level_N.json` format (verified
  against all 1001 shipped levels). Works standalone too — just open
  [`level-generator/index.html`](level-generator/index.html) in a browser, no server.
- **[`word-content-generator/`](word-content-generator/)** — FastAPI + CLI platform
  that generates, validates, localizes, and compiles word-association categories
  (compiles to the `bubble` format the Level Generator consumes). See its
  [README](word-content-generator/README.md).

## Planned

- **`analytics/`** — analytics/reporting tooling (TBD).
- Additional tools as needed.

## Deploy (Docker / Coolify)

One image serves both tabs. Point the build at this **repo root** with the Dockerfile
at `word-content-generator/Dockerfile` (it copies both folders and sets
`WCG_LEVELS_DIR`). Env: `ANTHROPIC_API_KEY`, optional `SHEET_WEBHOOK_URL` +
`SHEET_TOKEN`; persistent volume at `/app/data`; port `8000`, single instance.

## Notes on game content

Game content extracted from the Unity project is **not** committed to this public repo:
the Level Generator's full word bank (`wordbank.json`) and the Word Content pool
(`word-content-generator/data/categories/*.json`) are gitignored. Each tool ships a
small built-in default so it runs out of the box.
