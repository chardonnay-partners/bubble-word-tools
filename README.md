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
- **Word Content** tab — LLM category suggestions + the approved pool, with
  **→ Add to bank** to drop a category straight into the Level Generator's word bank.

It is **one single-page app**: `level-generator/index.html` (served at `/`) contains
both tabs and calls the `/api/*` endpoints directly — no iframe, one codebase. The
Word Content tab needs the running server (+ `ANTHROPIC_API_KEY`); the Level Generator
tab also works fully standalone (open the HTML file directly, or via GitHub Pages).

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

One image serves both tabs at one URL. In Coolify:

1. **+ New resource → Public Repository** → `chardonnay-partners/bubble-word-tools`,
   branch `main`, build pack **Dockerfile**.
2. **Base directory:** `/` (repo root) · **Dockerfile location:**
   `/word-content-generator/Dockerfile`. (The Dockerfile copies both folders and
   sets `WCG_LEVELS_DIR` so both tabs ship in the image.)
3. **Environment variables:**
   - `ANTHROPIC_API_KEY` — required for the Word Content tab's LLM features.
   - `APP_BASIC_AUTH` — set to `user:pass` to require login for the whole app
     (recommended for a public URL; the `/api/health` probe stays open). Unset = open.
   - optional `SHEET_WEBHOOK_URL` + `SHEET_TOKEN` for the Google-Sheet push.
4. **Persistent storage:** volume at `/app/data` (the category pool survives redeploys).
5. **Port `8000`, single instance.**

`ANTHROPIC_API_KEY` means anyone who can reach the URL can spend your Anthropic
credits — keep `APP_BASIC_AUTH` set or the app on a private network.

## Notes on game content

Game content extracted from the Unity project is **not** committed to this public repo:
the Level Generator's full word bank (`wordbank.json`) and the Word Content pool
(`word-content-generator/data/categories/*.json`) are gitignored. Each tool ships a
small built-in default so it runs out of the box.
