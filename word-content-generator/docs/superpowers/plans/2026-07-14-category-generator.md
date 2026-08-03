# Category Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `bwtools` Python CLI that generates, validates, reviews, localizes, and compiles word-association categories for the bubble word game.

**Architecture:** File-per-category JSON pool under `data/categories/` is the source of truth. A single argparse CLI (`python -m bwtools`) exposes pipeline stages: `generate` (Claude API, theme-seeded, dedup context) → `validate` → `review export/import` (CSV, all-or-nothing) → `localize` (approved only) → `compile` (pluggable format adapters) → `stats`. Categories form a graph: an item is either a localized word or a `ref` to another category.

**Tech Stack:** Python ≥3.11, stdlib (`json`, `csv`, `argparse`, `dataclasses`), `anthropic` SDK (only in `llm.py`), `pytest`.

**Spec:** `docs/superpowers/specs/2026-07-14-category-generator-design.md`

## Global Constraints

- Python `>=3.11`; only external runtime dependency is `anthropic>=0.40`.
- Item count per category: between `item_min` (4) and `item_max` (5) from `config/settings.json`.
- LLM model: `claude-sonnet-5` (from `config/settings.json`, key `model`). API key from `ANTHROPIC_API_KEY` env var.
- `en` is the canonical locale; required in `names` and in every `word` item.
- Category ids and refs: kebab-case (`[a-z0-9]+(-[a-z0-9]+)*`), unique, filename must equal inner id.
- Statuses: `draft`, `approved`, `rejected`. Rejected files are never deleted.
- Invalid LLM output is rejected and reported — never auto-repaired.
- `review import` is all-or-nothing: any invalid row aborts with zero changes applied.
- All category file writes are atomic (temp file + `os.replace`).
- `reports/` and `output/` are gitignored; `data/categories/` is committed.
- No code comments (project convention).

---

### Task 1: Project scaffolding + data model (`models.py`)

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `config/settings.json`
- Create: `config/themes.json`
- Create: `data/categories/.gitkeep`
- Create: `bwtools/__init__.py` (empty)
- Create: `bwtools/models.py`
- Create: `tests/test_models.py`

**Interfaces:**
- Produces: `Item(word: dict | None, ref: str | None)` with `Item.from_dict(data) -> Item`, `item.to_dict() -> dict`.
- Produces: `Category(id, theme, difficulty, status, items, names, image=None)` with `Category.from_dict(data) -> Category`, `category.to_dict() -> dict`, `category.words_for(locale) -> list[str]`, `category.refs() -> list[str]`.
- Produces: `SchemaError(ValueError)`, `VALID_STATUSES = ("draft", "approved", "rejected")`, `ID_PATTERN` (compiled kebab-case regex).
- All invalid shapes raise `SchemaError` with a human-readable message.

- [ ] **Step 1: Create scaffolding files**

`pyproject.toml`:

```toml
[project]
name = "bwtools"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["anthropic>=0.40"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
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

`config/settings.json`:

```json
{
  "model": "claude-sonnet-5",
  "item_min": 4,
  "item_max": 5,
  "locales": ["en", "tr"],
  "max_llm_retries": 3
}
```

`config/themes.json`:

```json
{
  "themes": [
    { "id": "animals", "hint": "animal kingdom: birds, pets, sea creatures, insects, habitats" },
    { "id": "food-drink", "hint": "food, dishes, ingredients, drinks, desserts, cuisines" },
    { "id": "nature", "hint": "plants, flowers, weather, geography, seasons, landscapes" },
    { "id": "home", "hint": "furniture, rooms, kitchen tools, household objects" },
    { "id": "sports", "hint": "sports, equipment, positions, games" },
    { "id": "travel", "hint": "transport, countries, landmarks, vacation items" },
    { "id": "arts-entertainment", "hint": "music, cinema, books, instruments, art supplies" },
    { "id": "science-tech", "hint": "space, gadgets, computers, inventions, units" },
    { "id": "clothing", "hint": "clothes, accessories, footwear, fabrics" },
    { "id": "professions", "hint": "jobs, workplaces, tools of trades" }
  ]
}
```

`data/categories/.gitkeep`: empty file. `bwtools/__init__.py`: empty file.

- [ ] **Step 2: Write the failing tests**

`tests/test_models.py`:

```python
import pytest

from bwtools.models import Category, Item, SchemaError


def valid_category_dict():
    return {
        "id": "birds",
        "theme": "animals",
        "difficulty": 1,
        "image": None,
        "status": "draft",
        "items": [
            {"word": {"en": "Pigeon", "tr": "Güvercin"}},
            {"word": {"en": "Crow"}},
            {"word": {"en": "Eagle"}},
            {"ref": "owls"},
        ],
        "names": {"en": "Birds", "tr": "Kuşlar"},
    }


def test_category_roundtrip():
    data = valid_category_dict()
    category = Category.from_dict(data)
    assert category.id == "birds"
    assert category.to_dict() == data


def test_words_for_and_refs():
    category = Category.from_dict(valid_category_dict())
    assert category.words_for("en") == ["Pigeon", "Crow", "Eagle"]
    assert category.words_for("tr") == ["Güvercin"]
    assert category.refs() == ["owls"]


def test_item_requires_exactly_one_of_word_or_ref():
    with pytest.raises(SchemaError):
        Item.from_dict({"word": {"en": "Pigeon"}, "ref": "owls"})
    with pytest.raises(SchemaError):
        Item.from_dict({})


def test_empty_word_text_rejected():
    with pytest.raises(SchemaError):
        Item.from_dict({"word": {"en": "  "}})


@pytest.mark.parametrize("field,value", [
    ("id", "Birds"),
    ("id", "birds_x"),
    ("difficulty", 0),
    ("difficulty", 4),
    ("difficulty", "1"),
    ("status", "pending"),
    ("names", {"tr": "Kuşlar"}),
    ("names", {"en": ""}),
    ("items", []),
])
def test_invalid_category_fields_rejected(field, value):
    data = valid_category_dict()
    data[field] = value
    with pytest.raises(SchemaError):
        Category.from_dict(data)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd ~/Desktop/Projects/bubble-word-tools && python3 -m pytest tests/test_models.py -v`
Expected: FAIL / errors with `ModuleNotFoundError: No module named 'bwtools.models'`

- [ ] **Step 4: Write the implementation**

`bwtools/models.py`:

```python
import re
from dataclasses import dataclass, field

VALID_STATUSES = ("draft", "approved", "rejected")
ID_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


class SchemaError(ValueError):
    pass


@dataclass
class Item:
    word: dict | None = None
    ref: str | None = None

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise SchemaError(f"item must be an object, got {type(data).__name__}")
        if ("word" in data) == ("ref" in data):
            raise SchemaError("item must have exactly one of 'word' or 'ref'")
        if "word" in data:
            word = data["word"]
            if not isinstance(word, dict) or not word:
                raise SchemaError("'word' must be a non-empty object of locale to text")
            for locale, text in word.items():
                if not isinstance(text, str) or not text.strip():
                    raise SchemaError(f"word text for locale '{locale}' is empty")
            return cls(word=word)
        ref = data["ref"]
        if not isinstance(ref, str) or not ID_PATTERN.fullmatch(ref):
            raise SchemaError(f"'ref' must be a kebab-case id, got {ref!r}")
        return cls(ref=ref)

    def to_dict(self):
        if self.word is not None:
            return {"word": self.word}
        return {"ref": self.ref}


