# Localization Sheet (CSV) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every web pick appends sheet-style translation rows (key + 9 language columns) to a committed `data/localization.csv`, translated from English with strict proper-noun rules, downloadable from the UI.

**Architecture:** `config/settings.json` grows to 9 locales; the existing per-locale `localize_category` engine does the translating at pick time. A new store-agnostic `wcg/core/sheet.py` renders a category into CSV rows; `wcg/web/app.py` wires it into `/api/select` and serves the file; the Pool tab gets a download link.

**Tech Stack:** Python ≥3.11, stdlib `csv`, existing wcg package, FastAPI.

**Spec:** `docs/superpowers/specs/2026-07-17-localization-sheet-design.md`

## Global Constraints

- Locales: `["en", "tr", "fr", "de", "ja", "ko", "pt", "es", "ru"]`, defined only in `config/settings.json`.
- CSV path: `data/localization.csv` (sibling of `data/categories/`, committed). Header exactly: `Key,English(en),Turkish(tr),French(fr),German(de),Japanese(ja),Korean(ko),Portuguese(pt),Spanish(es),Russian(ru)`.
- Keys: category row key = category id; item row key = `<category-id>.<word-slug>` (English word lowercased, non-alphanumerics collapsed to `-`).
- Missing locale → empty CSV cell. CSV write failure → warning, never a lost save.
- Proper nouns: place names per target-language convention; person names/surnames NEVER translated; other proper nouns keep conventional local form or stay unchanged.
- No code comments. All UI copy in English. No backfill of existing categories.

---

### Task 1: Nine locales + proper-noun rules in the localize prompt

**Files:**
- Modify: `config/settings.json:5` (locales list)
- Modify: `wcg/core/localize.py:6-15` (`localize_system`)
- Test: `tests/test_localize.py` (append one test; extend the top import)

**Interfaces:**
- Consumes: existing `localize_system(locale) -> str`.
- Produces: same signature, prompt now carries proper-noun rules; `settings["locales"]` lists 9 locales for every consumer (select flow, stats, compile, sheet).

- [ ] **Step 1: Write the failing test**

In `tests/test_localize.py`, extend the existing import line `from wcg.core.localize import run_localize, localize_category` to also import `localize_system`, and append:

```python
def test_localize_system_proper_noun_rules():
    system = localize_system("tr")
    assert "NEVER translated" in system
    assert "Drinkwater" in system
    assert "Nueva York" in system
    assert "Londra" in system
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 -m pytest tests/test_localize.py::test_localize_system_proper_noun_rules -q`
Expected: FAIL (assertion on "NEVER translated").

- [ ] **Step 3: Extend the prompt and the locales**

Replace `localize_system` in `wcg/core/localize.py` with:

```python
def localize_system(locale):
    return (
        f"You localize word-game categories into the language with code '{locale}'.\n"
        "Given a category name and its words in English, produce natural equivalents "
        "in the target language - NOT literal translations. Words may change for "
        "cultural fit but must stay in the same association category, same order, "
        "same count.\n"
        "Proper nouns follow these rules:\n"
        "- Place names use the target language's own convention: London becomes "
        "Londra in Turkish; New York stays New York in Turkish but becomes "
        "Nueva York in Spanish.\n"
        "- Person names and surnames are NEVER translated, even when they have a "
        "dictionary meaning: Danny Drinkwater keeps the surname Drinkwater in "
        "every language.\n"
        "- Other proper nouns keep their conventional local form if one exists, "
        "otherwise stay unchanged.\n"
        'Return ONLY a JSON object: {"name": "...", "words": ["..."]}'
    )
```

In `config/settings.json` replace the locales line with:

```json
  "locales": ["en", "tr", "fr", "de", "ja", "ko", "pt", "es", "ru"],
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest -q`
Expected: 97 passed (96 + 1 new; existing tests carry their own settings fixtures, so the config change affects none of them).

Run: `python3 -m wcg validate`
Expected: `21 categories, 0 errors, ...` exit 0 (validation does not inspect locales).

- [ ] **Step 5: Commit**

```bash
git add config/settings.json wcg/core/localize.py tests/test_localize.py
git commit -m "feat: nine locales and proper-noun rules in localize prompt"
```

---

### Task 2: wcg/core/sheet.py (CSV renderer)

