from collections import defaultdict
from dataclasses import dataclass


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
