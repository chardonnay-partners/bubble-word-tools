from collections import Counter

from ..core.backfill import missing_locales


def compute_stats(pool, locales):
    approved = [c for c in pool.values() if c.status == "approved"]
    coverage = {}
    for locale in locales:
        complete = sum(
            1 for c in approved
            if locale in c.names
            and all(locale in item.word for item in c.items if item.word))
        coverage[locale] = round(100 * complete / len(approved), 1) if approved else 0.0
    return {
        "total": len(pool),
        "by_status": dict(Counter(c.status for c in pool.values())),
        "by_theme": dict(Counter(c.theme for c in pool.values())),
        "locale_coverage": coverage,
        "missing_translations": sum(
            1 for c in approved if missing_locales(c, locales)),
    }


def run(store, settings):
    stats = compute_stats(store.load_all(), settings["locales"])
    print(f"total: {stats['total']}")
    for section in ("by_status", "by_theme"):
        print(f"{section}:")
        for key, count in sorted(stats[section].items()):
            print(f"  {key}: {count}")
    print("locale_coverage:")
    for locale, percent in stats["locale_coverage"].items():
        print(f"  {locale}: {percent}%")
    return 0
