# Word Content Generator — Milestone 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the bubble-word-tools core into the game-agnostic `wcg` package and ship the interactive FastAPI web UI (propose → pick → auto-localize → pool).

**Architecture:** `wcg/core` holds the shared engine (models, store, llm, validation, localize, propose), `wcg/games` holds per-game compile adapters (bubble, ws), `wcg/commands` keeps the CLI, `wcg/web` adds FastAPI + a static two-tab UI. Migration is copy + rename from `/Users/murat/Desktop/Projects/bubble-word-tools` (the SOURCE repo, readable during implementation); its tests migrate unchanged in behavior, proving semantics survived.

**Tech Stack:** Python ≥3.11, `anthropic`, FastAPI + uvicorn (web extra), pytest + httpx (dev).

**Spec:** `docs/superpowers/specs/2026-07-15-word-content-generator-design.md`
**Source repo:** `/Users/murat/Desktop/Projects/bubble-word-tools` (read-only during this plan; archived in Task 9)

## Global Constraints

- Package `wcg`, CLI `python -m wcg`, web entry `wcg-serve`. No game branding in core/web.
- Only runtime dependency: `anthropic>=0.40`; web extra: `fastapi>=0.110`, `uvicorn[standard]>=0.29`; dev: `pytest>=8`, `httpx>=0.27`.
- Behavior of migrated code must not change: all migrated tests pass with only import/name edits.
- Categories: 4–5 items (`item_min`/`item_max` from settings), `en` canonical, ids kebab-case, statuses draft/approved/rejected, atomic writes, invalid LLM output rejected never repaired.
- Web select flow: selection saves directly as `approved`; auto-localizes to all `settings.locales` (en+tr now); on localization failure the category is still saved en-only with a warning — a human-approved pick is never lost.
- `compile --format bubble|ws` (bubble = the former `game` format).
- All UI copy in English. No code comments (project convention).
- `reports/` and `output/` gitignored; `data/categories/` committed.

---

### Task 1: Scaffold + migrate core (models, store, llm) + config/data

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `wcg/__init__.py`, `wcg/core/__init__.py` (all empty `__init__`)
- Copy from SOURCE: `bwtools/models.py` → `wcg/core/models.py`; `bwtools/store.py` → `wcg/core/store.py`; `bwtools/llm.py` → `wcg/core/llm.py`; `tests/conftest.py` → `tests/conftest.py`; `tests/test_models.py`, `tests/test_store.py`, `tests/test_llm.py` → same names under `tests/`
- Copy from SOURCE: `config/settings.json`, `config/themes.json` → `config/`; `data/categories/*.json` + `.gitkeep` → `data/categories/`

**Interfaces:**
- Produces: `wcg.core.models` (`Category`, `Item`, `SchemaError`, `ID_PATTERN`, `VALID_STATUSES`; `Category.words_for(locale)`, `.refs()`, `.from_dict/.to_dict`), `wcg.core.store.CategoryStore(root)` (`.load_all()/.save()/.by_status()`), `wcg.core.llm` (`LlmClient(model, max_retries=3, client=None, backoff=1.0).complete_json(system, user)`, `LlmError`).
- Produces: `tests/conftest.py` with `make_category(cid, theme, status, words, refs, difficulty, names)` and `FakeLlm(responses)` (`.calls`, `.complete_json` pops canned responses, raises Exceptions).

- [ ] **Step 1: Write scaffolding files**

`pyproject.toml`:

```toml
[project]
name = "word-content-generator"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["anthropic>=0.40"]

[project.optional-dependencies]
web = ["fastapi>=0.110", "uvicorn[standard]>=0.29"]
dev = ["pytest>=8", "httpx>=0.27"]

[project.scripts]
wcg-serve = "wcg.web.app:run"

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]

[tool.setuptools.packages.find]
include = ["wcg*"]
```

`.gitignore`:

```
__pycache__/
.pytest_cache/
*.egg-info/
.venv/
reports/
output/
```

Empty files: `wcg/__init__.py`, `wcg/core/__init__.py`.

- [ ] **Step 2: Copy core modules, config, data, and tests from SOURCE**

```bash
SRC=/Users/murat/Desktop/Projects/bubble-word-tools
cp $SRC/bwtools/models.py wcg/core/models.py
cp $SRC/bwtools/store.py  wcg/core/store.py
cp $SRC/bwtools/llm.py    wcg/core/llm.py
mkdir -p config data/categories tests
cp $SRC/config/settings.json $SRC/config/themes.json config/
cp $SRC/data/categories/* data/categories/
cp $SRC/tests/conftest.py $SRC/tests/test_models.py $SRC/tests/test_store.py $SRC/tests/test_llm.py tests/
```

- [ ] **Step 3: Apply renames**

- `config/settings.json`: add `"propose_variants": 3` after `"max_llm_retries": 3` (keep valid JSON).
- `wcg/core/store.py`: no change needed (`from .models import Category, SchemaError` still resolves inside `wcg/core/`).
- `tests/conftest.py`: `from bwtools.models import Category, Item` → `from wcg.core.models import Category, Item`
- `tests/test_models.py`: `from bwtools.models import` → `from wcg.core.models import`
- `tests/test_store.py`: `from bwtools.models import SchemaError` → `from wcg.core.models import SchemaError`; `from bwtools.store import CategoryStore` → `from wcg.core.store import CategoryStore`
- `tests/test_llm.py`: `from bwtools.llm import LlmClient, LlmError` → `from wcg.core.llm import LlmClient, LlmError`

- [ ] **Step 4: Run the migrated tests**

