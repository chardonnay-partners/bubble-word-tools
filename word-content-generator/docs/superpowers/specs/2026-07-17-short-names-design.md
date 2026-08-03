# Short Display Names + Descriptor (and Pool Reset)

**Goal:** Category names shown in the game (and translated into all locales) are short — at most 2 words, 1 preferred. Each category also carries a unique descriptive internal name (the *descriptor*) that drives the id, the CSV keys, and pool disambiguation. The old migrated animals pool is deleted; the user's three live picks stay.

## Naming model

- `Category.descriptor` — new optional string field. The specific internal English name ("Australian Animals"). When absent (legacy files), `names["en"]` serves as the descriptor via the accessor `descriptor_or_name()`.
- `names` — unchanged in shape, but now holds the SHORT display name per locale ("Animals" / "Hayvanlar" / ...). Rule: at most 2 words; single word preferred when meaning survives.
- Duplicate display names across categories are fine (validation has no name-uniqueness check); ids/keys stay unique because they derive from the descriptor.

## Schema

- `from_dict`: `descriptor` optional; if present must be a non-empty string (else `SchemaError`). Unknown-key tolerance means old readers ignore it.
- `to_dict`: includes `"descriptor"` only when set (legacy files round-trip byte-identical).
- New accessor: `descriptor_or_name()` returns `descriptor or names["en"]`.

## Propose flow

- Each variant now returns `{"name", "descriptor", "theme", "difficulty", "words"}`:
  - `name`: short display name, **max 2 words** — a variant whose name has 3+ words is rejected (never repaired);
  - `descriptor`: specific phrase describing the angle (required non-empty string, no length cap).
- The system prompt explains both fields with the Australian Animals → Animals example.
- Dedup context (`existing_names` in the user prompt) now lists descriptors (`descriptor_or_name()`), not display names.

## Select flow

- id = `unique_id(slugify(variant["descriptor"]), pool)` — e.g. `australian-animals` even when the display name is "Animals".
- Saved category: `descriptor` = variant's descriptor, `names["en"]` = short name; localization translates the short name (localize prompt gains: keep the name as concise as the English one, never more than 2 words).
- CSV unchanged mechanically: key = category id (descriptor-derived), cells = short localized names.

## UI

- Variant cards: title = short name; the meta line shows the descriptor before theme/difficulty.
- Pool table: new "Descriptor" column right after Name; `/api/categories` rows gain a `descriptor` field (`descriptor_or_name()`).

## Pool reset

- Delete the 20 migrated animal categories (`git rm`), keep `football-world-cup-legends`, `ice-cream-flavors`, `iconic-skylines` and `.gitkeep`. Their display names stay long until the user shortens them by hand (or asks for help).
- `data/localization.csv` stays as-is (contains only iconic-skylines).

## Compatibility notes

- `/api/select` now rejects variants without a descriptor (400) — the UI always passes what propose returned, so the round-trip is unaffected.
- Legacy categories (no descriptor) keep working everywhere via the fallback accessor.

## Testing

- models: descriptor round-trip, empty-descriptor SchemaError, absent → None + fallback accessor.
- propose: fixtures gain descriptor; rejections for 3+-word name and missing/empty descriptor; prompt mentions both fields; dedup context uses descriptors.
- web: select derives id from descriptor while names.en is the short name; categories endpoint returns descriptor; existing select/CSV tests updated to two-name fixtures.
- localize: prompt contains the 2-word brevity rule.
- After the wipe: `wcg validate` → 3 categories, 0 errors; full suite green.