**Files:**
- Create: `wcg/core/sheet.py`
- Test: `tests/test_sheet.py`

**Interfaces:**
- Consumes: `Category` objects (via `tests/conftest.make_category` in tests); `category.names: dict`, `category.items[*].word: dict | None`.
- Produces: `LOCALE_LABELS: dict[str, str]`; `word_key(word: str) -> str`; `append_rows(category, csv_path, locales) -> int` (creates header when the file does not exist, appends one category row plus one row per word item, returns rows written excluding header). Task 3's select endpoint calls `append_rows`.

- [ ] **Step 1: Write the failing tests**

`tests/test_sheet.py`:

```python
import csv

from wcg.core.sheet import LOCALE_LABELS, append_rows, word_key
from tests.conftest import make_category

LOCALES = ["en", "tr", "es"]


def sheet_category():
    category = make_category(cid="world-cities", status="approved",
                             words=("London", "New York", "Rio, de Janeiro", "Tokyo"),
                             names={"en": "World Cities", "tr": "Dünya Şehirleri"})
    translations = {"London": "Londra", "New York": "New York",
                    "Rio, de Janeiro": "Rio", "Tokyo": "Tokyo"}
    for item in category.items:
        item.word["tr"] = translations[item.word["en"]]
    return category


def test_word_key():
    assert word_key("Sci-Fi") == "sci-fi"
    assert word_key("New York") == "new-york"
    assert word_key("Édouard!") == "douard"
    assert word_key("  ") == "item"


def test_new_file_gets_header_then_category_and_item_rows(tmp_path):
    path = tmp_path / "localization.csv"
    count = append_rows(sheet_category(), path, LOCALES)
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert count == 5
    assert rows[0] == ["Key", "English(en)", "Turkish(tr)", "Spanish(es)"]
    assert rows[1] == ["world-cities", "World Cities", "Dünya Şehirleri", ""]
    assert rows[2] == ["world-cities.london", "London", "Londra", ""]
    assert rows[3] == ["world-cities.new-york", "New York", "New York", ""]
    assert rows[4] == ["world-cities.rio-de-janeiro", "Rio, de Janeiro", "Rio", ""]
    assert rows[5] == ["world-cities.tokyo", "Tokyo", "Tokyo", ""]


def test_append_does_not_repeat_header(tmp_path):
    path = tmp_path / "localization.csv"
    append_rows(sheet_category(), path, LOCALES)
    append_rows(make_category(cid="birds"), path, LOCALES)
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert len(rows) == 11
    assert rows[6] == ["birds", "Birds", "", ""]
    assert rows[7] == ["birds.pigeon", "Pigeon", "", ""]


def test_ref_items_are_skipped(tmp_path):
    path = tmp_path / "localization.csv"
    category = make_category(cid="mixed", refs=("owls",))
    count = append_rows(category, path, LOCALES)
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert count == 5
    assert all("owls" not in row[0] for row in rows)


def test_all_configured_labels_exist():
    for locale in ["en", "tr", "fr", "de", "ja", "ko", "pt", "es", "ru"]:
        assert locale in LOCALE_LABELS
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_sheet.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'wcg.core.sheet'`.

- [ ] **Step 3: Write `wcg/core/sheet.py`**

```python
import csv
import re
from pathlib import Path

LOCALE_LABELS = {
    "en": "English(en)",
    "tr": "Turkish(tr)",
    "fr": "French(fr)",
    "de": "German(de)",
    "ja": "Japanese(ja)",
    "ko": "Korean(ko)",
    "pt": "Portuguese(pt)",
    "es": "Spanish(es)",
    "ru": "Russian(ru)",
}


def word_key(word):
    key = re.sub(r"[^a-z0-9]+", "-", word.lower()).strip("-")
    return key or "item"


def append_rows(category, csv_path, locales):
    csv_path = Path(csv_path)
    new_file = not csv_path.exists()
    word_items = [item for item in category.items if item.word]
    rows = [[category.id] + [category.names.get(locale, "") for locale in locales]]
    for item in word_items:
        rows.append([f"{category.id}.{word_key(item.word['en'])}"]
                    + [item.word.get(locale, "") for locale in locales])
    with open(csv_path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(
                ["Key"] + [LOCALE_LABELS.get(l, f"{l}({l})") for l in locales])
        writer.writerows(rows)
    return len(rows)
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests/test_sheet.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add wcg/core/sheet.py tests/test_sheet.py
git commit -m "feat: CSV sheet renderer (key plus per-locale columns)"
```

