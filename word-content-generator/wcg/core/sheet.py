import csv
import json
import re
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

LOCALE_LABELS = {
    "en": "English(en)",
    "tr": "Turkish(tr)",
    "fr": "French(fr)",
    "de": "German(de)",
    "ja": "Japanese(ja)",
    "ko": "Korean(ko)",
    "pt": "Portuguese(pt)",
    "es": "Spanish(es)",
    "ru": "Russian(ru)",
}


def word_key(word):
    key = re.sub(r"[^a-z0-9]+", "-", word.lower()).strip("-")
    return key or "item"


class SheetPushError(Exception):
    pass


def build_rows(category, locales):
    rows = [[category.id] + [category.names.get(locale, "") for locale in locales]]
    for item in category.items:
        if not item.word:
            continue
        rows.append([f"{category.id}.{word_key(item.word['en'])}"]
                    + [item.word.get(locale, "") for locale in locales])
    return rows


def push_rows(rows, url, token, timeout=20, action=None):
    body = {"token": token, "rows": rows}
    if action:
        body["action"] = action
    payload = json.dumps(body).encode("utf-8")
    request = Request(url, data=payload,
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except (URLError, OSError) as error:
        raise SheetPushError(f"request failed: {error}")
    try:
        result = json.loads(body)
    except json.JSONDecodeError:
        raise SheetPushError(f"unexpected reply: {body[:200]}")
    if not isinstance(result, dict):
        raise SheetPushError(f"unexpected reply: {body[:200]}")
    if result.get("error"):
        raise SheetPushError(str(result["error"]))
    return result


def csv_header(locales):
    return ["Key"] + [LOCALE_LABELS.get(l, f"{l}({l})") for l in locales]


def check_header(csv_path, expected):
    with open(csv_path, encoding="utf-8", newline="") as handle:
        found = next(csv.reader(handle), [])
    if found != expected:
        raise ValueError(
            f"localization.csv header mismatch: file has {found}, "
            f"settings expect {expected}")


def append_rows(category, csv_path, locales):
    csv_path = Path(csv_path)
    new_file = not csv_path.exists()
    expected = csv_header(locales)
    if not new_file:
        check_header(csv_path, expected)
    rows = build_rows(category, locales)
    with open(csv_path, "a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(expected)
        writer.writerows(rows)
    return len(rows)


def update_csv_rows(csv_path, rows, locales):
    csv_path = Path(csv_path)
    expected = csv_header(locales)
    if not csv_path.exists():
        existing = []
    else:
        check_header(csv_path, expected)
        with open(csv_path, encoding="utf-8", newline="") as handle:
            existing = list(csv.reader(handle))[1:]
    fresh = {row[0]: row for row in rows}
    merged = [fresh.pop(line[0], line) for line in existing]
    merged.extend(fresh.values())
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(expected)
        writer.writerows(merged)
    return len(rows)