Run: `cd ~/Desktop/Projects/word-content-generator && python3 -m pytest tests/test_models.py tests/test_store.py tests/test_llm.py -q`
Expected: all pass (14 + 5 + 7 = 26). If `anthropic` is missing: `python3 -m pip install -e ".[web,dev]"` first.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: scaffold wcg package, migrate core models/store/llm from bwtools"
```

---

### Task 2: core/validation + validate command + full CLI entry

**Files:**
- Create: `wcg/core/validation.py` (from SOURCE `bwtools/commands/validate.py`, minus `run`)
- Create: `wcg/commands/__init__.py` (empty), `wcg/commands/validate.py` (thin wrapper)
- Create: `wcg/__main__.py` (complete final CLI — later tasks only add modules, not CLI edits)
- Copy+rename: SOURCE `tests/test_validate.py` → `tests/test_validate.py`

**Interfaces:**
- Produces: `wcg.core.validation` — `Issue(severity, category_id, message)`, `validate_pool(pool, settings) -> list[Issue]`, `write_report(issues, path)`.
- Produces: `wcg.commands.validate.run(store, settings, report_path) -> int`.
- Produces: `wcg/__main__.py` `main(argv=None)` with subcommands validate/generate/review/localize/compile/stats, global options `--data-dir` (default `data/categories`), `--config-dir` (`config`), `--reports-dir` (`reports`), `--output-dir` (`output`); `require_api_key() -> bool`. Branch imports are lazy, so not-yet-migrated commands don't break the ones that exist.

- [ ] **Step 1: Copy and split validation**

```bash
SRC=/Users/murat/Desktop/Projects/bubble-word-tools
cp $SRC/bwtools/commands/validate.py wcg/core/validation.py
cp $SRC/tests/test_validate.py tests/test_validate.py
```

Edit `wcg/core/validation.py`: delete the `run(store, settings, report_path)` function entirely and delete the now-unused `from ..models import SchemaError` import. Keep `Issue`, `validate_pool`, `_find_cycles`, `_cross_category_reuse`, `write_report` unchanged.

Create `wcg/commands/validate.py`:

```python
from ..core.models import SchemaError
from ..core.validation import validate_pool, write_report


def run(store, settings, report_path):
    try:
        pool = store.load_all()
    except SchemaError as error:
        print(f"ERROR {error}")
        return 1
    issues = validate_pool(pool, settings)
    write_report(issues, report_path)
    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = len(issues) - error_count
    print(f"{len(pool)} categories, {error_count} errors, {warning_count} warnings")
    print(f"report: {report_path}")
    return 1 if error_count else 0
```

Edit `tests/test_validate.py`: `from bwtools.commands.validate import Issue, validate_pool, write_report` → `from wcg.core.validation import Issue, validate_pool, write_report`.

- [ ] **Step 2: Write the full CLI entry**

`wcg/__main__.py`:

```python
import argparse
import json
import os
import sys
from pathlib import Path

from .core.store import CategoryStore
from .commands import validate as validate_cmd


def load_settings(config_dir):
    return json.loads((Path(config_dir) / "settings.json").read_text(encoding="utf-8"))


def require_api_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    print("ERROR ANTHROPIC_API_KEY is not set. Get a key at "
          "https://console.anthropic.com and run: export ANTHROPIC_API_KEY=sk-ant-...")
    return False


def build_parser():
    parser = argparse.ArgumentParser(prog="wcg")
    parser.add_argument("--data-dir", default="data/categories")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--output-dir", default="output")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    generate = sub.add_parser("generate")
    generate.add_argument("--theme")
    generate.add_argument("--count", type=int, default=20)
    generate.add_argument("--parents", action="store_true")
    review = sub.add_parser("review")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_sub.add_parser("export")
    review_import = review_sub.add_parser("import")
    review_import.add_argument("csv_path")
    localize = sub.add_parser("localize")
    localize.add_argument("--locale", required=True)
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("--format", choices=("bubble", "ws"), default="bubble")
    compile_parser.add_argument("--locale")
    sub.add_parser("stats")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config_dir)
    store = CategoryStore(Path(args.data_dir))
    reports_dir = Path(args.reports_dir)
    if args.command == "validate":
        return validate_cmd.run(store, settings, reports_dir / "validation.md")
    if args.command == "generate":
        if not require_api_key():
            return 2
        from .core.llm import LlmClient
        from .commands import generate as generate_cmd
        themes = json.loads(
            (Path(args.config_dir) / "themes.json").read_text(encoding="utf-8"))["themes"]
        llm = LlmClient(settings["model"], settings.get("max_llm_retries", 3))
        if args.parents:
            result = generate_cmd.run_generate_parents(args.count, store, llm, settings)
            print(f"parents: {len(result['accepted'])} accepted, "
                  f"{len(result['rejected'])} rejected")
            return validate_cmd.run(store, settings, reports_dir / "validation.md")
        if not args.theme:
            print("ERROR --theme is required unless --parents is set")
            return 2
        theme_ids = [t["id"] for t in themes] if args.theme == "all" else [args.theme]
        report_lines = []
        for theme_id in theme_ids:
            result = generate_cmd.run_generate(
                theme_id, args.count, store, llm, settings, themes)
            print(f"{theme_id}: {len(result['accepted'])} accepted, "
                  f"{len(result['rejected'])} rejected")
            report_lines += [f"- [{theme_id}] {label}: {reason}"
                             for label, reason in result["rejected"]]
        if report_lines:
            reports_dir.mkdir(parents=True, exist_ok=True)
            with open(reports_dir / "generate.md", "a", encoding="utf-8") as handle:
                handle.write("\n".join(report_lines) + "\n")
        return validate_cmd.run(store, settings, reports_dir / "validation.md")
    if args.command == "review":
        from .commands import review as review_cmd
        if args.review_command == "export":
            count = review_cmd.export_drafts(store, reports_dir / "review.csv")
            print(f"exported {count} drafts to {reports_dir / 'review.csv'}")
            return 0
        try:
            result = review_cmd.import_decisions(store, Path(args.csv_path), settings)
        except review_cmd.ReviewImportError as error:
            print(f"IMPORT ABORTED, no changes applied:\n{error}")
            return 1
        print(f"approved {result['approved']}, rejected {result['rejected']}, "
              f"skipped {result['skipped']}")
        return validate_cmd.run(store, settings, reports_dir / "validation.md")
    if args.command == "localize":
        if not require_api_key():
            return 2
        from .core.llm import LlmClient
        from .core.localize import run_localize
        llm = LlmClient(settings["model"], settings.get("max_llm_retries", 3))
        result = run_localize(args.locale, store, llm, settings)
        print(f"localized {len(result['localized'])}, failed {len(result['failed'])}")
        for cid, reason in result["failed"]:
            print(f"FAILED {cid}: {reason}")
        return 0 if not result["failed"] else 1
    if args.command == "compile":
        from .commands import compile_cmd
        locales = (args.locale.split(",") if args.locale else settings["locales"])
        return compile_cmd.run(store, settings, Path(args.output_dir),
                               args.format, locales)
    if args.command == "stats":
        from .commands import stats as stats_cmd
        return stats_cmd.run(store, settings)
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run tests + CLI smoke**

Run: `python3 -m pytest tests/test_validate.py -q` — expected: 7 passed.
Run: `python3 -m wcg validate`
Expected: `20 categories, 0 errors, 14 warnings` (the migrated animals pool) and exit 0.

- [ ] **Step 4: Commit**

```bash
git add wcg/ tests/test_validate.py
git commit -m "feat: core validation engine, validate command, full wcg CLI entry"
```

---

### Task 3: Migrate generate command (+ parents mode)

