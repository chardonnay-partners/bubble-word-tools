# Bubble Word — Category Generator Design

**Date:** 2026-07-14
**Status:** Approved
**Repo:** `bubble-word-tools` (this repo)

## Purpose

We are about to start development of a bubble-association word game (reference: Bubble Word Jam, `com.vgames.bubbleword`). The game consumes categories of associated words (e.g. Birds = Pigeon, Crow, Eagle, Owl). Word-solitaire's `words_categories.json` (7,388 categories, ~40K words) is a structural reference, but we will not ship its data as-is — we build our own generator and content pool.

This tool generates, validates, reviews, localizes, and compiles that content pool.

## Requirements

- Large-scale category production (thousands of categories over time).
- 4–5 items per category.
- Multi-language support; `en` is canonical, other locales filled on demand.
- Hierarchical categories: in the game, a completed category becomes a bubble that can itself be an item of a higher category (Pigeon+Crow+Eagle+Owl → Birds; Birds+Cats+Dogs → Animals). Depth is unbounded.
- Some categories will have images in a later phase; the schema reserves a slot now, image tooling comes later.
- Human review gate between LLM generation and final output (genre's #1 content complaint is nonsensical word–category pairings).
- Words are LLM-generated (Claude API), pipeline validates and deduplicates.
- Words must be easy and internationally understandable: prefer cross-language cognates and proper nouns (planets like Uranus and Jupiter, Pizza, Taxi) over obscure vocabulary. `difficulty` encodes this: 1 = internationally transparent everyday words, 2 = common but language-dependent, 3 = niche. Compiled output is ordered easiest-first so the game can consume categories in difficulty order.

## Data Model

One JSON file per category at `data/categories/<id>.json`:

```json
{
  "id": "birds",
  "theme": "animals",
  "difficulty": 1,
  "image": null,
  "status": "draft",
  "items": [
    { "word": { "en": "Pigeon", "tr": "Güvercin" } },
    { "word": { "en": "Crow",   "tr": "Karga" } },
    { "word": { "en": "Eagle",  "tr": "Kartal" } },
    { "ref": "owls" }
  ],
  "names": { "en": "Birds", "tr": "Kuşlar" }
}
```

- **items** — each entry is either `{"word": {locale: text}}` or `{"ref": "<category-id>"}` (graph model). Refs are resolved at compile time; cycles are rejected by validation.
- **Locales live inside the word objects**, not in separate files. `en` is required; other locales optional until localized.
- **status** — lifecycle `draft → approved`, plus `rejected`. Rejected categories are kept on disk so they stay in the dedup context and the LLM does not regenerate them.
- **theme** — flat curation/generation tag (animals, food, sports…), independent of the `ref` hierarchy. Themes are defined in `config/themes.json`.
- **difficulty** — 1–3, assigned by the LLM, correctable during review. 1 = internationally transparent (cognates, proper nouns), 2 = common but language-dependent, 3 = niche.
- **image** — always `null` for now; later an asset key (e.g. `"birds_icon"`).
- **id** — unique, kebab-case, English. All refs point at these ids.

## CLI

Single entry point: `python -m bwtools <command>`.

### generate `--theme <name>|all --count N`
Theme-seeded generation via Claude API (model: `claude-sonnet-5`, structured output). The prompt includes all existing category names and words for that theme as dedup context ("do not produce these"). Output: `en`-only categories written as `draft` files immediately (no lost work on crash). Invalid LLM output (wrong item count, duplicates, schema mismatch) is rejected and reported — never silently fixed; the shortfall is picked up by the next run.

`generate --parents` — hierarchy mode: inspects existing categories and proposes parent categories with `ref` items (Birds+Cats+Dogs → Animals).

### validate
Checks the whole pool: id uniqueness, ref target existence, cycle detection (DFS), item count within 4–5, intra-category word duplicates (error), empty locales, schema conformance. Cross-category word reuse is allowed (as in WS data, where 40K placements share 14K unique words) but listed in the report for curation awareness. Report: `reports/validation.md`. Other commands run validation before/after their work.

### review export / review import
`export` writes drafts to `reports/review.csv` (one row per category: id, name, words, difficulty, theme, empty `decision` column). Reviewer fills `decision` (`approve`/`reject`) and may edit words directly in the CSV. `import` applies decisions: statuses update, edited words are written back. Unknown ids or invalid decisions abort the whole import (all-or-nothing).

### localize `--locale <code>`
Fills missing locales on `approved` categories only (review happens once, on `en`; translation cost is never wasted on rejects). The prompt asks for natural equivalents in the target language, not literal translation — words may change for cultural fit. Category names are localized too.

### compile `--format game|ws --locale <codes>`
Compiles the approved pool into `output/`, ordered by difficulty ascending (then id). Format adapters are pluggable (Strategy pattern):
- `game` — our rich format; refs validated and kept as ids, categories with excluded ref targets dropped transitively.
- `ws` — word-solitaire-compatible flat list (`[{categoryId, wordsIds[]}]`), one file per locale.

Categories missing a requested locale are skipped with a warning.

### stats
Pool summary: categories per theme, status distribution, locale coverage %.

## Repo Layout

```
bubble-word-tools/
  bwtools/
    __main__.py          # CLI (argparse subcommands)
    models.py            # Category/Item dataclasses + schema (de)serialization
    store.py             # data/categories/ IO, pool queries
    llm.py               # Claude API client (retry, structured output)
    commands/            # generate, validate, review, localize, compile, stats
    formats/             # compile adapters (game.py, ws.py)
  config/
    themes.json          # theme seeds
    settings.json        # model name, item min/max, locale list
  data/categories/       # category files (committed — source of truth)
  reports/               # validation/review artifacts (gitignored)
  output/                # compile artifacts (gitignored)
  tests/
```

## Error Handling

- API key from `ANTHROPIC_API_KEY`; LLM calls retry with backoff.
- Generated files are written immediately — a crash mid-run loses nothing.
- Invalid LLM output is rejected and reported, never auto-repaired.
- `review import` is all-or-nothing.
- File writes are atomic (temp file + rename).

## Testing

- LLM calls mocked; `llm.py` is the only module touching the real API.
- Unit tests: validation rules (cycle detection, dedup, schema), review export/import round-trip, compile adapters.
- Runner: `pytest`.

## v1 Acceptance Criteria

End-to-end flow works: `generate --theme all` produces ~200 draft categories from 8–10 themes → CSV review → approved set localized with `localize --locale tr` → `compile` emits both the rich format and the WS-compatible output.

## Out of Scope (v1)

- Image generation/assignment tooling (schema slot reserved only).
- Google Sheets review integration (CSV covers current needs; can be layered on later).
- Level generation (which categories appear in which level is the game's concern).
- Unity-side consumption code (game repo does not exist yet).
