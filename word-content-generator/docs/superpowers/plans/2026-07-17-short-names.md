# Short Display Names + Descriptor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Categories carry a unique descriptive internal name (`descriptor`) plus a short display name (`names`, ≤2 words) that is what gets translated; the old migrated pool is deleted.

**Architecture:** `Category` gains an optional `descriptor` field with a `descriptor_or_name()` fallback so legacy files keep working. Propose returns both names and rejects long display names; select derives the id from the descriptor; localize keeps translations short. UI shows both. CSV mechanics unchanged (keys already come from the id).

**Tech Stack:** existing wcg package, FastAPI, vanilla JS.

**Spec:** `docs/superpowers/specs/2026-07-17-short-names-design.md`

## Global Constraints

- Display name (`names[*]`): at most 2 words; variants with a 3+-word `name` are rejected, never repaired.
- `descriptor`: optional in the schema (legacy fallback = `names["en"]`); required non-empty in propose variants; drives `slugify` → id → CSV keys.
- `to_dict` includes `descriptor` only when set (legacy files round-trip unchanged).
- Pool reset deletes exactly the 20 migrated animal categories; keeps `football-world-cup-legends`, `ice-cream-flavors`, `iconic-skylines`, `.gitkeep`, and `data/localization.csv`.
- No code comments. All UI copy English.

---

### Task 1: Category.descriptor (schema + accessor)

**Files:**
- Modify: `wcg/core/models.py` (dataclass field, `from_dict`, `to_dict`, accessor)
- Test: `tests/test_models.py` (append three tests)

**Interfaces:**
- Produces: `Category.descriptor: str | None = None`; `Category.descriptor_or_name() -> str` (descriptor or `names["en"]`); `from_dict` accepts optional non-empty-string `descriptor` (else `SchemaError`); `to_dict` emits it only when set. Tasks 2-3 rely on `descriptor_or_name` and the `from_dict` key.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py` (it already imports `pytest`, `Category`, `SchemaError`):

```python
DESCRIPTOR_BASE = {"id": "australian-animals", "theme": "animals",
                   "difficulty": 1, "image": None, "status": "draft",
                   "items": [{"word": {"en": "Kangaroo"}}],
                   "names": {"en": "Animals"}}


def test_descriptor_round_trip():
    category = Category.from_dict(dict(DESCRIPTOR_BASE,
                                       descriptor="Australian Animals"))
    assert category.descriptor == "Australian Animals"
    assert category.descriptor_or_name() == "Australian Animals"
    assert category.to_dict()["descriptor"] == "Australian Animals"


def test_descriptor_absent_falls_back_to_en_name():
    category = Category.from_dict(dict(DESCRIPTOR_BASE))
    assert category.descriptor is None
    assert category.descriptor_or_name() == "Animals"
    assert "descriptor" not in category.to_dict()


def test_descriptor_empty_rejected():
    with pytest.raises(SchemaError):
        Category.from_dict(dict(DESCRIPTOR_BASE, descriptor="   "))
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_models.py -q`
Expected: 3 new FAIL (TypeError/KeyError on descriptor), previous 14 pass.

- [ ] **Step 3: Implement**

In `wcg/core/models.py`:

1. Add to the `Category` dataclass after `image: str | None = None`:

```python
    descriptor: str | None = None
```

2. In `from_dict`, after the `image` validation block, add:

```python
        descriptor = data.get("descriptor")
        if descriptor is not None and (
                not isinstance(descriptor, str) or not descriptor.strip()):
            raise SchemaError(
                f"{cid}: 'descriptor' must be null or a non-empty string")
```

and extend the constructor call to pass `descriptor=descriptor`.

3. Replace `to_dict` with:

```python
    def to_dict(self):
        data = {
            "id": self.id,
            "theme": self.theme,
            "difficulty": self.difficulty,
            "image": self.image,
            "status": self.status,
            "items": [item.to_dict() for item in self.items],
            "names": self.names,
        }
        if self.descriptor is not None:
            data["descriptor"] = self.descriptor
        return data
```

4. Add next to `words_for`/`refs`:

```python
    def descriptor_or_name(self):
        return self.descriptor or self.names["en"]
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest -q`
Expected: 109 passed (106 + 3).

- [ ] **Step 5: Commit**

```bash
git add wcg/core/models.py tests/test_models.py
git commit -m "feat: optional category descriptor with display-name fallback"
```

---

### Task 2: Propose returns descriptor + short name

**Files:**
- Modify: `wcg/core/propose.py` (`propose_system`, `validate_variant`, `run_propose`)
- Test: `tests/test_propose.py` (replace the whole file)

**Interfaces:**
- Consumes: `Category.descriptor_or_name()` (Task 1).
- Produces: variants shaped `{"name", "descriptor", "theme", "difficulty", "words"}`; `validate_variant` rejects 3+-word names (`"name longer than 2 words"`) and missing/empty descriptors (`"missing descriptor"`). Task 3's select consumes `variant["descriptor"]`.

- [ ] **Step 1: Replace `tests/test_propose.py` entirely with:**

```python
import pytest

