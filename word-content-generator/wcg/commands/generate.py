from collections import Counter

from ..core.models import Category, SchemaError


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
    existing_names = sorted(c.descriptor_or_name() for c in theme_categories)
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
        f"- {c.id}: {c.descriptor_or_name()} (theme: {c.theme})"
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
