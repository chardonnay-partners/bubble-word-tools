# Push Picks to Shared Google Sheet — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a variant is picked in the web UI, its localization rows are pushed to the shared Google Sheet (inserted at the top of the "Word Content" tab via an Apps Script webhook) and the web UI Pool tab lists newest picks first; a `wcg sheet-push` command backfills/repairs from `localization.csv`.

**Architecture:** The user deploys a small Apps Script web app on the spreadsheet (idempotent by Key, inserts at row 2, token-guarded). Python side: `wcg/core/sheet.py` gains `build_rows`/`push_rows` (stdlib urllib), `/api/select` pushes inline after the CSV append (failures → warnings), `Category` gains an optional `created` timestamp used to sort `/api/categories` newest-first, and a new CLI command pushes the whole CSV (server dedupes).

**Tech Stack:** Python 3.14, FastAPI, stdlib `urllib`/`csv`/`json`, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-21-sheet-push-design.md`

## Global Constraints

- No new Python dependencies — HTTP via `urllib.request` only.
- Locales come from `settings["locales"]`; never hardcode the locale list.
- Push failures must NEVER block or roll back a pick: category file + CSV are written first.
- `config/sheet.json` holds a secret — it must be gitignored, never committed.
- Webhook payload shape: `{"token": str, "rows": [[key, <locale cells...>], ...]}` — same column order as `localization.csv`.
- Run tests with `python -m pytest` from the repo root.
- Code style: match existing files (no type hints, compact helpers, 4-space indent).

---

### Task 1: Optional `created` timestamp on Category

**Files:**
- Modify: `wcg/core/models.py` (Category dataclass, `from_dict`, `to_dict`)
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Category.created` — `str | None`, ISO-8601 UTC timestamp, default `None`. `Category.from_dict` accepts an optional `"created"` key (non-empty string when present); `to_dict()` includes `"created"` only when set. Old category JSON files (no `created`) load unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
def test_created_round_trips_when_set():
    data = {"id": "birds", "theme": "animals", "difficulty": 1,
            "status": "draft", "items": [{"word": {"en": "Crow"}}],
            "names": {"en": "Birds"}, "created": "2026-07-21T10:00:00+00:00"}
    category = Category.from_dict(data)
    assert category.created == "2026-07-21T10:00:00+00:00"
    assert category.to_dict()["created"] == "2026-07-21T10:00:00+00:00"


def test_created_absent_stays_none_and_off_dict():
    data = {"id": "birds", "theme": "animals", "difficulty": 1,
            "status": "draft", "items": [{"word": {"en": "Crow"}}],
            "names": {"en": "Birds"}}
    category = Category.from_dict(data)
    assert category.created is None
    assert "created" not in category.to_dict()


def test_created_empty_string_rejected():
    data = {"id": "birds", "theme": "animals", "difficulty": 1,
            "status": "draft", "items": [{"word": {"en": "Crow"}}],
            "names": {"en": "Birds"}, "created": "  "}
    with pytest.raises(SchemaError):
        Category.from_dict(data)
```

Check the top of `tests/test_models.py`: it must import `pytest`, `Category`, and `SchemaError` — add any of those that are missing.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_models.py -v -k created`
Expected: FAIL — `Category.__init__() got an unexpected keyword argument` / assertion errors.

- [ ] **Step 3: Implement**

In `wcg/core/models.py`, add a field to the `Category` dataclass (after `descriptor`):

```python
    created: str | None = None
```

In `Category.from_dict`, after the `descriptor` validation block, add:

```python
        created = data.get("created")
        if created is not None and (not isinstance(created, str) or not created.strip()):
            raise SchemaError(f"{cid}: 'created' must be null or a non-empty string")
```

Pass it through the constructor call at the end of `from_dict`:

```python
        return cls(id=cid, theme=theme, difficulty=difficulty, status=status,
                   items=items, names=names, image=image, descriptor=descriptor,
                   created=created)
```

In `to_dict`, after the `descriptor` block, add:

```python
        if self.created is not None:
            data["created"] = self.created
```

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add wcg/core/models.py tests/test_models.py
git commit -m "feat: optional created timestamp on Category"
```

---

### Task 2: `build_rows`, `push_rows`, `SheetPushError` in sheet.py

**Files:**
- Modify: `wcg/core/sheet.py`
- Test: `tests/test_sheet.py`

**Interfaces:**
- Consumes: `Category` (with `.items`, `.names`, `.id`).
- Produces:
  - `build_rows(category, locales) -> list[list[str]]` — first row is the category (`[id, names per locale...]`), then one row per word item (`[id.word-key, word per locale...]`). Ref items skipped. Exactly what `append_rows` writes.
  - `push_rows(rows, url, token, timeout=20) -> dict` — POSTs `{"token": token, "rows": rows}` as JSON to `url`, returns the parsed JSON reply. Raises `SheetPushError` on network errors, non-JSON replies, non-dict replies, or a reply containing a truthy `"error"` field.
  - `SheetPushError(Exception)`.
  - `append_rows` keeps its exact signature/behavior but is refactored to use `build_rows`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_sheet.py` (it already imports `pytest`, `LOCALE_LABELS`, `append_rows`, `word_key`, `make_category`, and defines `sheet_category()` / `LOCALES = ["en", "tr", "es"]`). Update the import line to:

```python
from wcg.core.sheet import (LOCALE_LABELS, SheetPushError, append_rows,
                            build_rows, push_rows, word_key)
```

Then add:

```python
def test_build_rows_matches_csv_layout():
    rows = build_rows(sheet_category(), LOCALES)
    assert rows == [
        ["world-cities", "World Cities", "Dünya Şehirleri", ""],
        ["world-cities.london", "London", "Londra", ""],
        ["world-cities.new-york", "New York", "New York", ""],
        ["world-cities.rio-de-janeiro", "Rio, de Janeiro", "Rio", ""],
        ["world-cities.tokyo", "Tokyo", "Tokyo", ""],
    ]


def test_build_rows_skips_ref_items():
    rows = build_rows(make_category(cid="mixed", refs=("owls",)), LOCALES)
    assert len(rows) == 5
    assert all("owls" not in row[0] for row in rows)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_push_rows_posts_json_and_returns_reply(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["timeout"] = timeout
        seen["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse('{"inserted": 2, "skipped": 0}')

    monkeypatch.setattr("wcg.core.sheet.urlopen", fake_urlopen)
    result = push_rows([["a", "x"], ["b", "y"]], "https://example.test/exec", "tok")
    assert result == {"inserted": 2, "skipped": 0}
    assert seen["url"] == "https://example.test/exec"
    assert seen["timeout"] == 20
    assert seen["body"] == {"token": "tok", "rows": [["a", "x"], ["b", "y"]]}


def test_push_rows_raises_on_network_error(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise URLError("no route to host")

    monkeypatch.setattr("wcg.core.sheet.urlopen", fake_urlopen)
    with pytest.raises(SheetPushError):
        push_rows([["a", "x"]], "https://example.test/exec", "tok")


def test_push_rows_raises_on_error_reply(monkeypatch):
    monkeypatch.setattr("wcg.core.sheet.urlopen",
                        lambda req, timeout=None: FakeResponse('{"error": "invalid token"}'))
    with pytest.raises(SheetPushError, match="invalid token"):
        push_rows([["a", "x"]], "https://example.test/exec", "tok")


def test_push_rows_raises_on_non_json_reply(monkeypatch):
    monkeypatch.setattr("wcg.core.sheet.urlopen",
                        lambda req, timeout=None: FakeResponse("<html>login</html>"))
    with pytest.raises(SheetPushError):
        push_rows([["a", "x"]], "https://example.test/exec", "tok")
```

Also add to the imports at the top of `tests/test_sheet.py`:

```python
import json
from urllib.error import URLError
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sheet.py -v`
Expected: ImportError — `cannot import name 'SheetPushError'`.

- [ ] **Step 3: Implement**

In `wcg/core/sheet.py`, replace the imports at the top with:

```python
import csv
import json
import re
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
```

Add after `word_key`:

```python
class SheetPushError(Exception):
    pass


def build_rows(category, locales):
    rows = [[category.id] + [category.names.get(locale, "") for locale in locales]]
    for item in category.items:
        if not item.word:
            continue
        rows.append([f"{category.id}.{word_key(item.word['en'])}"]
                    + [item.word.get(locale, "") for locale in locales])
    return rows


def push_rows(rows, url, token, timeout=20):
    payload = json.dumps({"token": token, "rows": rows}).encode("utf-8")
    request = Request(url, data=payload,
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except (URLError, OSError) as error:
        raise SheetPushError(f"request failed: {error}")
    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        raise SheetPushError(f"unexpected reply: {body[:200]}")
    if not isinstance(result, dict):
        raise SheetPushError(f"unexpected reply: {body[:200]}")
    if result.get("error"):
        raise SheetPushError(str(result["error"]))
    return result
```