from wcg.core.propose import (build_propose_prompt, propose_system,
                              run_propose, validate_variant)
from wcg.core.store import CategoryStore
from tests.conftest import FakeLlm, make_category

SETTINGS = {"item_min": 4, "item_max": 5, "propose_variants": 3}
THEMES = [{"id": "animals", "hint": "animal kingdom"}]


def entry(name="Planets", descriptor="Solar System Planets",
          words=("Mars", "Venus", "Jupiter", "Saturn"),
          theme="animals", difficulty=1):
    return {"name": name, "descriptor": descriptor, "theme": theme,
            "difficulty": difficulty, "words": list(words)}


def test_valid_variant_passes():
    variant, reason = validate_variant(entry(), ["animals"], SETTINGS)
    assert reason is None
    assert variant == {"name": "Planets", "descriptor": "Solar System Planets",
                       "theme": "animals", "difficulty": 1,
                       "words": ["Mars", "Venus", "Jupiter", "Saturn"]}


def test_unknown_theme_maps_to_other():
    variant, _ = validate_variant(entry(theme="space"), ["animals"], SETTINGS)
    assert variant["theme"] == "other"


def test_two_word_name_allowed():
    variant, reason = validate_variant(entry(name="Gas Giants"),
                                       ["animals"], SETTINGS)
    assert reason is None
    assert variant["name"] == "Gas Giants"


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(name=""),
    lambda e: e.update(name="Rocky Inner Planets"),
    lambda e: e.update(descriptor=""),
    lambda e: e.pop("descriptor"),
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


def test_system_prompt_explains_both_names():
    system = propose_system(4, 5, 3, ["animals"])
    assert "descriptor" in system
    assert "at most 2 words" in system


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

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_propose.py -q`
Expected: failures (descriptor assertions and rejections not implemented); no collection errors.

- [ ] **Step 3: Implement in `wcg/core/propose.py`**

Replace `propose_system` with:

```python
def propose_system(item_min, item_max, variants, theme_ids):
    return (
        "You suggest word-association categories for a mobile word game.\n"
        f"Given a topic, return ONLY a JSON array of exactly {variants} distinct "
        "interpretations of that topic. Each element:\n"
        '{"name": "<Short Name>", "descriptor": "<Specific Descriptor>", '
        '"theme": "<theme-id>", "difficulty": 1, "words": ["..."]}\n'
        "'name' is the display name shown in the game: at most 2 words, a single "
        "word when the meaning survives (descriptor 'Australian Animals' can have "
        "name 'Animals').\n"
        "'descriptor' uniquely describes the interpretation and may be longer.\n"
        f"Each variant must have between {item_min} and {item_max} words.\n"
        "Variants must differ meaningfully: a different angle, specificity, "
        "or word set.\n"
        "STRONGLY prefer easy, internationally understandable words: "
        "cross-language cognates and proper nouns (Uranus, Jupiter, Pizza, Taxi).\n"
        f"'theme' must be one of: {', '.join(theme_ids)} - or 'other' if none fits.\n"
        "Difficulty: 1 = internationally transparent everyday words, "
        "2 = common but language-dependent, 3 = niche."
    )
```

In `validate_variant`, after the existing `missing name` check, add:

```python
    if len(name.split()) > 2:
        return None, "name longer than 2 words"
    descriptor = entry.get("descriptor")
    if not isinstance(descriptor, str) or not descriptor.strip():
        return None, "missing descriptor"
```

and change the success return to:

```python
    return {"name": name.strip(), "descriptor": descriptor.strip(),
            "theme": theme, "difficulty": difficulty,
            "words": [w.strip() for w in words]}, None
```

In `run_propose`, change the `existing_names` line to:

```python
    existing_names = sorted(c.descriptor_or_name() for c in pool.values())
```

- [ ] **Step 4: Run the suite**

Run: `python3 -m pytest -q`
Expected: 114 passed (109 − 9 old propose + 14 new).

- [ ] **Step 5: Commit**

```bash
git add wcg/core/propose.py tests/test_propose.py
git commit -m "feat: propose short display name plus unique descriptor"
```

---

### Task 3: Select/id from descriptor, short localized names, UI columns

**Files:**
- Modify: `wcg/web/app.py` (select: id + saved dict; categories rows)
- Modify: `wcg/core/localize.py` (brevity line in prompt)
- Modify: `wcg/web/static/app.js` (variant meta, pool row), `wcg/web/static/index.html` (Descriptor column header)
- Test: `tests/test_web.py` (fixture + three new tests + one assertion), `tests/test_localize.py` (one test)

**Interfaces:**
- Consumes: `variant["descriptor"]` (Task 2), `descriptor_or_name()` (Task 1).
- Produces: select id = `unique_id(slugify(variant["descriptor"]), pool)`; saved category carries `descriptor`; `/api/categories` rows gain `"descriptor"`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_web.py`, change the `variant()` helper to:

```python
def variant(name="Planets", words=("Mars", "Venus", "Jupiter", "Saturn")):
    return {"name": name, "descriptor": name, "theme": "animals",
            "difficulty": 1, "words": list(words)}
```

(Descriptor equal to the name keeps every existing id assertion — `planets`, `planets-2` — valid.)

In `test_categories_listing_and_filters`, after `assert entry["id"] == "birds"`, add:

```python
    assert entry["descriptor"] == "Birds"
```

Append:

```python
def test_select_id_comes_from_descriptor(tmp_path):
    llm = FakeLlm([{"name": "Gezegenler",
                    "words": ["Mars", "Venüs", "Jüpiter", "Satürn"]}])
    client, store = build_client(tmp_path, llm)
    body = variant()
    body["descriptor"] = "Solar System Planets"
    response = client.post("/api/select", json={"variant": body})
    assert response.json()["category"]["id"] == "solar-system-planets"
    saved = store.load_all()["solar-system-planets"]
    assert saved.descriptor == "Solar System Planets"
    assert saved.names["en"] == "Planets"


def test_select_missing_descriptor_returns_400(tmp_path):
    client, _ = build_client(tmp_path, FakeLlm([]))
    body = variant()
    del body["descriptor"]
    assert client.post("/api/select", json={"variant": body}).status_code == 400
```

In `tests/test_localize.py`, append:

```python
def test_localize_system_keeps_name_short():
    assert "never more than 2 words" in localize_system("tr")
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest tests/test_web.py tests/test_localize.py -q`
Expected: new tests FAIL; the rest pass.

- [ ] **Step 3: Implement**

`wcg/web/app.py` — in `select()`:

```python
        cid = unique_id(slugify(variant["descriptor"]), pool)
```

and add `"descriptor": variant["descriptor"],` to the `Category.from_dict({...})` literal (after `"id": cid,`).

In `categories()`, extend the row dict with `"descriptor": category.descriptor_or_name(),` after `"name": ...`.

`wcg/core/localize.py` — in `localize_system`, after the line ending `"same count.\n"`, add:

```python
        "Keep the category name as concise as the English one - never more "
        "than 2 words.\n"
```

`wcg/web/static/app.js`:
- `renderVariants` meta line becomes:

```javascript
    meta.textContent = `${variant.descriptor} · theme: ${variant.theme} · difficulty: ${variant.difficulty}`;
```

- `renderPool` cell array becomes:

```javascript
      [c.name, c.descriptor, c.theme, c.status, c.difficulty, c.items.join(" · ")]
```

`wcg/web/static/index.html` — the pool table header row becomes:

```html
        <tr><th>Name</th><th>Descriptor</th><th>Theme</th><th>Status</th><th>Difficulty</th><th>Items</th></tr>
```

- [ ] **Step 4: Run the suite**

Run: `python3 -m pytest -q`
Expected: 117 passed (114 + 3).

- [ ] **Step 5: Commit**

```bash
git add wcg/web/app.py wcg/core/localize.py wcg/web/static/ tests/test_web.py tests/test_localize.py
git commit -m "feat: derive ids from descriptor, keep display names short in UI and translations"
```

---

### Task 4: Pool reset

**Files:**
- Delete: the 20 migrated animal category files under `data/categories/`

- [ ] **Step 1: Delete the migrated pool**

```bash
cd data/categories
git rm african-animals.json amphibians.json animal-habitats.json aquarium-fish.json arctic-animals.json australian-animals.json big-cats.json birds-of-prey.json common-pets.json farm-animals.json farm-birds.json insects.json marine-mammals.json nocturnal-animals.json primates.json reptiles.json rodents.json sea-creatures.json venomous-animals.json zoo-animals.json
cd ../..
```

Keep: `football-world-cup-legends.json`, `ice-cream-flavors.json`, `iconic-skylines.json`, `.gitkeep`, and `data/localization.csv` (untouched).

- [ ] **Step 2: Verify**

Run: `python3 -m pytest -q` — expected 117 passed.
Run: `python3 -m wcg validate` — expected `3 categories, 0 errors, 0 warnings`, exit 0 (the three picks share no words).
Run: `ls data/categories/` — exactly the three JSON files plus `.gitkeep`.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: reset pool to live picks only"
```

---

## Final Verification

- [ ] `python3 -m pytest -q` — 117 passed.
- [ ] `python3 -m wcg validate` — 3 categories, 0 errors.
- [ ] Live (user-driven): restart `wcg-serve`; propose shows short names with descriptors on cards; picking saves an id derived from the descriptor and short translated names in the CSV; Pool tab shows the Descriptor column.