**Files:**
- Copy: SOURCE `bwtools/commands/generate.py` → `wcg/commands/generate.py`
- Copy: SOURCE `tests/test_generate.py`, `tests/test_generate_parents.py` → `tests/`

**Interfaces:**
- Consumes: `wcg.core.models.Category/SchemaError`, `wcg.core.store.CategoryStore`.
- Produces: `wcg.commands.generate` — `generation_system(item_min, item_max)`, `build_user_prompt(theme, count, existing_names, existing_words, all_ids)`, `run_generate(theme_id, count, store, llm, settings, themes) -> dict`, `parents_system(item_min, item_max)`, `run_generate_parents(count, store, llm, settings) -> dict` (all behavior identical to bwtools).

- [ ] **Step 1: Copy and rename imports**

```bash
SRC=/Users/murat/Desktop/Projects/bubble-word-tools
cp $SRC/bwtools/commands/generate.py wcg/commands/generate.py
cp $SRC/tests/test_generate.py $SRC/tests/test_generate_parents.py tests/
```

- `wcg/commands/generate.py`: `from ..models import Category, SchemaError` → `from ..core.models import Category, SchemaError`
- `tests/test_generate.py`: `from bwtools.commands.generate import ...` → `from wcg.commands.generate import ...`; `from bwtools.store import CategoryStore` → `from wcg.core.store import CategoryStore`
- `tests/test_generate_parents.py`: same two rename patterns.

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/test_generate.py tests/test_generate_parents.py -q`
Expected: 9 passed (5 + 4).

- [ ] **Step 3: Commit**

```bash
git add wcg/commands/generate.py tests/test_generate.py tests/test_generate_parents.py
git commit -m "feat: migrate generate command with parents mode"
```

---

### Task 4: core/localize with per-category engine

**Files:**
- Create: `wcg/core/localize.py` (refactored from SOURCE `bwtools/commands/localize.py`)
- Copy: SOURCE `tests/test_localize.py` → `tests/test_localize.py`
- Test (new cases appended): `tests/test_localize.py`

**Interfaces:**
- Produces: `wcg.core.localize` — `localize_system(locale) -> str`; `localize_category(category, locale, llm) -> tuple[str, str | None]` returning `("skipped", None)` when the locale is already complete (no LLM call), `("localized", None)` on success (category mutated in place, NOT saved), `("failed", reason)` on invalid payload or duplicate localized words (category untouched); `LlmError` propagates to the caller. `run_localize(locale, store, llm, settings) -> dict` — same external behavior as bwtools (`{"localized": [ids], "failed": [(id, reason)]}`; saves on success; catches LlmError per category).
- The web select flow (Task 8) calls `localize_category` directly.

- [ ] **Step 1: Copy the old module and test**

```bash
SRC=/Users/murat/Desktop/Projects/bubble-word-tools
cp $SRC/tests/test_localize.py tests/test_localize.py
```

Edit `tests/test_localize.py` imports: `from bwtools.commands.localize import run_localize` → `from wcg.core.localize import run_localize`; `from bwtools.llm import LlmError` → `from wcg.core.llm import LlmError`; `from bwtools.store import CategoryStore` → `from wcg.core.store import CategoryStore`.

- [ ] **Step 2: Append new tests for localize_category**

Append to `tests/test_localize.py`:

```python
from wcg.core.localize import localize_category


def test_localize_category_skips_complete(tmp_path):
    category = make_category(cid="done", status="approved",
                             names={"en": "Done", "tr": "Bitti"})
    for item in category.items:
        item.word["tr"] = item.word["en"] + "-tr"
    llm = FakeLlm([])
    assert localize_category(category, "tr", llm) == ("skipped", None)
    assert llm.calls == []


def test_localize_category_mutates_but_does_not_save(tmp_path):
    store = CategoryStore(tmp_path)
    category = make_category(cid="birds", status="approved")
    store.save(category)
    llm = FakeLlm([{"name": "Kuşlar",
                    "words": ["Güvercin", "Karga", "Kartal", "Baykuş"]}])
    outcome, reason = localize_category(category, "tr", llm)
    assert (outcome, reason) == ("localized", None)
    assert category.names["tr"] == "Kuşlar"
    assert "tr" not in store.load_all()["birds"].names


def test_localize_category_failure_reason():
    category = make_category(cid="birds", status="approved")
    llm = FakeLlm([{"name": "Kuşlar", "words": ["At", "at", "Kartal", "Baykuş"]}])
    assert localize_category(category, "tr", llm) == ("failed", "duplicate localized words")
```

(Place the import at the top of the file with the other imports.)

- [ ] **Step 3: Run tests to verify the new ones fail**

Run: `python3 -m pytest tests/test_localize.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'wcg.core.localize'`

- [ ] **Step 4: Write `wcg/core/localize.py`**

```python
import json

from .llm import LlmError


def localize_system(locale):
    return (
        f"You localize word-game categories into the language with code '{locale}'.\n"
        "Given a category name and its words in English, produce natural equivalents "
        "in the target language - NOT literal translations. Words may change for "
        "cultural fit but must stay in the same association category, same order, "
        "same count.\n"
        'Return ONLY a JSON object: {"name": "...", "words": ["..."]}'
    )


def localize_category(category, locale, llm):
    word_items = [item for item in category.items if item.word]
    if locale in category.names and all(locale in item.word for item in word_items):
        return "skipped", None
    payload = json.dumps(
        {"name": category.names["en"],
         "words": [item.word["en"] for item in word_items]},
        ensure_ascii=False)
    raw = llm.complete_json(localize_system(locale), payload)
    if (not isinstance(raw, dict)
            or not isinstance(raw.get("name"), str) or not raw["name"].strip()
            or not isinstance(raw.get("words"), list)
            or len(raw["words"]) != len(word_items)
            or not all(isinstance(w, str) and w.strip() for w in raw["words"])):
        return "failed", "invalid localization payload"
    lowered = [w.strip().lower() for w in raw["words"]]
    if len(set(lowered)) != len(lowered):
        return "failed", "duplicate localized words"
    category.names[locale] = raw["name"].strip()
    for item, word in zip(word_items, raw["words"]):
        item.word[locale] = word.strip()
    return "localized", None