@dataclass
class Category:
    id: str
    theme: str
    difficulty: int
    status: str
    items: list = field(default_factory=list)
    names: dict = field(default_factory=dict)
    image: str | None = None

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise SchemaError("category must be an object")
        cid = data.get("id")
        if not isinstance(cid, str) or not ID_PATTERN.fullmatch(cid):
            raise SchemaError(f"'id' must be a kebab-case string, got {cid!r}")
        theme = data.get("theme")
        if not isinstance(theme, str) or not theme.strip():
            raise SchemaError(f"{cid}: 'theme' must be a non-empty string")
        difficulty = data.get("difficulty")
        if not isinstance(difficulty, int) or isinstance(difficulty, bool) or not 1 <= difficulty <= 3:
            raise SchemaError(f"{cid}: 'difficulty' must be an integer 1-3, got {difficulty!r}")
        status = data.get("status")
        if status not in VALID_STATUSES:
            raise SchemaError(f"{cid}: 'status' must be one of {VALID_STATUSES}, got {status!r}")
        image = data.get("image")
        if image is not None and (not isinstance(image, str) or not image.strip()):
            raise SchemaError(f"{cid}: 'image' must be null or a non-empty string")
        raw_items = data.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            raise SchemaError(f"{cid}: 'items' must be a non-empty list")
        items = [Item.from_dict(entry) for entry in raw_items]
        names = data.get("names")
        if not isinstance(names, dict) or not isinstance(names.get("en"), str) or not names["en"].strip():
            raise SchemaError(f"{cid}: 'names' must contain a non-empty 'en' name")
        for locale, name in names.items():
            if not isinstance(name, str) or not name.strip():
                raise SchemaError(f"{cid}: name for locale '{locale}' is empty")
        return cls(id=cid, theme=theme, difficulty=difficulty, status=status,
                   items=items, names=names, image=image)

    def to_dict(self):
        return {
            "id": self.id,
            "theme": self.theme,
            "difficulty": self.difficulty,
            "image": self.image,
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "names": self.names,
        }

    def words_for(self, locale):
        return [item.word[locale] for item in self.items if item.word and locale in item.word]

    def refs(self):
        return [item.ref for item in self.items if item.ref]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_models.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore config/ data/ bwtools/ tests/
git commit -m "feat: project scaffolding and category data model"
```

---

### Task 2: Category store (`store.py`)

**Files:**
- Create: `bwtools/store.py`
- Create: `tests/conftest.py`
- Create: `tests/test_store.py`

**Interfaces:**
- Consumes: `Category`, `SchemaError` from `bwtools.models`.
- Produces: `CategoryStore(root: Path)` with `.load_all() -> dict[str, Category]` (sorted by filename, raises `SchemaError` on invalid file or filename/id mismatch), `.save(category: Category) -> Path` (atomic write, creates dirs), `.by_status(status: str) -> list[Category]`.
- Produces (test helper): `make_category(cid="birds", theme="animals", status="draft", words=(...), refs=(), difficulty=1, names=None) -> Category` in `tests/conftest.py`.

- [ ] **Step 1: Write the test helper and failing tests**

`tests/conftest.py`:

```python
from bwtools.models import Category, Item


def make_category(cid="birds", theme="animals", status="draft",
                  words=("Pigeon", "Crow", "Eagle", "Owl"), refs=(),
                  difficulty=1, names=None):
    items = [Item(word={"en": word}) for word in words]
    items += [Item(ref=ref) for ref in refs]
    return Category(id=cid, theme=theme, difficulty=difficulty, status=status,
                    items=items, names=names or {"en": cid.replace("-", " ").title()})
```

`tests/test_store.py`:

```python
import json

import pytest

from bwtools.models import SchemaError
from bwtools.store import CategoryStore
from tests.conftest import make_category


def test_save_and_load_roundtrip(tmp_path):
    store = CategoryStore(tmp_path / "categories")
    category = make_category()
    path = store.save(category)
    assert path.name == "birds.json"
    pool = store.load_all()
    assert list(pool) == ["birds"]
    assert pool["birds"].to_dict() == category.to_dict()


def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category())
    assert [p.name for p in tmp_path.iterdir()] == ["birds.json"]


