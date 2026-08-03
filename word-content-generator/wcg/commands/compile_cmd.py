import json

from ..core.validation import validate_pool
from ..games.bubble import compile_bubble
from ..games.ws import compile_ws


def run(store, settings, output_dir, fmt, locales):
    pool = store.load_all()
    errors = [issue for issue in validate_pool(pool, settings) if issue.severity == "error"]
    if errors:
        for issue in errors:
            print(f"ERROR [{issue.category_id}] {issue.message}")
        return 1
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings, written = [], []
    emitted = 0
    if fmt == "bubble":
        payload, warnings = compile_bubble(pool, locales)
        emitted += len(payload["categories"])
        path = output_dir / "categories_bubble.json"
        _write(path, payload)
        written.append(path)
    else:
        for locale in locales:
            data, locale_warnings = compile_ws(pool, locale)
            warnings.extend(locale_warnings)
            emitted += len(data)
            path = output_dir / f"words_categories_{locale}.json"
            _write(path, data)
            written.append(path)
    for warning in warnings:
        print(f"WARN {warning}")
    for path in written:
        print(f"wrote {path}")
    return 1 if emitted == 0 else 0


def _write(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
