# Exactly 4 Items Per Category

**Decision:** Every category holds exactly 4 items. Proposals, generation, and validation all enforce 4 — never 5.

**Approach (chosen: config-only, Option A):** The 4–5 range lives solely in `config/settings.json` (`item_min`, `item_max`); propose, generate, parents mode, select validation, and `validate_pool` all read it from settings. Setting `item_max` to 4 enforces the rule everywhere with zero code changes. LLM prompts will read "between 4 and 4 words" — awkward but unambiguous; rejected Option B (prompt wording polish to "exactly 4") as unnecessary churn in migrated code.

## Changes

1. `config/settings.json`: `"item_max": 5` → `"item_max": 4`.
2. Data migration: 14 of the 20 draft categories have 5 items; remove the **last** item from each so the committed pool passes validation. All are drafts; no approved content is touched. Writes go through the existing atomic store.

## Not Changing

- `item_min` stays 4. No prompt text, validation logic, or test fixtures change (tests supply their own settings dicts).
- Ref items count toward the 4 exactly as words do (existing `validate_pool` semantics).

## Verification

- `python3 -m pytest -q` — suite stays green (96).
- `python3 -m wcg validate` — 20 categories, 0 errors, exit 0.
- Live: restart `wcg-serve` (settings load at startup); a propose call returns 4-word variants only; a 5-word variant POSTed to `/api/select` is rejected 400.
