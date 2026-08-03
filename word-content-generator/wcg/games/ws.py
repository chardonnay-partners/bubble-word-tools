from collections import Counter


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
    seen = Counter(entry["categoryId"] for entry in output)
    for name, count in seen.items():
        if count > 1:
            warnings.append(f"duplicate categoryId '{name}' in locale '{locale}'")
    return output, warnings