---

### Task 3: Wire the sheet into select, download endpoint, UI link

**Files:**
- Modify: `wcg/web/app.py` (imports, `create_app` body: csv path, select append, new endpoint)
- Modify: `wcg/web/static/index.html` (Pool tab link)
- Test: `tests/test_web.py` (append three tests)

**Interfaces:**
- Consumes: `wcg.core.sheet.append_rows` (Task 2); existing select flow.
- Produces: `GET /api/localization.csv` (200 `text/csv` download once rows exist, 404 JSON `{error}` before); select responses may carry `sheet: ...` warnings on CSV write failure.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web.py`:

```python
def test_select_appends_localization_csv(tmp_path):
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, _ = build_client(tmp_path, llm)
    client.post("/api/select", json={"variant": variant()})
    lines = (tmp_path / "localization.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Key,English(en),Turkish(tr)"
    assert lines[1] == "planets,Planets,Gezegenler"
    assert lines[2] == "planets.mars,Mars,Mars"


def test_select_csv_has_empty_cells_on_failed_locale(tmp_path):
    llm = FakeLlm([LlmError("boom")])
    client, _ = build_client(tmp_path, llm)
    client.post("/api/select", json={"variant": variant()})
    lines = (tmp_path / "localization.csv").read_text(encoding="utf-8").splitlines()
    assert lines[1] == "planets,Planets,"


def test_localization_csv_download(tmp_path):
    client, _ = build_client(tmp_path, FakeLlm([]))
    assert client.get("/api/localization.csv").status_code == 404
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, _ = build_client(tmp_path, llm)
    client.post("/api/select", json={"variant": variant()})
    response = client.get("/api/localization.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "planets.mars" in response.text
```

Note for the first test: the test fixture's `SETTINGS["locales"]` is `["en", "tr"]`, so the header has only those columns — the 9-locale header is covered by `tests/test_sheet.py` and the real `config/settings.json`. `test_select_appends_localization_csv` asserts `planets.mars,Mars,Mars` because FakeLlm's canned response localizes "Mars" to "Mars".

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_web.py -q`
Expected: the three new tests FAIL (no CSV file, 404 endpoint missing); the previous 13 pass.

- [ ] **Step 3: Wire app.py**

In `wcg/web/app.py`:

1. Extend the responses import: `from fastapi.responses import FileResponse, JSONResponse`
2. Add to the core imports: `from ..core.sheet import append_rows`
3. In `create_app`, right after `store = CategoryStore(Path(data_dir))`, add:

```python
    csv_path = Path(data_dir).parent / "localization.csv"
```

4. In `select()`, replace the final `store.save(category)` / `return` block with:

```python
        store.save(category)
        try:
            append_rows(category, csv_path, settings["locales"])
        except OSError as error:
            warnings.append(f"sheet: {error}")
        return {"category": category.to_dict(), "warnings": warnings}
```

5. Before the static mount, add:

```python
    @app.get("/api/localization.csv")
    def localization_csv():
        if not csv_path.exists():
            return JSONResponse({"error": "no localization rows yet"},
                                status_code=404)
        return FileResponse(csv_path, media_type="text/csv",
                            filename="localization.csv")
```

- [ ] **Step 4: Add the UI link**

In `wcg/web/static/index.html`, inside `<section id="view-pool">`, directly after `<p id="pool-stats"></p>`, add:

```html
    <p id="pool-tools"><a href="/api/localization.csv" download>Download localization.csv</a></p>
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: everything green (16 web tests total; suite total 105 = 97 + 5 sheet + 3 web).

- [ ] **Step 6: Commit**

```bash
git add wcg/web/app.py wcg/web/static/index.html tests/test_web.py
git commit -m "feat: write localization.csv on select and serve it from the UI"
```

---

## Final Verification

- [ ] `python3 -m pytest -q` — all green.
- [ ] `python3 -m wcg validate` — 0 errors, exit 0.
- [ ] Restart `wcg-serve`; live: pick a topic in the UI → pick one → `data/localization.csv` gains a category row + 4 item rows with 9-locale columns; Pool tab shows the download link; `/api/localization.csv` downloads. (Live LLM calls: ~8 per pick, expect 15-30 s.)