Refactor `append_rows` to use `build_rows` — replace these lines:

```python
    word_items = [item for item in category.items if item.word]
    rows = [[category.id] + [category.names.get(locale, "") for locale in locales]]
    for item in word_items:
        rows.append([f"{category.id}.{word_key(item.word['en'])}"]
                    + [item.word.get(locale, "") for locale in locales])
```

with:

```python
    rows = build_rows(category, locales)
```

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest`
Expected: all PASS (including the pre-existing `append_rows` tests, proving the refactor is behavior-preserving).

- [ ] **Step 5: Commit**

```bash
git add wcg/core/sheet.py tests/test_sheet.py
git commit -m "feat: build_rows/push_rows for Google Sheet webhook"
```

---

### Task 3: `/api/select` stamps `created` and pushes to the sheet

**Files:**
- Modify: `wcg/web/app.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `build_rows`, `push_rows`, `SheetPushError` from `wcg.core.sheet` (Task 2); `Category.created` (Task 1).
- Produces: `create_app` loads `config/sheet.json` (`{"webhook_url": str, "token": str}`) if present. `/api/select` sets `created` on new categories and pushes rows after the CSV append; failures/absence append `sheet: ...` strings to `warnings`. Exact warning when unconfigured: `"sheet: push to Google Sheet not configured"`.

- [ ] **Step 1: Update `build_client` and existing warning assertions**

In `tests/test_web.py`, replace `build_client` with:

```python
def build_client(tmp_path, llm, sheet_config=None):
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")
    (config / "themes.json").write_text(json.dumps(THEMES), encoding="utf-8")
    if sheet_config:
        (config / "sheet.json").write_text(json.dumps(sheet_config), encoding="utf-8")
    data = tmp_path / "categories"
    data.mkdir(exist_ok=True)
    app = create_app(data_dir=data, config_dir=config, llm_factory=lambda: llm)
    return TestClient(app), CategoryStore(data)
```

In `test_select_saves_approved_and_localizes`, replace

```python
    assert response.json()["warnings"] == []
```

with

```python
    assert response.json()["warnings"] == ["sheet: push to Google Sheet not configured"]
```

(The other warning tests index `warnings[0]`, which stays correct — the sheet warning is appended last.)

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_web.py`:

```python
SHEET_CONFIG = {"webhook_url": "https://example.test/exec", "token": "tok"}


def test_select_pushes_rows_to_sheet(tmp_path, monkeypatch):
    calls = []

    def fake_push(rows, url, token):
        calls.append((rows, url, token))
        return {"inserted": len(rows), "skipped": 0}

    monkeypatch.setattr("wcg.web.app.push_rows", fake_push)
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, _ = build_client(tmp_path, llm, sheet_config=SHEET_CONFIG)
    response = client.post("/api/select", json={"variant": variant()})
    assert response.json()["warnings"] == []
    rows, url, token = calls[0]
    assert url == "https://example.test/exec"
    assert token == "tok"
    assert rows[0] == ["planets", "Planets", "Gezegenler"]
    assert rows[1] == ["planets.mars", "Mars", "Mars"]
    assert len(rows) == 5


def test_select_push_failure_is_warning_only(tmp_path, monkeypatch):
    from wcg.core.sheet import SheetPushError

    def fake_push(rows, url, token):
        raise SheetPushError("request failed: down")

    monkeypatch.setattr("wcg.web.app.push_rows", fake_push)
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, store = build_client(tmp_path, llm, sheet_config=SHEET_CONFIG)
    response = client.post("/api/select", json={"variant": variant()})
    assert response.status_code == 200
    assert response.json()["warnings"] == ["sheet: request failed: down"]
    assert "planets" in store.load_all()
    assert "planets.mars" in (tmp_path / "localization.csv").read_text(encoding="utf-8")