def run_localize(locale, store, llm, settings):
    localized, failed = [], []
    for category in sorted(store.by_status("approved"), key=lambda c: c.id):
        try:
            outcome, reason = localize_category(category, locale, llm)
        except LlmError as error:
            failed.append((category.id, str(error)))
            continue
        if outcome == "failed":
            failed.append((category.id, reason))
        elif outcome == "localized":
            store.save(category)
            localized.append(category.id)
    return {"localized": localized, "failed": failed}
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_localize.py -q`
Expected: 8 passed (5 migrated + 3 new).

- [ ] **Step 6: Commit**

```bash
git add wcg/core/localize.py tests/test_localize.py
git commit -m "feat: core localize engine with per-category API"
```

---

### Task 5: Migrate review command

**Files:**
- Copy: SOURCE `bwtools/commands/review.py` → `wcg/commands/review.py`
- Copy: SOURCE `tests/test_review.py` → `tests/test_review.py`

**Interfaces:**
- Produces: `wcg.commands.review` — `export_drafts(store, csv_path) -> int`, `import_decisions(store, csv_path, settings) -> dict`, `ReviewImportError` (behavior identical to bwtools, including duplicate-row abort).

- [ ] **Step 1: Copy and rename imports**

```bash
SRC=/Users/murat/Desktop/Projects/bubble-word-tools
cp $SRC/bwtools/commands/review.py wcg/commands/review.py
cp $SRC/tests/test_review.py tests/test_review.py
```

- `wcg/commands/review.py`: `from ..models import ID_PATTERN, Item` → `from ..core.models import ID_PATTERN, Item`
- `tests/test_review.py`: `from bwtools.commands.review import ...` → `from wcg.commands.review import ...`; `from bwtools.store import CategoryStore` → `from wcg.core.store import CategoryStore`

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest tests/test_review.py -q`
Expected: 12 passed.

- [ ] **Step 3: Commit**

```bash
git add wcg/commands/review.py tests/test_review.py
git commit -m "feat: migrate CSV review command"
```

---

### Task 6: Games adapters + compile + stats + README (CLI parity complete)

**Files:**
- Create: `wcg/games/__init__.py` (empty)
- Copy: SOURCE `bwtools/formats/game.py` → `wcg/games/bubble.py`; `bwtools/formats/ws.py` → `wcg/games/ws.py`
- Copy: SOURCE `bwtools/commands/compile_cmd.py` → `wcg/commands/compile_cmd.py`; `bwtools/commands/stats.py` → `wcg/commands/stats.py`
- Copy: SOURCE `tests/test_compile.py`, `tests/test_stats.py` → `tests/`
- Create: `README.md`

**Interfaces:**
- Produces: `wcg.games.bubble.compile_bubble(pool, locales) -> tuple[dict, list[str]]` (the former `compile_game`, renamed); `wcg.games.ws.compile_ws(pool, locale) -> tuple[list, list[str]]`; `wcg.commands.compile_cmd.run(store, settings, output_dir, fmt, locales) -> int` where `fmt` is `"bubble"` or `"ws"` and bubble output file is `output/categories_bubble.json`; `wcg.commands.stats` — `compute_stats(pool, locales) -> dict`, `run(store, settings) -> int`.

- [ ] **Step 1: Copy and rename**

```bash
SRC=/Users/murat/Desktop/Projects/bubble-word-tools
mkdir -p wcg/games && touch wcg/games/__init__.py
cp $SRC/bwtools/formats/game.py wcg/games/bubble.py
cp $SRC/bwtools/formats/ws.py wcg/games/ws.py
cp $SRC/bwtools/commands/compile_cmd.py wcg/commands/compile_cmd.py
cp $SRC/bwtools/commands/stats.py wcg/commands/stats.py
cp $SRC/tests/test_compile.py $SRC/tests/test_stats.py tests/
```

Renames:
- `wcg/games/bubble.py`: rename function `compile_game` → `compile_bubble` (only the def line; body unchanged).
- `wcg/commands/compile_cmd.py`: imports → `from ..core.validation import validate_pool`, `from ..games.bubble import compile_bubble`, `from ..games.ws import compile_ws`; the format branch `if fmt == "game":` → `if fmt == "bubble":`; `compile_game(pool, locales)` call → `compile_bubble(pool, locales)`; output filename `"categories_game.json"` → `"categories_bubble.json"`.
- `wcg/commands/stats.py`: no import changes needed (uses only `collections.Counter`).
- `tests/test_compile.py`: `from bwtools.formats.game import compile_game` → `from wcg.games.bubble import compile_bubble`; `from bwtools.formats.ws import compile_ws` → `from wcg.games.ws import compile_ws`; every `compile_game(` call → `compile_bubble(`; any `from bwtools.commands.compile_cmd import` / `from bwtools.commands import compile_cmd` → `wcg.commands` equivalents; any `from bwtools.store import` → `from wcg.core.store import`.
- `tests/test_stats.py`: `from bwtools.commands.stats import compute_stats` → `from wcg.commands.stats import compute_stats`.

- [ ] **Step 2: Write README.md**

```markdown
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
    # it is saved as approved with translations.
    # Pool tab: browse the category pool.

## CLI

    python3 -m wcg generate --theme animals --count 20
    python3 -m wcg generate --theme all
    python3 -m wcg generate --parents --count 10
    python3 -m wcg validate
    python3 -m wcg review export
    python3 -m wcg review import reports/review.csv
    python3 -m wcg localize --locale tr
    python3 -m wcg compile --format bubble
    python3 -m wcg compile --format ws --locale en,tr
    python3 -m wcg stats

Categories live in `data/categories/` (one JSON file each, committed).
`reports/` and `output/` are generated and gitignored.

Design specs: `docs/superpowers/specs/`

## Tests

    python3 -m pytest
```

- [ ] **Step 3: Run the full suite + CLI smoke**

Run: `python3 -m pytest -q`
Expected: every test green (0 failures) — the exact total comes from pytest; do not hand-count.
Run: `python3 -m wcg stats; python3 -m wcg compile --format bubble; python3 -m wcg compile --format ws`
Expected: stats shows `total: 20`; both compile runs exit 1 with warnings (pool is all drafts — zero approved categories emitted is the designed exit-1 path), files still written under `output/`. Do not chain these with `&&` — the expected exit 1 would stop the chain.

- [ ] **Step 4: Commit**

```bash
git add wcg/games/ wcg/commands/compile_cmd.py wcg/commands/stats.py tests/test_compile.py tests/test_stats.py README.md
git commit -m "feat: migrate game adapters, compile and stats; full CLI parity"
```

---

### Task 7: core/propose (topic → variants)

**Files:**
- Create: `wcg/core/propose.py`
- Test: `tests/test_propose.py`

