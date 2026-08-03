from .llm import LlmError
from .localize import localize_category
from .sheet import SheetPushError, build_rows, push_rows, update_csv_rows


def missing_locales(category, locales):
    word_items = [item for item in category.items if item.word]
    return [locale for locale in locales
            if locale != "en"
            and (locale not in category.names
                 or any(locale not in item.word for item in word_items))]


def run_backfill(store, llm, settings, csv_path, sheet_config, only_ids=None,
                 attempts=None, max_attempts=2):
    # attempts: mutable {(cid, locale): count} shared across runs. Locales that
    # failed max_attempts times are left empty instead of retried forever
    # (cost control). Pass attempts=None to force retries (manual repair).
    locales = settings["locales"]
    localized, failed, warnings = [], [], []
    pool = sorted(store.by_status("approved"), key=lambda c: c.created or "")
    for category in pool:
        if only_ids is not None and category.id not in only_ids:
            continue
        if not missing_locales(category, locales):
            continue
        changed = False
        for locale in missing_locales(category, locales):
            key = (category.id, locale)
            if attempts is not None and attempts.get(key, 0) >= max_attempts:
                continue
            try:
                outcome, reason = localize_category(category, locale, llm)
            except LlmError as error:
                failed.append([category.id, locale, str(error)])
                if attempts is not None:
                    attempts[key] = attempts.get(key, 0) + 1
                continue
            if outcome == "failed":
                failed.append([category.id, locale, reason])
                if attempts is not None:
                    attempts[key] = attempts.get(key, 0) + 1
            elif outcome == "localized":
                changed = True
        if not changed:
            continue
        store.save(category)
        localized.append(category.id)
        rows = build_rows(category, locales)
        try:
            update_csv_rows(csv_path, rows, locales)
        except (OSError, ValueError) as error:
            warnings.append(f"csv: {error}")
        if sheet_config is None:
            warnings.append("sheet: push to Google Sheet not configured")
        else:
            try:
                push_rows(rows, sheet_config["webhook_url"],
                          sheet_config["token"], action="updateRows")
            except SheetPushError as error:
                warnings.append(f"sheet: {error}")
    return {"localized": localized, "failed": failed,
            "warnings": sorted(set(warnings))}
