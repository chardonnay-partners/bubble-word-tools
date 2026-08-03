# Exactly 4 Items Per Category Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce exactly 4 items per category everywhere by lowering `item_max` to 4 and trimming the 14 existing 5-item draft categories.

**Architecture:** The 4–5 range lives solely in `config/settings.json`; propose, generate, parents mode, select validation, and `validate_pool` all read it from there, so no code changes. Data migration goes through the existing atomic `CategoryStore`.

**Tech Stack:** Python ≥3.11, existing `wcg` package.

**Spec:** `docs/superpowers/specs/2026-07-17-exact-4-items-design.md`

## Global Constraints

- `item_min` stays 4; only `item_max` changes. No code, prompt text, or test fixture changes.
- Only draft categories are touched; the item removed is always the **last** in `items`.
- Writes go through `CategoryStore.save` (atomic, canonical formatting).
- No code comments (project convention).

---

### Task 1: Lower item_max to 4 and trim the pool

**Files:**
- Modify: `config/settings.json:4` (`"item_max": 5` → `"item_max": 4`)
- Modify: the 14 five-item files under `data/categories/` (via script, not by hand)

**Interfaces:**
- Consumes: `wcg.core.store.CategoryStore(root)` — `.load_all() -> dict[str, Category]`, `.save(category)`; `Category.items: list[Item]`.
- Produces: a pool where every category has exactly 4 items; settings that make every generator/validator enforce 4.

- [ ] **Step 1: Edit settings**

In `config/settings.json` change:

```json
  "item_max": 5,
```

to:

```json
  "item_max": 4,
```

- [ ] **Step 2: Trim 5-item categories via the store**

Run from the repo root:

```bash
python3 - <<'EOF'
from pathlib import Path
from wcg.core.store import CategoryStore

store = CategoryStore(Path("data/categories"))
for category in sorted(store.load_all().values(), key=lambda c: c.id):
    if len(category.items) == 5:
        category.items.pop()
        store.save(category)
        print(category.id)
EOF
```

Expected: exactly 14 category ids printed (african-animals, animal-habitats, arctic-animals, australian-animals, big-cats, birds-of-prey, common-pets, farm-animals, insects, reptiles, rodents, sea-creatures, zoo-animals, and one more from the pool — the script's output is authoritative).

- [ ] **Step 3: Verify no 5-item categories remain**

```bash
python3 - <<'EOF'
import json, glob
counts = sorted(len(json.load(open(p))["items"]) for p in glob.glob("data/categories/*.json"))
print(set(counts), len(counts))
EOF
```

Expected: `{4} 20`

- [ ] **Step 4: Run the suite and validate**

Run: `python3 -m pytest -q`
Expected: 96 passed (tests supply their own settings dicts, so none are affected).

Run: `python3 -m wcg validate`
Expected: `20 categories, 0 errors, N warnings` and exit 0 (warning count may shift from 14 as removed words change cross-category reuse — errors must be 0).

- [ ] **Step 5: Commit**

```bash
git add config/settings.json data/categories/
git commit -m "feat: enforce exactly 4 items per category"
```

- [ ] **Step 6: Restart the running web server**

If `wcg-serve` is running, kill and relaunch it (settings load at app startup):

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
kill <pid>
wcg-serve > /tmp/wcg-serve.log 2>&1 &
curl -s http://localhost:8000/api/health
```

Expected: `{"status":"ok"}`; a subsequent propose returns 4-word variants only.

---

## Final Verification

- [ ] `python3 -m pytest -q` — green.
- [ ] `python3 -m wcg validate` — 0 errors, exit 0.
- [ ] Live: propose a topic in the UI — every variant card shows exactly 4 words; picking one saves a 4-item category.