**Interfaces:**
- Consumes: `CategoryStore`, `FakeLlm`, `make_category`.
- Produces: `propose_system(item_min, item_max, variants, theme_ids) -> str`; `build_propose_prompt(topic, existing_names, existing_words) -> str`; `validate_variant(entry, theme_ids, settings) -> tuple[dict | None, str | None]` (validated variant `{"name", "theme", "difficulty", "words"}` with unknown theme mapped to `"other"`, or `(None, reason)`); `run_propose(topic, store, llm, settings, themes) -> list[dict]` (stateless: reads the pool for dedup context, writes nothing, drops invalid variants silently).
- Used by Task 8's `/api/propose` and `/api/select`.

- [ ] **Step 1: Write the failing tests**

`tests/test_propose.py`:

```python
import pytest

from wcg.core.propose import build_propose_prompt, run_propose, validate_variant
from wcg.core.store import CategoryStore
from tests.conftest import FakeLlm, make_category

SETTINGS = {"item_min": 4, "item_max": 5, "propose_variants": 3}
THEMES = [{"id": "animals", "hint": "animal kingdom"}]


def entry(name="Planets", words=("Mars", "Venus", "Jupiter", "Saturn"),
          theme="animals", difficulty=1):
    return {"name": name, "theme": theme, "difficulty": difficulty,
            "words": list(words)}


def test_valid_variant_passes():
    variant, reason = validate_variant(entry(), ["animals"], SETTINGS)
    assert reason is None
    assert variant == {"name": "Planets", "theme": "animals", "difficulty": 1,
                       "words": ["Mars", "Venus", "Jupiter", "Saturn"]}


def test_unknown_theme_maps_to_other():
    variant, _ = validate_variant(entry(theme="space"), ["animals"], SETTINGS)
    assert variant["theme"] == "other"


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(name=""),
    lambda e: e.update(words=["a", "b"]),
    lambda e: e.update(words=["Mars", "mars", "Venus", "Pluto"]),
    lambda e: e.update(difficulty=9),
    lambda e: e.pop("words"),
])
def test_invalid_variants_rejected(mutate):
    data = entry()
    mutate(data)
    variant, reason = validate_variant(data, ["animals"], SETTINGS)
    assert variant is None
    assert reason


def test_run_propose_drops_invalid_and_includes_dedup_context(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", theme="animals"))
    llm = FakeLlm([[entry(), entry(words=("a", "b")), "garbage"]])
    variants = run_propose("planets", store, llm, SETTINGS, THEMES)
    assert len(variants) == 1
    system, user = llm.calls[0]
    assert "Topic: planets" in user
    assert "Birds" in user
    assert "pigeon" in user
    assert "animals" in system


def test_prompt_without_pool_context():
    prompt = build_propose_prompt("planets", [], [])
    assert prompt == "Topic: planets"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_propose.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'wcg.core.propose'`

- [ ] **Step 3: Write `wcg/core/propose.py`**

```python
def propose_system(item_min, item_max, variants, theme_ids):
    return (
        "You suggest word-association categories for a mobile word game.\n"
        f"Given a topic, return ONLY a JSON array of exactly {variants} distinct "
        "interpretations of that topic. Each element:\n"
        '{"name": "<Category Name>", "theme": "<theme-id>", "difficulty": 1, '
        '"words": ["..."]}\n'
        f"Each variant must have between {item_min} and {item_max} words.\n"
        "Variants must differ meaningfully: a different angle, specificity, "
        "or word set.\n"
        "STRONGLY prefer easy, internationally understandable words: "
        "cross-language cognates and proper nouns (Uranus, Jupiter, Pizza, Taxi).\n"
        f"'theme' must be one of: {', '.join(theme_ids)} - or 'other' if none fits.\n"
        "Difficulty: 1 = internationally transparent everyday words, "
        "2 = common but language-dependent, 3 = niche."
    )


def build_propose_prompt(topic, existing_names, existing_words):
    lines = [f"Topic: {topic}"]
    if existing_names:
        lines.append("Existing category names (do not duplicate): "
                     + ", ".join(existing_names))
    if existing_words:
        lines.append("Words already in the pool (prefer alternatives): "
                     + ", ".join(existing_words))
    return "\n".join(lines)


def validate_variant(entry, theme_ids, settings):
    if not isinstance(entry, dict):
        return None, "not an object"
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        return None, "missing name"
    words = entry.get("words")
    if not isinstance(words, list) or not all(
            isinstance(w, str) and w.strip() for w in words):
        return None, "words must be a list of non-empty strings"
    if not settings["item_min"] <= len(words) <= settings["item_max"]:
        return None, (f"{len(words)} words, expected "
                      f"{settings['item_min']}-{settings['item_max']}")
    lowered = [w.strip().lower() for w in words]
    if len(set(lowered)) != len(lowered):
        return None, "duplicate words"
    difficulty = entry.get("difficulty")
    if not isinstance(difficulty, int) or isinstance(difficulty, bool) \
            or not 1 <= difficulty <= 3:
        return None, "difficulty must be an integer 1-3"
    theme = entry.get("theme")
    if not isinstance(theme, str) or theme not in theme_ids:
        theme = "other"
    return {"name": name.strip(), "theme": theme, "difficulty": difficulty,
            "words": [w.strip() for w in words]}, None


def run_propose(topic, store, llm, settings, themes):
    pool = store.load_all()
    existing_names = sorted(c.names["en"] for c in pool.values())
    existing_words = sorted({w.strip().lower()
                             for c in pool.values() for w in c.words_for("en")})
    theme_ids = [t["id"] for t in themes]
    raw = llm.complete_json(
        propose_system(settings["item_min"], settings["item_max"],
                       settings.get("propose_variants", 3), theme_ids),
        build_propose_prompt(topic, existing_names, existing_words))
    variants = []
    for entry in raw if isinstance(raw, list) else []:
        variant, _ = validate_variant(entry, theme_ids, settings)
        if variant:
            variants.append(variant)
    return variants
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_propose.py -q`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add wcg/core/propose.py tests/test_propose.py
git commit -m "feat: propose engine (topic to candidate variants)"
```

---

### Task 8: Web API (FastAPI app + wcg-serve)

**Files:**
- Create: `wcg/web/__init__.py` (empty), `wcg/web/app.py`, `wcg/web/static/.gitkeep` (placeholder so StaticFiles mount works before Task 9)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `run_propose`, `validate_variant` (Task 7), `localize_category` (Task 4), `compute_stats` (Task 6), `Category`, `CategoryStore`, `LlmError`.
- Produces: `wcg.web.app.create_app(data_dir="data/categories", config_dir="config", llm_factory=None) -> FastAPI` (llm_factory: zero-arg callable returning an LlmClient-compatible object or None; default factory returns None when `ANTHROPIC_API_KEY` is unset); `slugify(name) -> str`; `unique_id(slug, pool) -> str`; `run()` (uvicorn on `PORT` env or 8000). Endpoints per spec: GET `/api/health`, POST `/api/propose`, POST `/api/select`, GET `/api/categories?status=&theme=`, GET `/api/stats`; static mount at `/`.

- [ ] **Step 1: Write the failing tests**

`tests/test_web.py`:

```python
import json