def test_select_stamps_created(tmp_path):
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, store = build_client(tmp_path, llm)
    response = client.post("/api/select", json={"variant": variant()})
    created = response.json()["category"]["created"]
    assert created and created.endswith("+00:00")
    assert store.load_all()["planets"].created == created
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_web.py -v`
Expected: the three new tests FAIL (no push, no `created` key); `test_select_saves_approved_and_localizes` also FAILS until the warning is implemented.

- [ ] **Step 4: Implement**

In `wcg/web/app.py`:

Replace the import line

```python
from ..core.sheet import append_rows
```

with

```python
from ..core.sheet import SheetPushError, append_rows, build_rows, push_rows
```

Add to the stdlib imports at the top:

```python
from datetime import datetime, timezone
```

In `create_app`, after the `themes` loading lines, add:

```python
    sheet_path = config_path / "sheet.json"
    sheet_config = (json.loads(sheet_path.read_text(encoding="utf-8"))
                    if sheet_path.exists() else None)
```

In the `select` handler, add `"created"` to the `Category.from_dict({...})` payload (after `"names"`):

```python
        "created": datetime.now(timezone.utc).isoformat(),
```

Still in `select`, after the existing `append_rows` try/except block, add:

```python
        if sheet_config is None:
            warnings.append("sheet: push to Google Sheet not configured")
        else:
            try:
                push_rows(build_rows(category, settings["locales"]),
                          sheet_config["webhook_url"], sheet_config["token"])
            except SheetPushError as error:
                warnings.append(f"sheet: {error}")
```

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add wcg/web/app.py tests/test_web.py
git commit -m "feat: push picks to Google Sheet webhook on select"
```

---

### Task 4: Newest picks first in `/api/categories`