def test_load_rejects_filename_id_mismatch(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds"))
    (tmp_path / "birds.json").rename(tmp_path / "crows.json")
    with pytest.raises(SchemaError, match="does not match filename"):
        store.load_all()


def test_load_rejects_invalid_json_shape(tmp_path):
    store = CategoryStore(tmp_path)
    (tmp_path / "bad.json").write_text(json.dumps({"id": "bad"}), encoding="utf-8")
    with pytest.raises(SchemaError):
        store.load_all()


def test_by_status_filters(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", status="approved"))
    store.save(make_category(cid="crows", status="draft"))
    assert [c.id for c in store.by_status("approved")] == ["birds"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bwtools.store'`

- [ ] **Step 3: Write the implementation**

`bwtools/store.py`:

```python
import json
import os
from pathlib import Path

from .models import Category, SchemaError


class CategoryStore:
    def __init__(self, root):
        self.root = Path(root)

    def load_all(self):
        pool = {}
        for path in sorted(self.root.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise SchemaError(f"{path.name}: invalid JSON: {error}")
            category = Category.from_dict(data)
            if category.id != path.stem:
                raise SchemaError(
                    f"{path.name}: inner id '{category.id}' does not match filename")
            pool[category.id] = category
        return pool

    def save(self, category):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{category.id}.json"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(category.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        os.replace(tmp, path)
        return path

    def by_status(self, status):
        return [c for c in self.load_all().values() if c.status == status]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add bwtools/store.py tests/conftest.py tests/test_store.py
git commit -m "feat: category store with atomic file IO"
```

---

### Task 3: Validation engine + `validate` command + CLI entry

**Files:**
- Create: `bwtools/commands/__init__.py` (empty)
- Create: `bwtools/commands/validate.py`
- Create: `bwtools/__main__.py`
- Create: `tests/test_validate.py`

**Interfaces:**
- Consumes: `CategoryStore`, `Category`, `SchemaError`, `make_category`.
- Produces: `Issue(severity: str, category_id: str, message: str)` dataclass; `validate_pool(pool: dict[str, Category], settings: dict) -> list[Issue]`; `write_report(issues: list[Issue], path: Path) -> None`; `run(store, settings, report_path) -> int` (0 = clean or warnings only, 1 = errors or unreadable pool).
- Produces: `bwtools/__main__.py` with `main(argv=None) -> int`, global options `--data-dir` (default `data/categories`), `--config-dir` (default `config`), `--reports-dir` (default `reports`), `--output-dir` (default `output`); subcommand `validate`. Later tasks extend `build_parser()` and the dispatch in `main()`.

- [ ] **Step 1: Write the failing tests**

`tests/test_validate.py`:

```python
from bwtools.commands.validate import Issue, validate_pool, write_report
from tests.conftest import make_category

SETTINGS = {"item_min": 4, "item_max": 5}


def as_pool(*categories):
    return {c.id: c for c in categories}


def errors(issues):
    return [i for i in issues if i.severity == "error"]


def test_clean_pool_has_no_errors():
    pool = as_pool(make_category())
    assert errors(validate_pool(pool, SETTINGS)) == []


def test_item_count_out_of_range():
    pool = as_pool(make_category(words=("A", "B", "C")))
    assert any("expected 4-5" in i.message for i in errors(validate_pool(pool, SETTINGS)))


def test_missing_ref_target():
    pool = as_pool(make_category(words=("A", "B", "C"), refs=("ghost",)))
    assert any("'ghost' does not exist" in i.message
               for i in errors(validate_pool(pool, SETTINGS)))


def test_cycle_detected():
    a = make_category(cid="animals", words=("A", "B", "C"), refs=("birds",))
    b = make_category(cid="birds", words=("D", "E", "F"), refs=("animals",))
    issues = errors(validate_pool(as_pool(a, b), SETTINGS))
    assert any("cycle" in i.message for i in issues)


def test_intra_category_duplicate_word_is_error():
    pool = as_pool(make_category(words=("Pigeon", "pigeon", "Crow", "Owl")))
    assert any("duplicate word" in i.message for i in errors(validate_pool(pool, SETTINGS)))


def test_cross_category_reuse_is_warning_only():
    a = make_category(cid="birds", words=("Pigeon", "Crow", "Eagle", "Owl"))
    b = make_category(cid="pets", words=("Pigeon", "Dog", "Cat", "Hamster"))
    issues = validate_pool(as_pool(a, b), SETTINGS)
    assert errors(issues) == []
    assert any(i.severity == "warning" and "pigeon" in i.message.lower() for i in issues)


def test_write_report(tmp_path):
    report = tmp_path / "validation.md"
    write_report([Issue("error", "birds", "boom"), Issue("warning", "pets", "meh")], report)
    text = report.read_text(encoding="utf-8")
    assert "## Errors (1)" in text
    assert "- [birds] boom" in text
    assert "## Warnings (1)" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_validate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bwtools.commands'`

- [ ] **Step 3: Write the implementation**

`bwtools/commands/validate.py`:

```python
from collections import defaultdict
from dataclasses import dataclass

from ..models import SchemaError


@dataclass
class Issue:
    severity: str
    category_id: str
    message: str


def validate_pool(pool, settings):
    issues = []
    item_min, item_max = settings["item_min"], settings["item_max"]
    for category in pool.values():
        count = len(category.items)
        if not item_min <= count <= item_max:
            issues.append(Issue("error", category.id,
                                f"has {count} items, expected {item_min}-{item_max}"))
        for ref in category.refs():
            if ref not in pool:
                issues.append(Issue("error", category.id, f"ref '{ref}' does not exist"))
        lowered = [w.strip().lower() for w in category.words_for("en")]
        for word in sorted({w for w in lowered if lowered.count(w) > 1}):
            issues.append(Issue("error", category.id, f"duplicate word '{word}'"))
    issues.extend(_find_cycles(pool))
    issues.extend(_cross_category_reuse(pool))
    return issues


def _find_cycles(pool):
    issues = []
    state = dict.fromkeys(pool, 0)

    def visit(cid, path):
        state[cid] = 1
        for ref in pool[cid].refs():
            if ref not in pool:
                continue
            if state[ref] == 1:
                issues.append(Issue("error", cid,
                                    "cycle: " + " -> ".join(path + [ref])))
            elif state[ref] == 0:
                visit(ref, path + [ref])
        state[cid] = 2

    for cid in pool:
        if state[cid] == 0:
            visit(cid, [cid])
    return issues


def _cross_category_reuse(pool):
    placements = defaultdict(set)
    for category in pool.values():
        for word in category.words_for("en"):
            placements[word.strip().lower()].add(category.id)
    return [Issue("warning", ", ".join(sorted(cids)),
                  f"word '{word}' reused across categories")
            for word, cids in sorted(placements.items()) if len(cids) > 1]


def write_report(issues, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    lines = ["# Validation Report", ""]
    lines.append(f"## Errors ({len(errors)})")
    lines += [f"- [{i.category_id}] {i.message}" for i in errors] or ["- none"]
    lines.append("")
    lines.append(f"## Warnings ({len(warnings)})")
    lines += [f"- [{i.category_id}] {i.message}" for i in warnings] or ["- none"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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

`bwtools/__main__.py`:

```python
import argparse
import json
import sys
from pathlib import Path

from .store import CategoryStore
from .commands import validate as validate_cmd


def load_settings(config_dir):
    return json.loads((Path(config_dir) / "settings.json").read_text(encoding="utf-8"))


def build_parser():
    parser = argparse.ArgumentParser(prog="bwtools")
    parser.add_argument("--data-dir", default="data/categories")
    parser.add_argument("--config-dir", default="config")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--output-dir", default="output")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config_dir)
    store = CategoryStore(Path(args.data_dir))
    reports_dir = Path(args.reports_dir)
    if args.command == "validate":
        return validate_cmd.run(store, settings, reports_dir / "validation.md")
    return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_validate.py -v`
Expected: all PASS

- [ ] **Step 5: Smoke-test the CLI on the empty pool**

Run: `python3 -m bwtools validate`
Expected output: `0 categories, 0 errors, 0 warnings` and `report: reports/validation.md`; exit code 0.

- [ ] **Step 6: Commit**

```bash
git add bwtools/commands/ bwtools/__main__.py tests/test_validate.py
git commit -m "feat: validation engine, validate command, CLI entry point"
```

---

### Task 4: LLM client (`llm.py`)

**Files:**
- Create: `bwtools/llm.py`
- Create: `tests/test_llm.py`
- Modify: `tests/conftest.py` (append `FakeLlm`)

**Interfaces:**
- Produces: `LlmError(Exception)`; `LlmClient(model: str, max_retries: int = 3, client=None, backoff: float = 1.0)` with `.complete_json(system: str, user: str) -> object` (parsed JSON; strips markdown code fences; retries on API errors and invalid JSON with exponential backoff; raises `LlmError` after exhausting retries).
- Produces (test helper): `FakeLlm(responses)` in `tests/conftest.py` — `.complete_json(system, user)` records `(system, user)` in `.calls` and pops the next canned response, raising it if it is an exception. Used by Tasks 5, 6, 8.
- Only this module imports `anthropic`.

- [ ] **Step 1: Append `FakeLlm` to `tests/conftest.py`**

```python
class FakeLlm:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete_json(self, system, user):
        self.calls.append((system, user))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
```

- [ ] **Step 2: Write the failing tests**

`tests/test_llm.py`:

```python
from types import SimpleNamespace

import pytest

from bwtools.llm import LlmClient, LlmError


class FakeAnthropic:
    def __init__(self, texts):
        self.texts = list(texts)
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        text = self.texts.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


def make_client(texts):
    fake = FakeAnthropic(texts)
    return LlmClient("test-model", max_retries=3, client=fake, backoff=0), fake


def test_parses_json_response():
    client, _ = make_client(['[{"id": "birds"}]'])
    assert client.complete_json("sys", "user") == [{"id": "birds"}]


def test_strips_code_fences():
    client, _ = make_client(['```json\n{"name": "Birds"}\n```'])
    assert client.complete_json("sys", "user") == {"name": "Birds"}


def test_retries_on_invalid_json_then_succeeds():
    client, fake = make_client(["not json at all", '{"ok": true}'])
    assert client.complete_json("sys", "user") == {"ok": True}
    assert fake.calls == 2


def test_raises_llm_error_after_max_retries():
    client, fake = make_client(["bad", "bad", "bad"])
    with pytest.raises(LlmError, match="failed after 3 attempts"):
        client.complete_json("sys", "user")
    assert fake.calls == 3
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bwtools.llm'`

- [ ] **Step 4: Write the implementation**

`bwtools/llm.py`:

```python
import json
import time

import anthropic


class LlmError(Exception):
    pass


class LlmClient:
    def __init__(self, model, max_retries=3, client=None, backoff=1.0):
        self.model = model
        self.max_retries = max_retries
        self.backoff = backoff
        self._client = client or anthropic.Anthropic()

    def complete_json(self, system, user):
        last_error = None
        for attempt in range(self.max_retries):
            if attempt:
                time.sleep(self.backoff * (2 ** (attempt - 1)))
            try:
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=8192,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return self._parse(response.content[0].text)
            except (anthropic.APIError, LlmError) as error:
                last_error = error
        raise LlmError(f"LLM call failed after {self.max_retries} attempts: {last_error}")

    @staticmethod
    def _parse(text):
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0]
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise LlmError(f"response is not valid JSON: {error}")
```

Note: `anthropic` must be installed for the import to succeed. If `python3 -m pytest` fails on the import, install dev deps first: `python3 -m pip install -e ".[dev]"`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_llm.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add bwtools/llm.py tests/test_llm.py tests/conftest.py
git commit -m "feat: Claude API client with retry and JSON parsing"
```

---

### Task 5: `generate` command

**Files:**
- Create: `bwtools/commands/generate.py`
- Create: `tests/test_generate.py`
- Modify: `bwtools/__main__.py` (add subcommand + dispatch)

**Interfaces:**
- Consumes: `CategoryStore`, `Category`, `SchemaError`, `LlmClient`-compatible object (only `.complete_json`), `FakeLlm`, `make_category`.
- Produces: `generation_system(item_min: int, item_max: int) -> str`; `build_user_prompt(theme: dict, count: int, existing_names: list[str], existing_words: list[str], all_ids: list[str]) -> str`; `run_generate(theme_id: str, count: int, store, llm, settings, themes: list[dict]) -> dict` returning `{"accepted": [ids], "rejected": [(label, reason)]}` — raises `ValueError` on unknown theme. Accepted categories are saved as `draft` immediately, one file per category.
- Produces: CLI `generate --theme <id> --count N` (theme `all` iterates every theme in `config/themes.json`); rejections appended to `reports/generate.md`.

- [ ] **Step 1: Write the failing tests**

`tests/test_generate.py`:

```python
import pytest

from bwtools.commands.generate import build_user_prompt, run_generate
from bwtools.store import CategoryStore
from tests.conftest import FakeLlm, make_category

SETTINGS = {"item_min": 4, "item_max": 5}
THEMES = [{"id": "animals", "hint": "animal kingdom"}]


def candidate(cid="birds", name="Birds", words=("Pigeon", "Crow", "Eagle", "Owl"), difficulty=1):
    return {"id": cid, "name": name, "difficulty": difficulty, "words": list(words)}


def test_accepted_candidates_saved_as_draft(tmp_path):
    store = CategoryStore(tmp_path)
    llm = FakeLlm([[candidate("birds"), candidate("cats", "Cats", ("Siamese", "Persian", "Tabby", "Sphynx"))]])
    result = run_generate("animals", 2, store, llm, SETTINGS, THEMES)
    assert result["accepted"] == ["birds", "cats"]
    assert result["rejected"] == []
    pool = store.load_all()
    assert pool["birds"].status == "draft"
    assert pool["birds"].theme == "animals"
    assert pool["birds"].words_for("en") == ["Pigeon", "Crow", "Eagle", "Owl"]
    assert pool["birds"].names == {"en": "Birds"}


def test_invalid_candidates_rejected_not_saved(tmp_path):
    store = CategoryStore(tmp_path)
    llm = FakeLlm([[
        candidate("too-few", words=("A", "B")),
        candidate("dup-words", words=("Pigeon", "pigeon", "Crow", "Owl")),
        candidate("Bad_Id"),
        candidate("no-name", name=""),
        "not even an object",
    ]])
    result = run_generate("animals", 5, store, llm, SETTINGS, THEMES)
    assert result["accepted"] == []
    assert len(result["rejected"]) == 5
    assert store.load_all() == {}


def test_existing_id_rejected_and_dedup_context_in_prompt(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", theme="animals"))
    llm = FakeLlm([[candidate("birds")]])
    result = run_generate("animals", 1, store, llm, SETTINGS, THEMES)
    assert result["accepted"] == []
    assert "duplicate id" in result["rejected"][0][1]
    _, user_prompt = llm.calls[0]
    assert "Birds" in user_prompt
    assert "pigeon" in user_prompt


def test_unknown_theme_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown theme"):
        run_generate("ghosts", 1, CategoryStore(tmp_path), FakeLlm([]), SETTINGS, THEMES)


def test_prompt_mentions_count_and_hint():
    prompt = build_user_prompt(THEMES[0], 7, [], [], [])
    assert "exactly 7" in prompt
    assert "animal kingdom" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_generate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bwtools.commands.generate'`

- [ ] **Step 3: Write the implementation**

`bwtools/commands/generate.py`:

```python
from ..models import Category, SchemaError


def generation_system(item_min, item_max):
    return (
        "You generate word-association categories for a mobile word game.\n"
        "Return ONLY a JSON array. Each element:\n"
        '{"id": "<kebab-case-id>", "name": "<Category Name>", "difficulty": 1, '
        '"words": ["..."]}\n'
        f"Each category must have between {item_min} and {item_max} words.\n"
        "Words must be common English words or short phrases strongly associated "
        "with the category name.\n"
        "STRONGLY prefer easy, internationally understandable words: cross-language "
        "cognates and proper nouns (Uranus, Jupiter, Pizza, Taxi) that stay "
        "recognizable in most languages. Avoid obscure or highly language-specific "
        "vocabulary.\n"
        "Difficulty: 1 = internationally transparent everyday words, "
        "2 = common but language-dependent, 3 = niche."
    )


def build_user_prompt(theme, count, existing_names, existing_words, all_ids):
    lines = [
        f"Theme: {theme['id']} - {theme['hint']}",
        f"Generate exactly {count} new categories.",
    ]
    if all_ids:
        lines.append("Already used ids (do not reuse): " + ", ".join(sorted(all_ids)))
    if existing_names:
        lines.append("Existing category names in this theme (do not duplicate): "
                     + ", ".join(existing_names))
    if existing_words:
        lines.append("Words already used in this theme (avoid): "
                     + ", ".join(existing_words))
    return "\n".join(lines)


def run_generate(theme_id, count, store, llm, settings, themes):
    theme = next((t for t in themes if t["id"] == theme_id), None)
    if theme is None:
        raise ValueError(f"unknown theme '{theme_id}'")
    pool = store.load_all()
    theme_categories = [c for c in pool.values() if c.theme == theme_id]
    existing_names = sorted(c.names["en"] for c in theme_categories)
    existing_words = sorted({w.strip().lower()
                             for c in theme_categories for w in c.words_for("en")})
    raw = llm.complete_json(
        generation_system(settings["item_min"], settings["item_max"]),
        build_user_prompt(theme, count, existing_names, existing_words, list(pool)))
    accepted, rejected = [], []
    for entry in raw if isinstance(raw, list) else []:
        category, reason = _to_category(entry, theme_id, pool, settings)
        if category is None:
            rejected.append((str(entry)[:80], reason))
            continue
        store.save(category)
        pool[category.id] = category
        accepted.append(category.id)
    return {"accepted": accepted, "rejected": rejected}


def _to_category(entry, theme_id, pool, settings):
    if not isinstance(entry, dict):
        return None, "not an object"
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
    cid = entry.get("id")
    if isinstance(cid, str) and cid in pool:
        return None, f"duplicate id '{cid}'"
    try:
        category = Category.from_dict({
            "id": cid,
            "theme": theme_id,
            "difficulty": entry.get("difficulty"),
            "image": None,
            "status": "draft",
            "items": [{"word": {"en": w.strip()}} for w in words],
            "names": {"en": entry.get("name", "")},
        })
    except SchemaError as error:
        return None, str(error)
    return category, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_generate.py -v`
Expected: all PASS

- [ ] **Step 5: Wire into the CLI**

In `bwtools/__main__.py`, inside `build_parser()` after `sub.add_parser("validate")`, add:

```python
    generate = sub.add_parser("generate")
    generate.add_argument("--theme", required=True)
    generate.add_argument("--count", type=int, default=20)
```

In `main()`, after the `validate` branch, add:

```python
    if args.command == "generate":
        from .llm import LlmClient
        from .commands import generate as generate_cmd
        themes = json.loads(
            (Path(args.config_dir) / "themes.json").read_text(encoding="utf-8"))["themes"]
        llm = LlmClient(settings["model"], settings.get("max_llm_retries", 3))
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
```

- [ ] **Step 6: Run the full test suite**

Run: `python3 -m pytest -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add bwtools/commands/generate.py bwtools/__main__.py tests/test_generate.py
git commit -m "feat: theme-seeded generate command with dedup context"
```

---

### Task 6: `generate --parents` (hierarchy mode)

**Files:**
- Modify: `bwtools/commands/generate.py` (append parents mode)
- Modify: `bwtools/__main__.py` (add `--parents` flag)
- Create: `tests/test_generate_parents.py`

**Interfaces:**
- Consumes: everything from Task 5.
- Produces: `parents_system(item_min: int, item_max: int) -> str`; `run_generate_parents(count: int, store, llm, settings) -> dict` returning `{"accepted": [ids], "rejected": [(label, reason)]}`. Parent categories get `items` of `{"ref": child_id}`, theme = most common child theme, status `draft`.
- Produces: CLI `generate --parents --count N` (ignores `--theme`).

- [ ] **Step 1: Write the failing tests**

`tests/test_generate_parents.py`:

```python
from bwtools.commands.generate import run_generate_parents
from bwtools.store import CategoryStore
from tests.conftest import FakeLlm, make_category

SETTINGS = {"item_min": 4, "item_max": 5}


def seeded_store(tmp_path):
    store = CategoryStore(tmp_path)
    for cid in ("birds", "cats", "dogs", "fish"):
        store.save(make_category(cid=cid, theme="animals",
                                 words=(f"{cid}-a", f"{cid}-b", f"{cid}-c", f"{cid}-d")))
    return store


def parent(cid="animals", children=("birds", "cats", "dogs", "fish")):
    return {"id": cid, "name": "Animals", "difficulty": 2, "children": list(children)}


def test_parent_saved_with_ref_items(tmp_path):
    store = seeded_store(tmp_path)
    llm = FakeLlm([[parent()]])
    result = run_generate_parents(1, store, llm, SETTINGS)
    assert result["accepted"] == ["animals"]
    saved = store.load_all()["animals"]
    assert saved.refs() == ["birds", "cats", "dogs", "fish"]
    assert saved.status == "draft"
    assert saved.theme == "animals"


def test_unknown_child_rejected(tmp_path):
    store = seeded_store(tmp_path)
    llm = FakeLlm([[parent(children=("birds", "cats", "dogs", "ghost"))]])
    result = run_generate_parents(1, store, llm, SETTINGS)
    assert result["accepted"] == []
    assert "unknown child" in result["rejected"][0][1]


def test_duplicate_children_rejected(tmp_path):
    store = seeded_store(tmp_path)
    llm = FakeLlm([[parent(children=("birds", "birds", "cats", "dogs"))]])
    result = run_generate_parents(1, store, llm, SETTINGS)
    assert result["accepted"] == []
    assert "duplicate children" in result["rejected"][0][1]


def test_existing_ids_listed_in_prompt(tmp_path):
    store = seeded_store(tmp_path)
    llm = FakeLlm([[]])
    run_generate_parents(1, store, llm, SETTINGS)
    _, user_prompt = llm.calls[0]
    for cid in ("birds", "cats", "dogs", "fish"):
        assert cid in user_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_generate_parents.py -v`
Expected: FAIL with `ImportError: cannot import name 'run_generate_parents'`

- [ ] **Step 3: Append the implementation to `bwtools/commands/generate.py`**

```python
from collections import Counter


def parents_system(item_min, item_max):
    return (
        "You design parent categories for a word game where completed categories "
        "merge into higher-level categories.\n"
        "Return ONLY a JSON array. Each element:\n"
        '{"id": "<kebab-case-id>", "name": "<Parent Name>", "difficulty": 2, '
        '"children": ["<existing-category-id>"]}\n'
        f"Each parent must have between {item_min} and {item_max} children, chosen "
        "ONLY from the provided list of existing category ids.\n"
        "Children must genuinely belong to the parent concept "
        "(e.g. birds, cats, dogs -> animals)."
    )


def run_generate_parents(count, store, llm, settings):
    pool = store.load_all()
    listing = "\n".join(
        f"- {c.id}: {c.names['en']} (theme: {c.theme})"
        for c in sorted(pool.values(), key=lambda c: c.id))
    user = (f"Propose exactly {count} new parent categories.\n"
            f"Existing categories:\n{listing}")
    raw = llm.complete_json(
        parents_system(settings["item_min"], settings["item_max"]), user)
    accepted, rejected = [], []
    for entry in raw if isinstance(raw, list) else []:
        category, reason = _to_parent(entry, pool, settings)
        if category is None:
            rejected.append((str(entry)[:80], reason))
            continue
        store.save(category)
        pool[category.id] = category
        accepted.append(category.id)
    return {"accepted": accepted, "rejected": rejected}


def _to_parent(entry, pool, settings):
    if not isinstance(entry, dict):
        return None, "not an object"
    children = entry.get("children")
    if not isinstance(children, list) or not all(
            isinstance(c, str) for c in children):
        return None, "children must be a list of ids"
    if not settings["item_min"] <= len(children) <= settings["item_max"]:
        return None, (f"{len(children)} children, expected "
                      f"{settings['item_min']}-{settings['item_max']}")
    if len(set(children)) != len(children):
        return None, "duplicate children"
    unknown = [c for c in children if c not in pool]
    if unknown:
        return None, f"unknown child ids: {', '.join(unknown)}"
    cid = entry.get("id")
    if isinstance(cid, str) and cid in pool:
        return None, f"duplicate id '{cid}'"
    theme = Counter(pool[c].theme for c in children).most_common(1)[0][0]
    try:
        category = Category.from_dict({
            "id": cid,
            "theme": theme,
            "difficulty": entry.get("difficulty"),
            "image": None,
            "status": "draft",
            "items": [{"ref": c} for c in children],
            "names": {"en": entry.get("name", "")},
        })
    except SchemaError as error:
        return None, str(error)
    return category, None
```

Place the `from collections import Counter` import at the top of the file with the other imports.

- [ ] **Step 4: Wire the flag into the CLI**

In `build_parser()`, on the existing `generate` subparser, change `--theme` to optional and add the flag:

```python
    generate = sub.add_parser("generate")
    generate.add_argument("--theme")
    generate.add_argument("--count", type=int, default=20)
    generate.add_argument("--parents", action="store_true")
```

In the `generate` branch of `main()`, before the theme loop, add:

```python
        if args.parents:
            result = generate_cmd.run_generate_parents(args.count, store, llm, settings)
            print(f"parents: {len(result['accepted'])} accepted, "
                  f"{len(result['rejected'])} rejected")
            return validate_cmd.run(store, settings, reports_dir / "validation.md")
        if not args.theme:
            print("ERROR --theme is required unless --parents is set")
            return 2
```

- [ ] **Step 5: Run the full test suite**

Run: `python3 -m pytest -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add bwtools/commands/generate.py bwtools/__main__.py tests/test_generate_parents.py
git commit -m "feat: parent category generation mode"
```

---

### Task 7: `review export` / `review import`

**Files:**
- Create: `bwtools/commands/review.py`
- Create: `tests/test_review.py`
- Modify: `bwtools/__main__.py`

**Interfaces:**
- Consumes: `CategoryStore`, `Item`, `make_category`.
- Produces: `export_drafts(store, csv_path: Path) -> int` (row count; CSV columns `id,theme,name,difficulty,words,decision`; words pipe-joined, ref items serialized as `ref:<id>`); `import_decisions(store, csv_path: Path, settings: dict) -> dict` returning `{"approved": n, "rejected": n, "skipped": n}`; `ReviewImportError(ValueError)` listing every bad row with its line number — raised before any file is written (all-or-nothing).
- Import semantics: decision `approve` → status `approved` (edited words/difficulty written back), `reject` → status `rejected`, empty → skipped (stays draft). Editing words replaces the category's items (en-only word dicts; `ref:` tokens become ref items and must exist in the pool).
- Produces: CLI `review export` (writes `reports/review.csv`) and `review import <csv-path>`.

- [ ] **Step 1: Write the failing tests**

`tests/test_review.py`:

```python
import csv

import pytest

from bwtools.commands.review import ReviewImportError, export_drafts, import_decisions
from bwtools.store import CategoryStore
from tests.conftest import make_category

SETTINGS = {"item_min": 4, "item_max": 5}


def read_rows(csv_path):
    with open(csv_path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(csv_path, rows):
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["id", "theme", "name", "difficulty", "words", "decision"])
        writer.writeheader()
        writer.writerows(rows)


def seeded(tmp_path):
    store = CategoryStore(tmp_path / "categories")
    store.save(make_category(cid="birds", status="draft"))
    store.save(make_category(cid="cats", status="draft",
                             words=("Siamese", "Persian", "Tabby", "Sphynx")))
    store.save(make_category(cid="done", status="approved"))
    return store


def test_export_writes_only_drafts(tmp_path):
    store = seeded(tmp_path)
    csv_path = tmp_path / "review.csv"
    assert export_drafts(store, csv_path) == 2
    rows = read_rows(csv_path)
    assert [r["id"] for r in rows] == ["birds", "cats"]
    assert rows[0]["words"] == "Pigeon|Crow|Eagle|Owl"
    assert rows[0]["decision"] == ""


def test_export_serializes_refs(tmp_path):
    store = CategoryStore(tmp_path / "categories")
    store.save(make_category(cid="birds"))
    store.save(make_category(cid="animals", words=("Horse", "Snake", "Frog"),
                             refs=("birds",)))
    csv_path = tmp_path / "review.csv"
    export_drafts(store, csv_path)
    rows = {r["id"]: r for r in read_rows(csv_path)}
    assert rows["animals"]["words"] == "Horse|Snake|Frog|ref:birds"


def test_import_applies_decisions_and_edits(tmp_path):
    store = seeded(tmp_path)
    csv_path = tmp_path / "review.csv"
    export_drafts(store, csv_path)
    rows = read_rows(csv_path)
    rows[0]["decision"] = "approve"
    rows[0]["words"] = "Pigeon|Crow|Eagle|Falcon"
    rows[0]["difficulty"] = "2"
    rows[1]["decision"] = "reject"
    write_rows(csv_path, rows)
    result = import_decisions(store, csv_path, SETTINGS)
    assert result == {"approved": 1, "rejected": 1, "skipped": 0}
    pool = store.load_all()
    assert pool["birds"].status == "approved"
    assert pool["birds"].difficulty == 2
    assert pool["birds"].words_for("en") == ["Pigeon", "Crow", "Eagle", "Falcon"]
    assert pool["cats"].status == "rejected"


def test_import_empty_decision_skips(tmp_path):
    store = seeded(tmp_path)
    csv_path = tmp_path / "review.csv"
    export_drafts(store, csv_path)
    result = import_decisions(store, csv_path, SETTINGS)
    assert result == {"approved": 0, "rejected": 0, "skipped": 2}
    assert store.load_all()["birds"].status == "draft"


@pytest.mark.parametrize("mutate,match", [
    (lambda r: r.update(id="ghost"), "unknown id"),
    (lambda r: r.update(id="done"), "not a draft"),
    (lambda r: r.update(decision="maybe"), "invalid decision"),
    (lambda r: r.update(decision="approve", words="A|B"), "expected 4-5"),
    (lambda r: r.update(decision="approve", words="A|a|B|C"), "duplicate"),
    (lambda r: r.update(decision="approve", words="A|B|C|ref:ghost"), "unknown ref"),
    (lambda r: r.update(decision="approve", difficulty="9"), "difficulty"),
])
def test_import_invalid_row_aborts_everything(tmp_path, mutate, match):
    store = seeded(tmp_path)
    csv_path = tmp_path / "review.csv"
    export_drafts(store, csv_path)
    rows = read_rows(csv_path)
    rows[1]["decision"] = "approve"
    mutate(rows[0])
    write_rows(csv_path, rows)
    with pytest.raises(ReviewImportError, match=match):
        import_decisions(store, csv_path, SETTINGS)
    pool = store.load_all()
    assert pool["cats"].status == "draft"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_review.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bwtools.commands.review'`

- [ ] **Step 3: Write the implementation**

`bwtools/commands/review.py`:

```python
import csv

from ..models import ID_PATTERN, Item

FIELDNAMES = ["id", "theme", "name", "difficulty", "words", "decision"]
DECISIONS = ("approve", "reject", "")


class ReviewImportError(ValueError):
    pass


def export_drafts(store, csv_path):
    drafts = sorted(store.by_status("draft"), key=lambda c: c.id)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for category in drafts:
            writer.writerow({
                "id": category.id,
                "theme": category.theme,
                "name": category.names["en"],
                "difficulty": category.difficulty,
                "words": "|".join(_item_token(item) for item in category.items),
                "decision": "",
            })
    return len(drafts)


def _item_token(item):
    if item.ref:
        return f"ref:{item.ref}"
    return item.word["en"]


def import_decisions(store, csv_path, settings):
    pool = store.load_all()
    with open(csv_path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    planned, errors = [], []
    for line, row in enumerate(rows, start=2):
        error, plan = _check_row(row, pool, line, settings)
        if error:
            errors.append(error)
        elif plan:
            planned.append(plan)
    if errors:
        raise ReviewImportError("\n".join(errors))
    counts = {"approved": 0, "rejected": 0,
              "skipped": len(rows) - len(planned)}
    for category, decision, items, difficulty in planned:
        if decision == "approve":
            category.items = items
            category.difficulty = difficulty
            category.status = "approved"
            counts["approved"] += 1
        else:
            category.status = "rejected"
            counts["rejected"] += 1
        store.save(category)
    return counts


def _check_row(row, pool, line, settings):
    cid = (row.get("id") or "").strip()
    decision = (row.get("decision") or "").strip().lower()
    if cid not in pool:
        return f"line {line}: unknown id '{cid}'", None
    if pool[cid].status != "draft":
        return f"line {line}: '{cid}' is not a draft", None
    if decision not in DECISIONS:
        return f"line {line}: invalid decision '{decision}'", None
    if decision == "":
        return None, None
    if decision == "reject":
        return None, (pool[cid], "reject", None, None)
    try:
        difficulty = int(row.get("difficulty") or 0)
    except ValueError:
        difficulty = 0
    if not 1 <= difficulty <= 3:
        return f"line {line}: difficulty must be 1-3", None
    tokens = [t.strip() for t in (row.get("words") or "").split("|")]
    if not settings["item_min"] <= len(tokens) <= settings["item_max"]:
        return (f"line {line}: {len(tokens)} items, expected "
                f"{settings['item_min']}-{settings['item_max']}"), None
    if any(not t for t in tokens):
        return f"line {line}: empty word", None
    lowered = [t.lower() for t in tokens]
    if len(set(lowered)) != len(lowered):
        return f"line {line}: duplicate words", None
    items = []
    for token in tokens:
        if token.startswith("ref:"):
            ref = token[4:]
            if ref not in pool or not ID_PATTERN.fullmatch(ref):
                return f"line {line}: unknown ref '{ref}'", None
            items.append(Item(ref=ref))
        else:
            items.append(Item(word={"en": token}))
    return None, (pool[cid], "approve", items, difficulty)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_review.py -v`
Expected: all PASS

- [ ] **Step 5: Wire into the CLI**

In `build_parser()`:

```python
    review = sub.add_parser("review")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_sub.add_parser("export")
    review_import = review_sub.add_parser("import")
    review_import.add_argument("csv_path")
```

In `main()`:

```python
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
```

- [ ] **Step 6: Run the full test suite**

Run: `python3 -m pytest -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add bwtools/commands/review.py bwtools/__main__.py tests/test_review.py
git commit -m "feat: CSV review export and all-or-nothing import"
```

---

### Task 8: `localize` command

**Files:**
- Create: `bwtools/commands/localize.py`
- Create: `tests/test_localize.py`
- Modify: `bwtools/__main__.py`

**Interfaces:**
- Consumes: `CategoryStore`, `LlmError`, `FakeLlm`, `make_category`.
- Produces: `localize_system(locale: str) -> str`; `run_localize(locale: str, store, llm, settings) -> dict` returning `{"localized": [ids], "failed": [(id, reason)]}`. Only `approved` categories; categories already complete in the locale are skipped silently; ref items are ignored (their target localizes itself); LLM response must be `{"name": str, "words": [str]}` with `words` length equal to the category's word-item count, else the category is recorded as failed and left untouched.
- Produces: CLI `localize --locale <code>`.

- [ ] **Step 1: Write the failing tests**

`tests/test_localize.py`:

```python
import json

from bwtools.commands.localize import run_localize
from bwtools.llm import LlmError
from bwtools.store import CategoryStore
from tests.conftest import FakeLlm, make_category

SETTINGS = {"item_min": 4, "item_max": 5}


def test_localizes_missing_locale(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", status="approved"))
    llm = FakeLlm([{"name": "Kuşlar",
                    "words": ["Güvercin", "Karga", "Kartal", "Baykuş"]}])
    result = run_localize("tr", store, llm, SETTINGS)
    assert result["localized"] == ["birds"]
    saved = store.load_all()["birds"]
    assert saved.names["tr"] == "Kuşlar"
    assert saved.words_for("tr") == ["Güvercin", "Karga", "Kartal", "Baykuş"]
    payload = json.loads(llm.calls[0][1])
    assert payload["words"] == ["Pigeon", "Crow", "Eagle", "Owl"]


def test_skips_drafts_and_complete_categories(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="draft-cat", status="draft"))
    complete = make_category(cid="done", status="approved",
                             names={"en": "Done", "tr": "Bitti"})
    for item in complete.items:
        item.word["tr"] = item.word["en"] + "-tr"
    store.save(complete)
    llm = FakeLlm([])
    result = run_localize("tr", store, llm, SETTINGS)
    assert result == {"localized": [], "failed": []}
    assert llm.calls == []


def test_wrong_word_count_fails_category_untouched(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", status="approved"))
    llm = FakeLlm([{"name": "Kuşlar", "words": ["Güvercin"]}])
    result = run_localize("tr", store, llm, SETTINGS)
    assert result["localized"] == []
    assert result["failed"][0][0] == "birds"
    assert "tr" not in store.load_all()["birds"].names


def test_llm_error_recorded_and_continues(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", status="approved"))
    store.save(make_category(cid="cats", status="approved",
                             words=("Siamese", "Persian", "Tabby", "Sphynx")))
    llm = FakeLlm([LlmError("boom"),
                   {"name": "Kediler",
                    "words": ["Siyam", "İran", "Tekir", "Sfenks"]}])
    result = run_localize("tr", store, llm, SETTINGS)
    assert result["localized"] == ["cats"]
    assert result["failed"] == [("birds", "boom")]


def test_ref_items_ignored(tmp_path):
    store = CategoryStore(tmp_path)
    store.save(make_category(cid="birds", status="approved"))
    store.save(make_category(cid="animals", status="approved",
                             words=("Horse", "Snake", "Frog"), refs=("birds",)))
    llm = FakeLlm([
        {"name": "Hayvanlar", "words": ["At", "Yılan", "Kurbağa"]},
        {"name": "Kuşlar", "words": ["Güvercin", "Karga", "Kartal", "Baykuş"]},
    ])
    result = run_localize("tr", store, llm, SETTINGS)
    assert sorted(result["localized"]) == ["animals", "birds"]
    assert store.load_all()["animals"].words_for("tr") == ["At", "Yılan", "Kurbağa"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_localize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bwtools.commands.localize'`

- [ ] **Step 3: Write the implementation**

`bwtools/commands/localize.py`:

```python
import json

from ..llm import LlmError


def localize_system(locale):
    return (
        f"You localize word-game categories into the language with code '{locale}'.\n"
        "Given a category name and its words in English, produce natural equivalents "
        "in the target language - NOT literal translations. Words may change for "
        "cultural fit but must stay in the same association category, same order, "
        "same count.\n"
        'Return ONLY a JSON object: {"name": "...", "words": ["..."]}'
    )


def run_localize(locale, store, llm, settings):
    localized, failed = [], []
    for category in sorted(store.by_status("approved"), key=lambda c: c.id):
        word_items = [item for item in category.items if item.word]
        name_done = locale in category.names
        words_done = all(locale in item.word for item in word_items)
        if name_done and words_done:
            continue
        payload = json.dumps(
            {"name": category.names["en"],
             "words": [item.word["en"] for item in word_items]},
            ensure_ascii=False)
        try:
            raw = llm.complete_json(localize_system(locale), payload)
        except LlmError as error:
            failed.append((category.id, str(error)))
            continue
        if (not isinstance(raw, dict)
                or not isinstance(raw.get("name"), str) or not raw["name"].strip()
                or not isinstance(raw.get("words"), list)
                or len(raw["words"]) != len(word_items)
                or not all(isinstance(w, str) and w.strip() for w in raw["words"])):
            failed.append((category.id, "invalid localization payload"))
            continue
        category.names[locale] = raw["name"].strip()
        for item, word in zip(word_items, raw["words"]):
            item.word[locale] = word.strip()
        store.save(category)
        localized.append(category.id)
    return {"localized": localized, "failed": failed}
```

- [ ] **Step 4: Wire into the CLI**

In `build_parser()`:

```python
    localize = sub.add_parser("localize")
    localize.add_argument("--locale", required=True)
```

In `main()`:

```python
    if args.command == "localize":
        from .llm import LlmClient
        from .commands import localize as localize_cmd
        llm = LlmClient(settings["model"], settings.get("max_llm_retries", 3))
        result = localize_cmd.run_localize(args.locale, store, llm, settings)
        print(f"localized {len(result['localized'])}, failed {len(result['failed'])}")
        for cid, reason in result["failed"]:
            print(f"FAILED {cid}: {reason}")
        return 0 if not result["failed"] else 1
```

- [ ] **Step 5: Run the full test suite**

Run: `python3 -m pytest -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add bwtools/commands/localize.py bwtools/__main__.py tests/test_localize.py
git commit -m "feat: localize command for approved categories"
```

---

### Task 9: `compile` command with `game` and `ws` adapters

**Files:**
- Create: `bwtools/formats/__init__.py` (empty)
- Create: `bwtools/formats/game.py`
- Create: `bwtools/formats/ws.py`
- Create: `bwtools/commands/compile_cmd.py`
- Create: `tests/test_compile.py`
- Modify: `bwtools/__main__.py`

**Interfaces:**
- Consumes: `Category`, `make_category`.
- Produces: `compile_game(pool: dict[str, Category], locales: list[str]) -> tuple[dict, list[str]]` — `{"categories": [...]}` sorted by `(difficulty, id)` easiest-first, each entry `{id, theme, difficulty, image, names, items}` restricted to the requested locales; only `approved` categories complete in ALL requested locales; categories whose refs point outside the included set are dropped transitively; second element is warning strings.
- Produces: `compile_ws(pool: dict[str, Category], locale: str) -> tuple[list, list[str]]` — WS-compatible `[{"categoryId": <localized name>, "wordsIds": [<localized words>]}]`; ref items flatten to the referenced approved category's localized name; incomplete categories skipped with a warning.
- Produces: `bwtools/commands/compile_cmd.run(store, settings, output_dir: Path, fmt: str, locales: list[str]) -> int` writing `output/categories_game.json` or `output/words_categories_<locale>.json` per locale.
- Produces: CLI `compile --format game|ws --locale en,tr` (default `--locale` = settings `locales`).

- [ ] **Step 1: Write the failing tests**

`tests/test_compile.py`:

```python
from bwtools.formats.game import compile_game
from bwtools.formats.ws import compile_ws
from tests.conftest import make_category


def localized(cid, words, names, status="approved", refs=()):
    category = make_category(cid=cid, status=status,
                             words=tuple(w[0] for w in words), refs=refs, names=names)
    word_items = [item for item in category.items if item.word]
    for item, (en, tr) in zip(word_items, words):
        item.word["tr"] = tr
    return category


BIRD_WORDS = [("Pigeon", "Güvercin"), ("Crow", "Karga"),
              ("Eagle", "Kartal"), ("Owl", "Baykuş")]


def test_compile_game_includes_complete_categories():
    birds = localized("birds", BIRD_WORDS, {"en": "Birds", "tr": "Kuşlar"})
    payload, warnings = compile_game({"birds": birds}, ["en", "tr"])
    assert warnings == []
    entry = payload["categories"][0]
    assert entry["id"] == "birds"
    assert entry["names"] == {"en": "Birds", "tr": "Kuşlar"}
    assert entry["items"][0] == {"word": {"en": "Pigeon", "tr": "Güvercin"}}


def test_compile_game_skips_missing_locale_and_cascades_to_parents():
    birds = make_category(cid="birds", status="approved")
    animals = make_category(cid="animals", status="approved",
                            words=("Horse", "Snake", "Frog"), refs=("birds",))
    grand = make_category(cid="alive", status="approved",
                          words=("Tree", "Moss", "Fern"), refs=("animals",))
    payload, warnings = compile_game(
        {"birds": birds, "animals": animals, "alive": grand}, ["en", "tr"])
    assert payload["categories"] == []
    assert len(warnings) == 3


def test_compile_game_excludes_drafts():
    draft = make_category(cid="birds", status="draft")
    payload, warnings = compile_game({"birds": draft}, ["en"])
    assert payload["categories"] == []
    assert warnings == []


def test_compile_ws_flattens_refs_to_child_names():
    birds = localized("birds", BIRD_WORDS, {"en": "Birds", "tr": "Kuşlar"})
    animals = localized("animals",
                        [("Horse", "At"), ("Snake", "Yılan"), ("Frog", "Kurbağa")],
                        {"en": "Animals", "tr": "Hayvanlar"}, refs=("birds",))
    output, warnings = compile_ws({"birds": birds, "animals": animals}, "tr")
    assert warnings == []
    by_name = {entry["categoryId"]: entry["wordsIds"] for entry in output}
    assert by_name["Hayvanlar"] == ["At", "Yılan", "Kurbağa", "Kuşlar"]


def test_compile_ws_skips_incomplete_locale_with_warning():
    birds = make_category(cid="birds", status="approved")
    output, warnings = compile_ws({"birds": birds}, "tr")
    assert output == []
    assert "birds" in warnings[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_compile.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bwtools.formats'`

- [ ] **Step 3: Write the implementations**

`bwtools/formats/game.py`:

```python
def compile_game(pool, locales):
    approved = {cid: c for cid, c in pool.items() if c.status == "approved"}
    warnings = []
    included = {}
    for category in approved.values():
        missing = [loc for loc in locales
                   if loc not in category.names
                   or any(item.word and loc not in item.word for item in category.items)]
        if missing:
            warnings.append(
                f"{category.id}: missing locales {', '.join(missing)}, skipped")
        else:
            included[category.id] = category
    changed = True
    while changed:
        changed = False
        for cid in list(included):
            if any(ref not in included for ref in included[cid].refs()):
                warnings.append(f"{cid}: refs excluded category, skipped")
                del included[cid]
                changed = True
    categories = []
    for category in sorted(included.values(), key=lambda c: (c.difficulty, c.id)):
        categories.append({
            "id": category.id,
            "theme": category.theme,
            "difficulty": category.difficulty,
            "image": category.image,
            "names": {loc: category.names[loc] for loc in locales},
            "items": [
                {"word": {loc: item.word[loc] for loc in locales}}
                if item.word else {"ref": item.ref}
                for item in category.items
            ],
        })
    return {"categories": categories}, warnings
```

`bwtools/formats/ws.py`:

```python
def compile_ws(pool, locale):
    approved = {cid: c for cid, c in pool.items() if c.status == "approved"}
    warnings, output = [], []
    for category in sorted(approved.values(), key=lambda c: (c.difficulty, c.id)):
        if locale not in category.names:
            warnings.append(f"{category.id}: missing locale '{locale}', skipped")
            continue
        words, problem = [], None
        for item in category.items:
            if item.word:
                if locale not in item.word:
                    problem = f"missing locale '{locale}'"
                    break
                words.append(item.word[locale])
            else:
                child = approved.get(item.ref)
                if child is None or locale not in child.names:
                    problem = f"ref '{item.ref}' unavailable in '{locale}'"
                    break
                words.append(child.names[locale])
        if problem:
            warnings.append(f"{category.id}: {problem}, skipped")
            continue
        output.append({"categoryId": category.names[locale], "wordsIds": words})
    return output, warnings
```

`bwtools/commands/compile_cmd.py`:

```python
import json

from ..formats.game import compile_game
from ..formats.ws import compile_ws


def run(store, settings, output_dir, fmt, locales):
    pool = store.load_all()
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings, written = [], []
    if fmt == "game":
        payload, warnings = compile_game(pool, locales)
        path = output_dir / "categories_game.json"
        _write(path, payload)
        written.append(path)
    else:
        for locale in locales:
            data, locale_warnings = compile_ws(pool, locale)
            warnings.extend(locale_warnings)
            path = output_dir / f"words_categories_{locale}.json"
            _write(path, data)
            written.append(path)
    for warning in warnings:
        print(f"WARN {warning}")
    for path in written:
        print(f"wrote {path}")
    return 0


def _write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
```

- [ ] **Step 4: Wire into the CLI**

In `build_parser()`:

```python
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("--format", choices=("game", "ws"), default="game")
    compile_parser.add_argument("--locale")
```

In `main()`:

```python
    if args.command == "compile":
        from .commands import compile_cmd
        locales = (args.locale.split(",") if args.locale else settings["locales"])
        return compile_cmd.run(store, settings, Path(args.output_dir),
                               args.format, locales)
```

- [ ] **Step 5: Run the full test suite**

Run: `python3 -m pytest -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add bwtools/formats/ bwtools/commands/compile_cmd.py bwtools/__main__.py tests/test_compile.py
git commit -m "feat: compile command with game and ws format adapters"
```

---

### Task 10: `stats` command + README

**Files:**
- Create: `bwtools/commands/stats.py`
- Create: `tests/test_stats.py`
- Create: `README.md`
- Modify: `bwtools/__main__.py`

**Interfaces:**
- Consumes: `CategoryStore`, `make_category`.
- Produces: `compute_stats(pool: dict, locales: list[str]) -> dict` with keys `total`, `by_status` (dict), `by_theme` (dict), `locale_coverage` (locale → percent of approved categories fully covered, float rounded to 1 decimal, 0.0 when no approved categories).
- Produces: CLI `stats`.

- [ ] **Step 1: Write the failing tests**

`tests/test_stats.py`:

```python
from bwtools.commands.stats import compute_stats
from tests.conftest import make_category


def test_compute_stats():
    birds = make_category(cid="birds", theme="animals", status="approved")
    for item in birds.items:
        item.word["tr"] = item.word["en"] + "-tr"
    birds.names["tr"] = "Kuşlar"
    cats = make_category(cid="cats", theme="animals", status="approved",
                         words=("Siamese", "Persian", "Tabby", "Sphynx"))
    pizza = make_category(cid="pizza", theme="food-drink", status="draft")
    pool = {c.id: c for c in (birds, cats, pizza)}
    stats = compute_stats(pool, ["en", "tr"])
    assert stats["total"] == 3
    assert stats["by_status"] == {"approved": 2, "draft": 1}
    assert stats["by_theme"] == {"animals": 2, "food-drink": 1}
    assert stats["locale_coverage"] == {"en": 100.0, "tr": 50.0}


def test_empty_pool():
    stats = compute_stats({}, ["en"])
    assert stats["total"] == 0
    assert stats["locale_coverage"] == {"en": 0.0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_stats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bwtools.commands.stats'`

- [ ] **Step 3: Write the implementation**

`bwtools/commands/stats.py`:

```python
from collections import Counter


def compute_stats(pool, locales):
    approved = [c for c in pool.values() if c.status == "approved"]
    coverage = {}
    for locale in locales:
        complete = sum(
            1 for c in approved
            if locale in c.names
            and all(locale in item.word for item in c.items if item.word))
        coverage[locale] = round(100 * complete / len(approved), 1) if approved else 0.0
    return {
        "total": len(pool),
        "by_status": dict(Counter(c.status for c in pool.values())),
        "by_theme": dict(Counter(c.theme for c in pool.values())),
        "locale_coverage": coverage,
    }


def run(store, settings):
    stats = compute_stats(store.load_all(), settings["locales"])
    print(f"total: {stats['total']}")
    for section in ("by_status", "by_theme"):
        print(f"{section}:")
        for key, count in sorted(stats[section].items()):
            print(f"  {key}: {count}")
    print("locale_coverage:")
    for locale, percent in stats["locale_coverage"].items():
        print(f"  {locale}: {percent}%")
    return 0
```

- [ ] **Step 4: Wire into the CLI**

In `build_parser()`: `sub.add_parser("stats")`.

In `main()`:

```python
    if args.command == "stats":
        from .commands import stats as stats_cmd
        return stats_cmd.run(store, settings)
```

- [ ] **Step 5: Write `README.md`**

```markdown
# bubble-word-tools

Content pipeline for the bubble word game: generates, validates, reviews,
localizes, and compiles word-association categories.

## Setup

    python3 -m pip install -e ".[dev]"
    export ANTHROPIC_API_KEY=...

## Pipeline

    python3 -m bwtools generate --theme animals --count 20
    python3 -m bwtools generate --theme all
    python3 -m bwtools generate --parents --count 10
    python3 -m bwtools validate
    python3 -m bwtools review export
    python3 -m bwtools review import reports/review.csv
    python3 -m bwtools localize --locale tr
    python3 -m bwtools compile --format game
    python3 -m bwtools compile --format ws --locale en,tr
    python3 -m bwtools stats

Categories live in `data/categories/` (one JSON file each, committed).
`reports/` and `output/` are generated and gitignored.

Design spec: `docs/superpowers/specs/2026-07-14-category-generator-design.md`

## Tests

    python3 -m pytest
```

- [ ] **Step 6: Run the full test suite and a CLI smoke test**

Run: `python3 -m pytest -v && python3 -m bwtools stats`
Expected: all tests PASS; stats prints `total: 0` and empty sections.

- [ ] **Step 7: Commit**

```bash
git add bwtools/commands/stats.py tests/test_stats.py README.md bwtools/__main__.py
git commit -m "feat: stats command and README"
```

---

## Final Verification

- [ ] Run: `python3 -m pytest -v` — everything passes.
- [ ] Run the offline end-to-end path (no API key needed): `python3 -m bwtools validate && python3 -m bwtools review export && python3 -m bwtools stats` — all exit 0.
- [ ] The live-API acceptance run from the spec (`generate --theme all` → review → `localize --locale tr` → `compile`) is executed manually by the user once an `ANTHROPIC_API_KEY` is available; it is not part of automated verification.
