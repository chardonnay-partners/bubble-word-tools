# Bubble Word Tools

Tooling for the **Bubble Words** puzzle game. Each tool lives in its own folder and
is self-contained.

## Tools

- **[`level-generator/`](level-generator/)** — a browser-based tool to generate and
  hand-edit levels. Emits JSON that byte-matches the game's `Level_N.json` format
  (verified against all 1001 shipped levels). No build or install — open
  [`level-generator/index.html`](level-generator/index.html) in any browser.

## Planned

- **`analytics/`** — analytics/reporting tooling (TBD).
- Additional tools as needed.

## Conventions

- Each tool is a standalone folder with its own `README.md`.
- Prefer dependency-free, self-contained tools (open in a browser, or a single small
  server) so they're trivial to run and share.
- Game content extracted from the Unity project (e.g. full word banks) is **not**
  committed to this public repo — see each tool's README.