**Files:**
- Modify: `wcg/web/app.py` (`categories` handler)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `Category.created` (Task 1).
- Produces: `/api/categories` ordered by `created` descending; categories without `created` come last, alphabetical by id. Each row keeps its existing fields (no new field needed by the UI — order alone drives display).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web.py`:

```python
def test_categories_newest_first_then_legacy_alphabetical(tmp_path):
    client, store = build_client(tmp_path, None)
    old = make_category(cid="birds", status="approved")
    store.save(old)
    first = make_category(cid="pizza", status="approved")
    first.created = "2026-07-20T09:00:00+00:00"
    store.save(first)
    second = make_category(cid="cheese", status="approved")
    second.created = "2026-07-21T09:00:00+00:00"
    store.save(second)
    ids = [c["id"] for c in client.get("/api/categories").json()["categories"]]
    assert ids == ["cheese", "pizza", "birds"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_web.py::test_categories_newest_first_then_legacy_alphabetical -v`
Expected: FAIL — order is `["birds", "cheese", "pizza"]`.

- [ ] **Step 3: Implement**

In the `categories` handler in `wcg/web/app.py`, replace

```python
        for category in sorted(store.load_all().values(), key=lambda c: c.id):
```

with

```python
        pool = sorted(store.load_all().values(), key=lambda c: c.id)
        pool.sort(key=lambda c: c.created or "", reverse=True)
        for category in pool:
```

(Stable sort: timestamped picks first, newest on top; legacy `created=None` categories tie on `""` and keep their alphabetical order.)

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest`
Expected: all PASS (`test_categories_listing_and_filters` filters to a single row, so it is order-insensitive).

- [ ] **Step 5: Commit**

```bash
git add wcg/web/app.py tests/test_web.py
git commit -m "feat: newest picks first in Pool tab"
```

---

### Task 5: `wcg sheet-push` backfill/repair command

**Files:**
- Create: `wcg/commands/sheet_push.py`
- Modify: `wcg/__main__.py`
- Test: `tests/test_sheet_push.py` (new file)

**Interfaces:**
- Consumes: `push_rows`, `SheetPushError` from `wcg.core.sheet` (Task 2).
- Produces: `sheet_push.run(config_dir, csv_path) -> int` (exit code: 0 ok/nothing to push, 1 push failed, 2 missing config or CSV). CLI: `wcg sheet-push` pushes every data row of `data/localization.csv` (header skipped) to the webhook; the webhook's dedupe makes this a safe backfill/repair.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sheet_push.py`:

```python
import json

from wcg.commands import sheet_push
from wcg.core.sheet import SheetPushError

CSV = ("Key,English(en),Turkish(tr)\n"
       "planets,Planets,Gezegenler\n"
       "planets.mars,Mars,Mars\n")


def setup_dirs(tmp_path, with_config=True, with_csv=True):
    config = tmp_path / "config"
    config.mkdir()
    if with_config:
        (config / "sheet.json").write_text(json.dumps(
            {"webhook_url": "https://example.test/exec", "token": "tok"}),
            encoding="utf-8")
    csv_path = tmp_path / "localization.csv"
    if with_csv:
        csv_path.write_text(CSV, encoding="utf-8")
    return config, csv_path


def test_pushes_all_csv_rows(tmp_path, monkeypatch, capsys):
    calls = []

    def fake_push(rows, url, token):
        calls.append((rows, url, token))
        return {"inserted": 1, "skipped": 1}

    monkeypatch.setattr("wcg.commands.sheet_push.push_rows", fake_push)
    config, csv_path = setup_dirs(tmp_path)
    assert sheet_push.run(config, csv_path) == 0
    rows, url, token = calls[0]
    assert rows == [["planets", "Planets", "Gezegenler"],
                    ["planets.mars", "Mars", "Mars"]]
    assert url == "https://example.test/exec"
    assert token == "tok"
    out = capsys.readouterr().out
    assert "1 inserted" in out
    assert "1 already in sheet" in out


def test_missing_config_returns_2(tmp_path, capsys):
    config, csv_path = setup_dirs(tmp_path, with_config=False)
    assert sheet_push.run(config, csv_path) == 2
    assert "sheet.json" in capsys.readouterr().out


def test_missing_csv_returns_2(tmp_path, capsys):
    config, csv_path = setup_dirs(tmp_path, with_csv=False)
    assert sheet_push.run(config, csv_path) == 2
    assert "localization.csv" in capsys.readouterr().out


def test_push_error_returns_1(tmp_path, monkeypatch, capsys):
    def fake_push(rows, url, token):
        raise SheetPushError("invalid token")

    monkeypatch.setattr("wcg.commands.sheet_push.push_rows", fake_push)
    config, csv_path = setup_dirs(tmp_path)
    assert sheet_push.run(config, csv_path) == 1
    assert "invalid token" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sheet_push.py -v`
Expected: ImportError — `wcg.commands.sheet_push` does not exist.

- [ ] **Step 3: Implement the command**

Create `wcg/commands/sheet_push.py`:

```python
import csv
import json
from pathlib import Path

from ..core.sheet import SheetPushError, push_rows


def run(config_dir, csv_path):
    config_path = Path(config_dir) / "sheet.json"
    if not config_path.exists():
        print(f"ERROR {config_path} not found. "
              "See docs/sheet-webhook-setup.md for setup.")
        return 2
    config = json.loads(config_path.read_text(encoding="utf-8"))
    csv_path = Path(csv_path)
    if not csv_path.exists():
        print(f"ERROR {csv_path} not found")
        return 2
    with open(csv_path, encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))[1:]
    if not rows:
        print("nothing to push")
        return 0
    try:
        result = push_rows(rows, config["webhook_url"], config["token"])
    except SheetPushError as error:
        print(f"ERROR {error}")
        return 1
    print(f"pushed {len(rows)} rows: {result.get('inserted', 0)} inserted, "
          f"{result.get('skipped', 0)} already in sheet")
    return 0
```

- [ ] **Step 4: Wire up the CLI**

In `wcg/__main__.py`, in `build_parser`, after `sub.add_parser("stats")`, add:

```python
    sub.add_parser("sheet-push")
```

In `main`, before the final `return 2`, add:

```python
    if args.command == "sheet-push":
        from .commands import sheet_push
        return sheet_push.run(args.config_dir,
                              Path(args.data_dir).parent / "localization.csv")
```

- [ ] **Step 5: Run the full test suite and the CLI**

Run: `python -m pytest`
Expected: all PASS.

Run: `python -m wcg sheet-push`
Expected: `ERROR config/sheet.json not found. See docs/sheet-webhook-setup.md for setup.` with exit code 2 (webhook not deployed yet).

- [ ] **Step 6: Commit**

```bash
git add wcg/commands/sheet_push.py wcg/__main__.py tests/test_sheet_push.py
git commit -m "feat: wcg sheet-push backfill command"
```

---

### Task 6: Webhook setup docs + gitignore

**Files:**
- Create: `docs/sheet-webhook-setup.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: payload shape from Task 2 (`{"token", "rows"}`), config shape from Task 3 (`config/sheet.json`).
- Produces: paste-ready Apps Script + user setup steps.

- [ ] **Step 1: Add `config/sheet.json` to `.gitignore`**

Append this line to `.gitignore`:

```
config/sheet.json
```

- [ ] **Step 2: Write the setup doc**

Create `docs/sheet-webhook-setup.md`:

````markdown
# One-time setup: Google Sheet push webhook

Lets the generator push new picks straight into the shared pool spreadsheet
(tab "Word Content"), inserted at the top so people see the newest first.
Takes ~5 minutes.

## 1. Add the Apps Script to the spreadsheet

1. Open the pool spreadsheet:
   https://docs.google.com/spreadsheets/d/1qW17E9iSseOB3V3jj97PqWCqVy0M6ws_r-HqVJthXO0/edit
2. Menu: **Extensions → Apps Script**.
3. Delete any code in the editor and paste this, then set `TOKEN` to a long
   random string (e.g. run `openssl rand -hex 24` in a terminal):

```javascript
const TOKEN = "PASTE-A-LONG-RANDOM-STRING-HERE";
const SHEET_NAME = "Word Content";

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const body = JSON.parse(e.postData.contents);
    if (body.token !== TOKEN) {
      return reply({error: "invalid token"});
    }
    if (!Array.isArray(body.rows) || !body.rows.length) {
      return reply({error: "no rows"});
    }
    const sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME);
    const lastRow = sheet.getLastRow();
    const existing = new Set(
      lastRow > 1
        ? sheet.getRange(2, 1, lastRow - 1, 1).getValues()
            .map(function (row) { return String(row[0]); })
        : []);
    const width = sheet.getLastColumn();
    const fresh = body.rows
      .filter(function (row) { return !existing.has(String(row[0])); })
      .map(function (row) {
        const cells = row.slice(0, width);
        while (cells.length < width) cells.push("");
        return cells;
      });
    if (fresh.length) {
      sheet.insertRowsBefore(2, fresh.length);
      sheet.getRange(2, 1, fresh.length, width).setValues(fresh);
    }
    return reply({inserted: fresh.length,
                  skipped: body.rows.length - fresh.length});
  } finally {
    lock.releaseLock();
  }
}

