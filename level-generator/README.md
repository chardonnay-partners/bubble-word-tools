# Bubbles — Level Generator

A self-contained, offline web tool for authoring and generating levels for the
**Bubble Words** puzzle game. It emits JSON that byte-matches the game's
`Level_N.json` level format (verified against all 1001 shipped levels — every one
round-trips exactly).

## Run

No build, no install, no dependencies. Just open the file in any browser:

```bash
open index.html
```

Everything runs client-side; your word bank persists in the browser's `localStorage`.

## What it does

- **Generate** — seeded, deterministic generation. Pick category count, words per
  category, max bubbles, move limit, difficulty, spawn seed, and how many special
  bubbles to sprinkle in. Same generator seed + params → the identical level.
  *Reroll* bumps the seed.
- **Manual edit** — hand-tune everything: categories & words (with `parentCategory`
  promotion and per-word `IsCracked` / `crackBreakNum` / `IsLinked` flags), all level
  params, and every special-bubble type.
- **Spawn pool (`allWordEntries`)** — the list of orbs that actually spawn, edited
  independently of the categories. *Auto-derive* mirrors the categories; turn it off
  to hand-order the spawn list (the first `maxBubblesInScene` spawn immediately, the
  tail is the refill queue).
- **Special bubbles** — Frozen, Burst, Cryptic, Key/Lock, Screw-Lock, Cracked,
  Backward, Linked, Chains, and the Bubble Separator. Each with optional advanced
  `has…` / `minMax…` procedural-placement flags.
- **Board preview** — renders the spawn pool coloured by resolved category (the game's
  8-colour palette, applied modulo the category index), with special-bubble markers
  and the initial-board / refill-queue split.
- **Live validation** — flags unwinnable configs, unmapped spawn words, empty
  categories, and non-multiple-of-4 spawn groups.
- **I/O** — Load an existing `Level_N.json`, edit the JSON directly and *Apply* it
  back, Export a single `Level_N.json`, or **Batch** a range of levels.

## Word bank

The **📚 Word Bank** drawer holds the vocabulary the generator draws from. A compact
default (~120 categories) is built into `index.html`, so the tool works out of the box.

Bank edits persist in your browser (*Export* to save a copy, *Import* to load one,
*Reset* to restore the built-in default). You can import a `wordbank.json` in either
the full `{ "categories": [...] }` form or the compact `[["Name",["word",…]], …]` form.

## Level format

Nine core keys, in a fixed order, always present:

```
categories, allWordEntries, maxBubblesInScene, moveLimit, randomSeed,
levelDifficulty, frozenBubbles, useBubbleSeparator, bubbleSeparatorData
```

Special-bubble blocks (`burstBubbles`, `keyLockBubbles`, `screwLockBubbles`,
`crackedBubbles`, `backwardBubbles`, `linkedBubbles`, `crypticBubbles`,
`bubbleChains`) and the `has…` / `minMax…` flags are **appended only when used**, so a
plain level's output stays identical to hand-authored content. (The game's DTO field
is spelled `hasSeperator` — sic — and `IsCracked` / `IsLinked` are PascalCase; the
tool matches this exactly.)

### Key concepts

- **`categories`** define colour / merge groups. Each word resolves to a category
  (first occurrence, case-insensitive).
- **`allWordEntries`** is the authoritative spawn list — the orbs that appear. It is a
  separate pool and may differ from the flattened categories (a category can list a
  word that never spawns).
- **Completability** — an orb's tier equals its word count and it pops at tier 4
  (`MaxTier = 4`). So each category's *spawned* orbs ideally number a multiple of 4.
  Levels can intentionally leave a remainder, so this is a **warning**, not a hard
  error.
- **`moveLimit`** is a raw addend. In-game moves ≈
  `moveLimit + categories×3 + splitWords + bonus(1–3)`, where `bonus` is a
  per-level-number hash added at runtime.

## Deploying generated levels

Export writes `Level_N.json`. Drop it into the game's `Resources/Levels/` folder
(levels are loaded by number).
