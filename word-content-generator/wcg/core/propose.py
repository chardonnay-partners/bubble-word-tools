def propose_system(item_min, item_max, variants, theme_ids):
    return (
        "You suggest word-association categories for a mobile word game.\n"
        f"Given a topic, return ONLY a JSON array of exactly {variants} distinct "
        "interpretations of that topic. Each element:\n"
        '{"name": "<Short Name>", "descriptor": "<Specific Descriptor>", '
        '"theme": "<theme-id>", "difficulty": 1, "words": ["..."]}\n'
        "'name' is the display name shown in the game: at most 2 words, as short "
        "as possible WITHOUT losing what defines the category. NEVER drop a "
        "qualifier that changes the meaning: descriptor 'Indian Snacks and "
        "Street Food' must keep name 'Indian Snacks' - never 'Street Food', "
        "which wrongly suggests street food in general. Only drop words that "
        "are redundant: 'Types of Coffee Beverages' can be 'Coffee Drinks'.\n"
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


def build_propose_prompt(topic, existing_names, existing_words):
    lines = [f"Topic: {topic}"]
    if existing_names:
        lines.append("Existing category names (do not duplicate): "
                     + ", ".join(existing_names))
    if existing_words:
        lines.append("Words already in the pool (prefer alternatives): "
                     + ", ".join(existing_words))
    return "\n".join(lines)


def validate_variant(entry, theme_ids, settings):
    if not isinstance(entry, dict):
        return None, "not an object"
    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        return None, "missing name"
    if len(name.split()) > 2:
        return None, "name longer than 2 words"
    descriptor = entry.get("descriptor")
    if not isinstance(descriptor, str) or not descriptor.strip():
        return None, "missing descriptor"
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
    difficulty = entry.get("difficulty")
    if not isinstance(difficulty, int) or isinstance(difficulty, bool) \
            or not 1 <= difficulty <= 3:
        return None, "difficulty must be an integer 1-3"
    theme = entry.get("theme")
    if not isinstance(theme, str) or theme not in theme_ids:
        theme = "other"
    return {"name": name.strip(), "descriptor": descriptor.strip(),
            "theme": theme, "difficulty": difficulty,
            "words": [w.strip() for w in words]}, None


def run_propose(topic, store, llm, settings, themes):
    pool = store.load_all()
    existing_names = sorted(c.descriptor_or_name() for c in pool.values())
    existing_words = sorted({w.strip().lower()
                             for c in pool.values() for w in c.words_for("en")})
    theme_ids = [t["id"] for t in themes]
    raw = llm.complete_json(
        propose_system(settings["item_min"], settings["item_max"],
                       settings.get("propose_variants", 3), theme_ids),
        build_propose_prompt(topic, existing_names, existing_words))
    variants = []
    for entry in raw if isinstance(raw, list) else []:
        variant, _ = validate_variant(entry, theme_ids, settings)
        if variant:
            variants.append(variant)
    return variants
