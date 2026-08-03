def compile_bubble(pool, locales):
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