from fastapi.testclient import TestClient

from wcg.core.llm import LlmError
from wcg.core.store import CategoryStore
from wcg.web.app import create_app, slugify
from tests.conftest import FakeLlm, make_category

SETTINGS = {"model": "m", "item_min": 4, "item_max": 5,
            "locales": ["en", "tr"], "propose_variants": 3,
            "max_llm_retries": 3}
THEMES = {"themes": [{"id": "animals", "hint": "animal kingdom"}]}


def build_client(tmp_path, llm):
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")
    (config / "themes.json").write_text(json.dumps(THEMES), encoding="utf-8")
    data = tmp_path / "categories"
    data.mkdir(exist_ok=True)
    app = create_app(data_dir=data, config_dir=config, llm_factory=lambda: llm)
    return TestClient(app), CategoryStore(data)


def variant(name="Planets", words=("Mars", "Venus", "Jupiter", "Saturn")):
    return {"name": name, "theme": "animals", "difficulty": 1,
            "words": list(words)}


def test_health(tmp_path):
    client, _ = build_client(tmp_path, None)
    assert client.get("/api/health").json() == {"status": "ok"}


def test_slugify():
    assert slugify("Gas Giants!") == "gas-giants"
    assert slugify("  ") == "category"


def test_propose_returns_valid_variants_only(tmp_path):
    llm = FakeLlm([[variant(),
                    variant("Gas Giants", ("Jupiter", "Saturn", "Uranus", "Neptune")),
                    "garbage"]])
    client, _ = build_client(tmp_path, llm)
    response = client.post("/api/propose", json={"topic": "planets"})
    assert response.status_code == 200
    assert [v["name"] for v in response.json()["variants"]] == ["Planets", "Gas Giants"]


def test_propose_without_api_key_returns_503(tmp_path):
    client, _ = build_client(tmp_path, None)
    assert client.post("/api/propose", json={"topic": "planets"}).status_code == 503


def test_propose_empty_topic_returns_400(tmp_path):
    client, _ = build_client(tmp_path, FakeLlm([]))
    assert client.post("/api/propose", json={"topic": "   "}).status_code == 400


def test_propose_llm_error_returns_502(tmp_path):
    client, _ = build_client(tmp_path, FakeLlm([LlmError("down")]))
    response = client.post("/api/propose", json={"topic": "planets"})
    assert response.status_code == 502
    assert "down" in response.json()["error"]


def test_select_saves_approved_and_localizes(tmp_path):
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, store = build_client(tmp_path, llm)
    response = client.post("/api/select", json={"variant": variant()})
    assert response.status_code == 200
    assert response.json()["warnings"] == []
    saved = store.load_all()["planets"]
    assert saved.status == "approved"
    assert saved.names == {"en": "Planets", "tr": "Gezegenler"}
    assert saved.words_for("tr") == ["Mars", "Venüs", "Jüpiter", "Satürn"]


def test_select_localization_failure_still_saves_en_only(tmp_path):
    llm = FakeLlm([LlmError("boom")])
    client, store = build_client(tmp_path, llm)
    response = client.post("/api/select", json={"variant": variant()})
    assert response.status_code == 200
    assert "boom" in response.json()["warnings"][0]
    saved = store.load_all()["planets"]
    assert saved.status == "approved"
    assert "tr" not in saved.names


