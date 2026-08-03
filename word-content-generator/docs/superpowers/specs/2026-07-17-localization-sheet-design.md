# Localization Sheet (CSV) on Pick

**Goal:** Every "Pick this one" also appends translation rows to a committed CSV (`data/localization.csv`) shaped like the game team's Google Sheet: a key column plus one column per language, translated from English. The daily workflow needs no terminal: the CSV builds itself on pick and is downloadable from the UI.

## Languages

`settings.locales` is `["en", "fr", "de", "ja", "ko", "pt", "es", "ru"]`. English stays canonical; picks localize to all 7 non-en locales via the existing per-locale `localize_category` engine (7 sequential LLM calls, ~15-30 s per pick; per-locale failure tolerated). Category JSON files carry all locales; `compile` can emit any of them. Note: `wcg compile --format ws` without `--locale` emits one file per configured locale (8).

## CSV format

- Path: `data/localization.csv` (committed; sibling of `data/categories/`).
- Header (written when the file does not exist):
  `Key,English(en),French(fr),German(de),Japanese(ja),Korean(ko),Portuguese(pt),Spanish(es),Russian(ru)`
- Per pick, appended in order:
  - one category row: key = category id (e.g. `football-world-cup-legends`), cells = category name per locale;
  - one row per item: key = `<category-id>.<word-slug>` where word-slug is the English word lowercased with non-alphanumerics collapsed to `-` (`Sci-Fi` → `sci-fi`, `New York` → `new-york`).
- A locale missing from the category (failed localization) produces an empty cell — visible in the sheet for later fixing.
- Standard CSV quoting via Python's `csv` module; UTF-8. Import into Google Sheets via File → Import.
- No Id column. No backfill of pre-existing categories (a backfill command can be added later if wanted).

## Proper-noun translation rules

`localize_system` gains explicit rules, applied to every language:

- Place names follow the target language's own convention: New York stays New York in German but becomes Nueva York in Spanish and Нью-Йорк in Russian.
- Person names and surnames are NEVER translated, even when the name has a dictionary meaning (Danny Drinkwater stays Drinkwater in every language).
- Internationally standard proper nouns (brands, titles) keep their conventional local form if one exists, otherwise stay as-is.

## Web layer

- `/api/select` appends the CSV rows after the category is saved. CSV write failure must not lose the save: it is reported as a warning, like a localization failure.
- New endpoint `GET /api/localization.csv` returns the file as a download (404 JSON `{error}` if no pick has happened yet).
- UI: a "Download localization.csv" link in the Pool tab, pointing at the endpoint.

## Module boundaries

- New `wcg/core/sheet.py`: `LOCALE_LABELS` (locale → column label), `word_key(word) -> str`, `append_rows(category, csv_path, locales) -> int` (creates header if needed, appends rows, returns row count written). No knowledge of FastAPI or the store.
- `wcg/web/app.py` wires it into select and serves the download.
- `config/settings.json` is the only place the language list lives.

## Testing

- Unit tests for `word_key` and `append_rows` (new file gets header, append-only, empty cells for missing locales, quoting of commas/quotes).
- Web test: pick with FakeLlm responses for all 8 locales → CSV contains category row + 4 item rows with translated cells; pick with a failing locale → empty cells + warning; download endpoint round-trip; 404 before first pick.
- Existing suite (96) stays green; existing localize/select semantics unchanged apart from the longer locale list coming from settings.