function reply(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
```

4. Click the save icon (name the project anything, e.g. "wcg webhook").

## 2. Deploy as a web app

1. **Deploy → New deployment**.
2. Gear icon → type **Web app**.
3. *Execute as:* **Me** · *Who has access:* **Anyone**.
4. Click **Deploy**, authorize when prompted, and copy the **Web app URL**
   (ends in `/exec`).

Note: after any later edit to the script you must **Deploy → Manage
deployments → edit → New version**, otherwise the URL keeps serving the old
code.

## 3. Configure the generator

Create `config/sheet.json` (gitignored — it holds the secret):

```json
{
  "webhook_url": "https://script.google.com/macros/s/DEPLOYMENT-ID/exec",
  "token": "the same TOKEN string you pasted in the script"
}
```

## 4. Backfill and verify

```bash
python -m wcg sheet-push
```

Expected output like: `pushed 25 rows: 16 inserted, 9 already in sheet` — and
the new rows appear at the top of the Word Content tab.

From now on every pick in the web UI is pushed automatically; if the push
fails you'll see a `sheet: ...` warning in the status line, and rerunning
`python -m wcg sheet-push` repairs the sheet from `data/localization.csv`.

## How it behaves

- **Idempotent:** rows whose Key already exists in column A are skipped, so
  re-pushing is always safe.
- **Newest on top:** new rows are inserted at row 2, below the header.
- The webhook never edits or deletes existing rows.
````

- [ ] **Step 3: Verify and commit**

Run: `python -m pytest`
Expected: all PASS.

Run: `git status`
Expected: only the two intended files listed; `config/sheet.json` (if present) NOT listed.

```bash
git add docs/sheet-webhook-setup.md .gitignore
git commit -m "docs: Google Sheet webhook setup guide"
```

---

## Post-implementation (needs the user)

1. User follows `docs/sheet-webhook-setup.md` (deploy script, create `config/sheet.json`).
2. Run `python -m wcg sheet-push` — expect 16 inserted, 9 skipped.
3. Pick a word set in the web UI and confirm it appears at the top of the Google Sheet and at the top of the Pool tab.