def test_select_id_collision_gets_suffix(tmp_path):
    llm = FakeLlm([
        {"name": "Gezegenler", "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]},
        {"name": "Gezegenler", "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]},
    ])
    client, _ = build_client(tmp_path, llm)
    client.post("/api/select", json={"variant": variant()})
    response = client.post("/api/select", json={"variant": variant()})
    assert response.json()["category"]["id"] == "planets-2"


def test_select_invalid_variant_returns_400(tmp_path):
    client, _ = build_client(tmp_path, FakeLlm([]))
    response = client.post("/api/select",
                           json={"variant": {"name": "X", "words": ["a"]}})
    assert response.status_code == 400


def test_categories_listing_and_filters(tmp_path):
    client, store = build_client(tmp_path, None)
    store.save(make_category(cid="birds", theme="animals", status="approved",
                             words=("Pigeon", "Crow", "Eagle"), refs=("owls",)))
    store.save(make_category(cid="pizza", theme="food", status="draft"))
    data = client.get("/api/categories", params={"status": "approved"}).json()
    assert len(data["categories"]) == 1
    entry = data["categories"][0]
    assert entry["id"] == "birds"
    assert entry["items"] == ["Pigeon", "Crow", "Eagle", "-> owls"]


def test_stats_endpoint(tmp_path):
    client, store = build_client(tmp_path, None)
    store.save(make_category(cid="birds", status="approved"))
    stats = client.get("/api/stats").json()
    assert stats["total"] == 1
    assert stats["by_status"] == {"approved": 1}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_web.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'wcg.web'` (install `.[web,dev]` first if fastapi/httpx are missing).

- [ ] **Step 3: Write `wcg/web/app.py`** (and empty `wcg/web/__init__.py`, `wcg/web/static/.gitkeep`)

```python
import json
import os
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..commands.stats import compute_stats
from ..core.llm import LlmError
from ..core.localize import localize_category
from ..core.models import Category
from ..core.propose import run_propose, validate_variant
from ..core.store import CategoryStore


class ProposeBody(BaseModel):
    topic: str


class SelectBody(BaseModel):
    variant: dict


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "category"


def unique_id(slug, pool):
    if slug not in pool:
        return slug
    suffix = 2
    while f"{slug}-{suffix}" in pool:
        suffix += 1
    return f"{slug}-{suffix}"


def create_app(data_dir="data/categories", config_dir="config", llm_factory=None):
    app = FastAPI()
    store = CategoryStore(Path(data_dir))
    config_path = Path(config_dir)
    settings = json.loads((config_path / "settings.json").read_text(encoding="utf-8"))
    themes = json.loads((config_path / "themes.json").read_text(encoding="utf-8"))["themes"]
    theme_ids = [t["id"] for t in themes]

    def default_factory():
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        from ..core.llm import LlmClient
        return LlmClient(settings["model"], settings.get("max_llm_retries", 3))

    factory = llm_factory or default_factory

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/propose")
    def propose(body: ProposeBody):
        llm = factory()
        if llm is None:
            return JSONResponse({"error": "ANTHROPIC_API_KEY is not set"},
                                status_code=503)
        topic = body.topic.strip()
        if not topic:
            return JSONResponse({"error": "topic is empty"}, status_code=400)
        try:
            variants = run_propose(topic, store, llm, settings, themes)
        except LlmError as error:
            return JSONResponse({"error": str(error)}, status_code=502)
        return {"variants": variants}

    @app.post("/api/select")
    def select(body: SelectBody):
        llm = factory()
        if llm is None:
            return JSONResponse({"error": "ANTHROPIC_API_KEY is not set"},
                                status_code=503)
        variant, reason = validate_variant(body.variant, theme_ids, settings)
        if variant is None:
            return JSONResponse({"error": f"invalid variant: {reason}"},
                                status_code=400)
        pool = store.load_all()
        cid = unique_id(slugify(variant["name"]), pool)
        category = Category.from_dict({
            "id": cid,
            "theme": variant["theme"],
            "difficulty": variant["difficulty"],
            "image": None,
            "status": "approved",
            "items": [{"word": {"en": word}} for word in variant["words"]],
            "names": {"en": variant["name"]},
        })
        warnings = []
        for locale in settings["locales"]:
            if locale == "en":
                continue
            try:
                outcome, failure = localize_category(category, locale, llm)
                if outcome == "failed":
                    warnings.append(f"{locale}: {failure}")
            except LlmError as error:
                warnings.append(f"{locale}: {error}")
        store.save(category)
        return {"category": category.to_dict(), "warnings": warnings}

    @app.get("/api/categories")
    def categories(status: str = "", theme: str = ""):
        rows = []
        for category in sorted(store.load_all().values(), key=lambda c: c.id):
            if status and category.status != status:
                continue
            if theme and category.theme != theme:
                continue
            items = [item.word["en"] if item.word else f"-> {item.ref}"
                     for item in category.items]
            rows.append({"id": category.id, "name": category.names["en"],
                         "theme": category.theme, "status": category.status,
                         "difficulty": category.difficulty, "items": items})
        return {"categories": rows}

    @app.get("/api/stats")
    def stats():
        return compute_stats(store.load_all(), settings["locales"])

    app.mount("/", StaticFiles(directory=Path(__file__).parent / "static",
                               html=True), name="static")
    return app


def run():
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0",
                port=int(os.environ.get("PORT", "8000")))
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_web.py -q`
Expected: 12 passed.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: everything green.

- [ ] **Step 6: Commit**

```bash
git add wcg/web/ tests/test_web.py
git commit -m "feat: FastAPI web API (propose, select, categories, stats)"
```

---

### Task 9: Static UI + archive + docs migration + final verification

**Files:**
- Create: `wcg/web/static/index.html`, `wcg/web/static/style.css`, `wcg/web/static/app.js` (delete `wcg/web/static/.gitkeep`)
- Copy: SOURCE `docs/superpowers/specs/2026-07-14-category-generator-design.md` and `docs/superpowers/plans/2026-07-14-category-generator.md` → same paths in this repo (historical record)
- Modify (in SOURCE repo): append archive note to `/Users/murat/Desktop/Projects/bubble-word-tools/README.md` and commit there

**Interfaces:**
- Consumes: the Task 8 API endpoints exactly as specified.
- Produces: the two-tab UI at `/`.

- [ ] **Step 1: Write `wcg/web/static/index.html`**

```html
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Word Content Generator</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header>
  <h1>Word Content Generator</h1>
  <nav>
    <button id="tab-generate" class="tab active">Generate</button>
    <button id="tab-pool" class="tab">Pool</button>
  </nav>
</header>
<main>
  <section id="view-generate">
    <form id="propose-form">
      <input id="topic" type="text" placeholder="Type a topic, e.g. planets"
             autocomplete="off" required>
      <button id="suggest-btn" type="submit">Suggest</button>
    </form>
    <p id="generate-status"></p>
    <div id="variants"></div>
  </section>
  <section id="view-pool" hidden>
    <p id="pool-stats"></p>
    <div id="pool-filters">
      <select id="filter-theme"><option value="">All themes</option></select>
      <select id="filter-status"><option value="">All statuses</option></select>
    </div>
    <table id="pool-table">
      <thead>
        <tr><th>Name</th><th>Theme</th><th>Status</th><th>Difficulty</th><th>Items</th></tr>
      </thead>
      <tbody></tbody>
    </table>
  </section>
</main>
<script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `wcg/web/static/style.css`**

```css
* { box-sizing: border-box; margin: 0; }
body { font-family: system-ui, sans-serif; color: #1a1a2e; background: #f7f7fb; }
header { display: flex; align-items: center; gap: 24px; padding: 16px 24px;
         background: #fff; border-bottom: 1px solid #e2e2ee; }
h1 { font-size: 18px; }
nav { display: flex; gap: 8px; }
.tab { padding: 8px 16px; border: 1px solid #d0d0e0; background: #fff;
       border-radius: 8px; cursor: pointer; font-size: 14px; }
.tab.active { background: #3b3b98; color: #fff; border-color: #3b3b98; }
main { max-width: 960px; margin: 24px auto; padding: 0 16px; }
#propose-form { display: flex; gap: 8px; }
#topic { flex: 1; padding: 10px 14px; border: 1px solid #d0d0e0;
         border-radius: 8px; font-size: 15px; }
#suggest-btn { padding: 10px 20px; border: 0; border-radius: 8px;
               background: #3b3b98; color: #fff; font-size: 15px; cursor: pointer; }
#suggest-btn:disabled, #topic:disabled { opacity: 0.5; }
#generate-status { margin: 12px 2px; min-height: 20px; font-size: 14px; }
#variants { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 12px; }
.card { background: #fff; border: 1px solid #e2e2ee; border-radius: 12px;
        padding: 16px; display: flex; flex-direction: column; gap: 8px; }
.card h3 { font-size: 16px; }
.card .meta { font-size: 12px; color: #6b6b8a; }
.card .words { font-size: 14px; line-height: 1.5; flex: 1; }
.card button { align-self: flex-start; padding: 8px 14px; border: 0;
               border-radius: 8px; background: #10ac84; color: #fff; cursor: pointer; }
#pool-stats { margin-bottom: 12px; font-size: 14px; color: #6b6b8a; }
#pool-filters { display: flex; gap: 8px; margin-bottom: 12px; }
#pool-filters select { padding: 8px 12px; border: 1px solid #d0d0e0;
                       border-radius: 8px; }
#pool-table { width: 100%; border-collapse: collapse; background: #fff;
              border: 1px solid #e2e2ee; border-radius: 12px; overflow: hidden; }
#pool-table th, #pool-table td { text-align: left; padding: 10px 12px;
                                 border-bottom: 1px solid #eee; font-size: 14px; }
#pool-table th { background: #fafafd; font-weight: 600; }
```

- [ ] **Step 3: Write `wcg/web/static/app.js`**

```javascript
const $ = (id) => document.getElementById(id);

function switchTab(name) {
  $("view-generate").hidden = name !== "generate";
  $("view-pool").hidden = name !== "pool";
  $("tab-generate").classList.toggle("active", name === "generate");
  $("tab-pool").classList.toggle("active", name === "pool");
  if (name === "pool") loadPool();
}
$("tab-generate").onclick = () => switchTab("generate");
$("tab-pool").onclick = () => switchTab("pool");

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function setBusy(busy, message) {
  $("suggest-btn").disabled = busy;
  $("topic").disabled = busy;
  if (message !== undefined) $("generate-status").textContent = message || "";
}

$("propose-form").onsubmit = async (event) => {
  event.preventDefault();
  const topic = $("topic").value.trim();
  if (!topic) return;
  setBusy(true, "Asking the model for suggestions...");
  $("variants").innerHTML = "";
  try {
    const data = await api("/api/propose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    });
    renderVariants(data.variants);
    $("generate-status").textContent = data.variants.length
      ? "Pick one to add it to the pool:"
      : "No valid suggestions returned - try again.";
  } catch (error) {
    $("generate-status").textContent = "Error: " + error.message;
  } finally {
    setBusy(false, undefined);
  }
};

function renderVariants(variants) {
  const container = $("variants");
  container.innerHTML = "";
  variants.forEach((variant) => {
    const card = document.createElement("div");
    card.className = "card";
    const title = document.createElement("h3");
    title.textContent = variant.name;
    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = `theme: ${variant.theme} · difficulty: ${variant.difficulty}`;
    const words = document.createElement("p");
    words.className = "words";
    words.textContent = variant.words.join(" · ");
    const button = document.createElement("button");
    button.textContent = "Pick this one";
    button.onclick = () => select(variant);
    card.append(title, meta, words, button);
    container.appendChild(card);
  });
}

async function select(variant) {
  setBusy(true, "Saving and localizing...");
  try {
    const data = await api("/api/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ variant }),
    });
    const warnings = data.warnings.length
      ? ` (warnings: ${data.warnings.join("; ")})` : "";
    $("generate-status").textContent =
      `Saved "${data.category.names.en}" as ${data.category.id}${warnings}`;
    $("variants").innerHTML = "";
    $("topic").value = "";
  } catch (error) {
    $("generate-status").textContent = "Error: " + error.message;
  } finally {
    setBusy(false, undefined);
  }
}

let poolCategories = [];

async function loadPool() {
  try {
    const stats = await api("/api/stats");
    $("pool-stats").textContent = `${stats.total} categories · ` +
      Object.entries(stats.by_status).map(([k, v]) => `${k}: ${v}`).join(" · ");
    const data = await api("/api/categories");
    poolCategories = data.categories;
    fillFilters(poolCategories);
    renderPool();
  } catch (error) {
    $("pool-stats").textContent = "Error: " + error.message;
  }
}

function fillFilters(categories) {
  fillSelect($("filter-theme"), "All themes",
             [...new Set(categories.map((c) => c.theme))].sort());
  fillSelect($("filter-status"), "All statuses",
             [...new Set(categories.map((c) => c.status))].sort());
}

function fillSelect(select, allLabel, values) {
  const current = select.value;
  select.innerHTML = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = allLabel;
  select.appendChild(all);
  values.forEach((value) => {
    const option = document.createElement("option");
    option.textContent = value;
    select.appendChild(option);
  });
  select.value = current;
}

$("filter-theme").onchange = renderPool;
$("filter-status").onchange = renderPool;

function renderPool() {
  const theme = $("filter-theme").value;
  const status = $("filter-status").value;
  const body = $("pool-table").querySelector("tbody");
  body.innerHTML = "";
  poolCategories
    .filter((c) => (!theme || c.theme === theme) && (!status || c.status === status))
    .forEach((c) => {
      const row = document.createElement("tr");
      [c.name, c.theme, c.status, c.difficulty, c.items.join(" · ")]
        .forEach((value) => {
          const cell = document.createElement("td");
          cell.textContent = String(value);
          row.appendChild(cell);
        });
      body.appendChild(row);
    });
}
```

Delete `wcg/web/static/.gitkeep`.

- [ ] **Step 4: Smoke-test the UI**

```bash
wcg-serve &
sleep 2
curl -s http://localhost:8000/api/health
curl -s http://localhost:8000/ | head -5
curl -s http://localhost:8000/api/categories | head -c 200
kill %1
```

Expected: health `{"status":"ok"}`, HTML doctype served at `/`, categories JSON with the 20 animals entries. (Propose/select need the API key — covered by unit tests; live check happens in final verification.)

- [ ] **Step 5: Migrate historical docs + archive the old repo**

```bash
SRC=/Users/murat/Desktop/Projects/bubble-word-tools
mkdir -p docs/superpowers/plans
cp $SRC/docs/superpowers/specs/2026-07-14-category-generator-design.md docs/superpowers/specs/
cp $SRC/docs/superpowers/plans/2026-07-14-category-generator.md docs/superpowers/plans/
```

Append to `/Users/murat/Desktop/Projects/bubble-word-tools/README.md`:

```markdown

## Superseded

This repo has been absorbed into `word-content-generator` (game-agnostic
platform: same core + web UI). It is kept as a frozen archive; develop there.
```

Commit in the SOURCE repo: `cd $SRC && git add README.md && git commit -m "docs: archived - superseded by word-content-generator"`.

- [ ] **Step 6: Final verification + commit**

Run: `python3 -m pytest -q` — all green.
Run: `python3 -m wcg stats` — total: 20.

```bash
git add wcg/web/static/ docs/
git commit -m "feat: two-tab web UI; migrate historical docs; archive bubble-word-tools"
```

---

## Final Verification

- [ ] `python3 -m pytest -q` — full suite green.
- [ ] `python3 -m wcg validate && python3 -m wcg stats` — exit 0, 20 categories.
- [ ] Live check (requires `ANTHROPIC_API_KEY`, run by the user/controller, not automated): `wcg-serve` → browser → topic "planets" → up to 3 variants → pick one → saved approved with en+tr → visible in Pool tab → `python3 -m wcg compile --format bubble` includes it.
