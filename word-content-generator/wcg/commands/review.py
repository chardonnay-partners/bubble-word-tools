import csv

from ..core.models import ID_PATTERN, Item

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
    seen_ids = set()
    for line, row in enumerate(rows, start=2):
        cid = (row.get("id") or "").strip()
        if cid in seen_ids:
            errors.append(f"line {line}: duplicate row for id '{cid}'")
            continue
        seen_ids.add(cid)
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
