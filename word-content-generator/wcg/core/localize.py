import json

from .llm import LlmError


def localize_system(locale):
    return (
        f"You localize word-game categories into the language with code '{locale}'.\n"
        "You get the category's full description plus its short display name and "
        "words in English. Produce the target-language display name and words - "
        "natural, conventional phrasing, same order, same count.\n"
        "Every word must refer to the SAME thing as the English word: use the "
        "target language's conventional name for it, or a transliteration when "
        "none exists. NEVER swap an item for a different item of the local "
        "culture: in a category described as 'Indian Snacks and Street Food', "
        "'Samosa' stays samosa in every language (Japanese サモサ) - it never "
        "becomes a local dish like Takoyaki or Empanada.\n"
        "Translate the display name so it stays faithful to the full "
        "description: if the description says Indian food, the localized name "
        "must not read as generic or local street food.\n"
        "Proper nouns follow these rules:\n"
        "- Place names use the target language's own convention: London becomes "
        "Londra in Turkish; New York stays New York in Turkish but becomes "
        "Nueva York in Spanish.\n"
        "- Person names and surnames are NEVER translated, even when they have a "
        "dictionary meaning: Danny Drinkwater keeps the surname Drinkwater in "
        "every language.\n"
        "- Other proper nouns keep their conventional local form if one exists, "
        "otherwise stay unchanged.\n"
        "Keep the category name as concise as the English one - never more "
        "than 2 words.\n"
        'Return ONLY a JSON object: {"name": "...", "words": ["..."]}'
    )


def localize_category(category, locale, llm):
    word_items = [item for item in category.items if item.word]
    if locale in category.names and all(locale in item.word for item in word_items):
        return "skipped", None
    payload = json.dumps(
        {"category": category.descriptor_or_name(),
         "name": category.names["en"],
         "words": [item.word["en"] for item in word_items]},
        ensure_ascii=False)
    raw = llm.complete_json(localize_system(locale), payload)
    if (not isinstance(raw, dict)
            or not isinstance(raw.get("name"), str) or not raw["name"].strip()
            or not isinstance(raw.get("words"), list)
            or len(raw["words"]) != len(word_items)
            or not all(isinstance(w, str) and w.strip() for w in raw["words"])):
        return "failed", "invalid localization payload"
    lowered = [w.strip().lower() for w in raw["words"]]
    if len(set(lowered)) != len(lowered):
        return "failed", "duplicate localized words"
    category.names[locale] = raw["name"].strip()
    for item, word in zip(word_items, raw["words"]):
        item.word[locale] = word.strip()
    return "localized", None


def run_localize(locale, store, llm, settings):
    localized, failed = [], []
    for category in sorted(store.by_status("approved"), key=lambda c: c.id):
        try:
            outcome, reason = localize_category(category, locale, llm)
        except LlmError as error:
            failed.append((category.id, str(error)))
            continue
        if outcome == "failed":
            failed.append((category.id, reason))
        elif outcome == "localized":
            store.save(category)
            localized.append(category.id)
    return {"localized": localized, "failed": failed}
