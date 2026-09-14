#!/usr/bin/env python3
"""Fill the `meaning` field for every word in the Unity default level set (Assets/Resources/Levels).

Sources, in priority order, keyed by (category, word):
  1. meanings already in the files being processed (never overwritten),
  2. the variant_2 level set in Unity (Assets/Resources/LevelSets/variant_2),
  3. CURATED_MEANINGS in level-generator/index.html (category|word),
  4. BAKED_MEANINGS in level-generator/index.html (word only, category-agnostic),
  5. a local cache (meanings_cache.json) of previously generated text,
  6. the Claude API for whatever is still missing (ANTHROPIC_API_KEY, or the file written by set_api_key.py).

Usage
  python3 fill_meanings.py --dry-run                 # scan + reuse, report coverage, write nothing
  python3 fill_meanings.py --generate                # also generate the missing ones (API), fill the cache
  python3 fill_meanings.py --generate --apply        # ... and write the level files
  python3 fill_meanings.py --apply                   # write whatever is known (reuse + cache) without the API
Options: --levels 51-1001  --model claude-sonnet-5  --batch-size 40  --workers 6  --unity PATH

The files are rewritten in the same compact JSON Unity wrote them in (verified byte-for-byte on
untouched files), with `meaning` inserted right after `fullWord` like the variant_2 set.
"""
import argparse
import glob
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_UNITY = os.path.normpath(os.path.join(HERE, "..", "..", "bubble-word"))
CACHE_PATH = os.path.join(HERE, "meanings_cache.json")
REPORT_PATH = os.path.join(HERE, "meanings_report.txt")
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"

MAX_LEN = 80

SYSTEM_PROMPT = """You write one-line meanings for words in a word-association puzzle game for a general audience.
Each word belongs to a category; the meaning must fit that category's sense of the word.
Style, matching the existing set exactly:
- 3 to 10 words, plain everyday English, no jargon, no trailing period, lowercase start unless it begins with a name.
- Never use the word itself (or its plural/verb form) inside the meaning.
- Describe what the thing is, not the category: "a young cat" for Kitten in Baby Animals; "the highest mountain in Africa" for Kilimanjaro in Mountains; "a layered bulb that makes you cry" for Onion in Toppings.
- For people, places, brands and titles say who or what it is in a few words: "the 16th US president" for Lincoln in US Presidents.
- If a word means the same thing in every listed category, the meanings may be identical; if a category changes the sense (Bass in Fish vs Bass in Music), write different meanings.
Return only JSON: {"<word>": {"<category>": "<meaning>", ...}, ...} with exactly the words and categories you were given."""


# ----------------------------------------------------------------------------- scanning

def level_number(path):
    return int(re.search(r"Level_(\d+)\.json$", path).group(1))


def load_levels(folder, lo, hi):
    files = sorted(glob.glob(os.path.join(folder, "Level_*.json")), key=level_number)
    return [p for p in files if lo <= level_number(p) <= hi]


def key(category, word):
    return f"{category.strip().lower()}|{word.strip().lower()}"


def scan_pairs(paths):
    """(category, word) pairs across the given level files, with the display forms seen first."""
    pairs = OrderedDict()          # key -> (category, word, parentCategory)
    for path in paths:
        data = json.load(open(path, encoding="utf-8"))
        for cat in data["categories"]:
            for w in cat["words"]:
                k = key(cat["category"], w["fullWord"])
                if k not in pairs:
                    pairs[k] = (cat["category"].strip(), w["fullWord"].strip(), (cat.get("parentCategory") or "").strip())
    return pairs


# ----------------------------------------------------------------------------- sources

def variant2_meanings(unity):
    by_pair, by_word = {}, {}
    for path in glob.glob(os.path.join(unity, "Assets", "Resources", "LevelSets", "*", "Level_*.json")):
        data = json.load(open(path, encoding="utf-8"))
        for cat in data["categories"]:
            for w in cat["words"]:
                m = (w.get("meaning") or "").strip()
                if not m:
                    continue
                by_pair.setdefault(key(cat["category"], w["fullWord"]), m)
                by_word.setdefault(w["fullWord"].strip().lower(), m)
    return by_pair, by_word


def tool_meanings():
    """CURATED_MEANINGS (category|word) and BAKED_MEANINGS (word) from index.html."""
    src = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()

    def grab(name):
        m = re.search(r"const " + name + r"=(\{.*?\});\n", src, re.S)
        return json.loads(m.group(1)) if m else {}

    curated = {k.lower(): v for k, v in grab("CURATED_MEANINGS").items()}
    baked = {k.lower(): v for k, v in grab("BAKED_MEANINGS").items()}
    curated_by_word = {}
    for k, v in curated.items():
        curated_by_word.setdefault(k.split("|", 1)[1], v)
    return curated, curated_by_word, baked


def existing_meanings(paths):
    found = {}
    for path in paths:
        data = json.load(open(path, encoding="utf-8"))
        for cat in data["categories"]:
            for w in cat["words"]:
                m = (w.get("meaning") or "").strip()
                if m:
                    found.setdefault(key(cat["category"], w["fullWord"]), m)
    return found


def load_cache():
    if os.path.exists(CACHE_PATH):
        return json.load(open(CACHE_PATH, encoding="utf-8"))
    return {}


_cache_lock = threading.Lock()


def save_cache(cache):
    with _cache_lock:
        tmp = CACHE_PATH + ".tmp"
        json.dump(cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)
        os.replace(tmp, CACHE_PATH)


# ----------------------------------------------------------------------------- validation

def word_forms(word):
    w = word.lower()
    forms = {w}
    if w.endswith("s"):
        forms.add(w[:-1])
    forms.add(w + "s")
    forms.add(w + "es")
    return forms


def validate(word, meaning):
    m = (meaning or "").strip().rstrip(".").strip()
    if not m:
        return None, "empty"
    if len(m) > MAX_LEN:
        return None, "too long"
    if "\n" in m:
        return None, "multiline"
    tokens = set(re.findall(r"[a-z']+", m.lower()))
    if tokens & word_forms(word) and " " not in word:
        return None, "contains the word"
    return m, None


# ----------------------------------------------------------------------------- API

KEY_FILE = os.path.expanduser("~/.config/bubble-word-tools/anthropic_api_key")


def load_api_key():
    """ANTHROPIC_API_KEY from the environment, else the file written by set_api_key.py."""
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if key:
        return key
    if os.path.exists(KEY_FILE):
        return open(KEY_FILE, encoding="utf-8").read().strip()
    return ""


def ssl_context():
    """python.org builds ship without root certificates; prefer certifi, then the macOS system bundle."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for bundle in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        if os.path.exists(bundle):
            return ssl.create_default_context(cafile=bundle)
    return ssl.create_default_context()


SSL_CONTEXT = ssl_context()


class ApiError(Exception):
    pass


def call_claude(model, api_key, user_text, max_tokens=8192, retries=5):
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_text}],
    }).encode("utf-8")
    last = None
    for attempt in range(retries):
        if attempt:
            time.sleep(min(30, 2 ** attempt))
        req = urllib.request.Request(API_URL, data=body, method="POST", headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
        })
        try:
            with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
                payload = json.load(resp)
            text = "".join(block.get("text", "") for block in payload.get("content", []))
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.removeprefix("```").removeprefix("json")
                cleaned = cleaned.rsplit("```", 1)[0].strip()
            return json.loads(cleaned)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:300]!r}"
            if e.code in (400, 401, 403):
                raise ApiError(last)
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
            last = repr(e)
    raise ApiError(f"gave up after {retries} attempts: {last}")


def build_request(batch):
    """batch: list of (word, [(category, parent), ...])"""
    lines = []
    for word, cats in batch:
        shown = []
        for cat, parent in cats:
            shown.append(f"{cat} (under {parent})" if parent else cat)
        lines.append(f"- {word}: " + "; ".join(shown))
    return "Words and their categories:\n" + "\n".join(lines) + "\n\nReturn the JSON object."


def generate_missing(missing, cache, model, api_key, batch_size, workers, report):
    """missing: dict key -> (category, word, parent). Fills cache[key] = meaning."""
    by_word = defaultdict(list)
    for k, (cat, word, parent) in missing.items():
        by_word[word.lower()].append((cat, parent, k, word))
    words = sorted(by_word)
    batches = [words[i:i + batch_size] for i in range(0, len(words), batch_size)]
    print(f"generating {len(missing)} pairs for {len(words)} words in {len(batches)} requests with {model} ...", flush=True)

    done_pairs = 0
    failures = []

    def run(batch_words, pass_no):
        batch = [(by_word[w][0][3], [(c, p) for c, p, _, _ in by_word[w]]) for w in batch_words]
        result = call_claude(model, api_key, build_request(batch))
        out, bad = {}, []
        for w in batch_words:
            entries = by_word[w]
            got = None
            for kk in (entries[0][3], w, entries[0][3].lower(), entries[0][3].title()):
                if isinstance(result, dict) and kk in result:
                    got = result[kk]
                    break
            if not isinstance(got, dict):
                bad.extend(entries)
                continue
            lower = {str(k).strip().lower(): v for k, v in got.items()}
            for cat, parent, k, word in entries:
                raw = lower.get(cat.lower()) or lower.get(f"{cat} (under {parent})".lower()) or (next(iter(lower.values())) if len(lower) == 1 else None)
                m, why = validate(word, raw if isinstance(raw, str) else "")
                if m:
                    out[k] = m
                else:
                    bad.append((cat, parent, k, word))
        return out, bad

    pending = batches
    for pass_no in (1, 2, 3):
        if not pending:
            break
        next_pending = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run, b, pass_no): b for b in pending}
            for fut in as_completed(futures):
                b = futures[fut]
                try:
                    out, bad = fut.result()
                except ApiError as e:
                    print(f"  batch failed ({len(b)} words): {e}", flush=True)
                    if "HTTP 401" in str(e) or "HTTP 403" in str(e):
                        raise
                    next_pending.append(b)
                    continue
                cache.update(out)
                done_pairs += len(out)
                save_cache(cache)
                if bad:
                    # retry the bad ones as smaller batches next pass
                    bad_words = sorted({word.lower() for _, _, _, word in bad})
                    next_pending.extend([bad_words[i:i + max(5, batch_size // 4)] for i in range(0, len(bad_words), max(5, batch_size // 4))])
                print(f"  {done_pairs}/{len(missing)} pairs done (pass {pass_no})", flush=True)
        pending = next_pending
    for b in pending:
        for w in b:
            for cat, parent, k, word in by_word[w]:
                if k not in cache:
                    failures.append(f"{cat} | {word}")
    if failures:
        report.append(f"UNRESOLVED after 3 passes ({len(failures)}):")
        report.extend("  " + f for f in failures)
    return failures


# ----------------------------------------------------------------------------- sense check

SENSE_SYSTEM_PROMPT = """You check one-line meanings for words in a word-association puzzle game.
Each word currently has ONE meaning used under several categories. For every category decide whether that
meaning fits the sense the category implies. Bass under "fish" is a fish, not an instrument; Mercury under
"liquids" is the metal, not the planet; Apple under "computer brands" is the company.
Return only JSON: {"<label>": {"<category>": "ok" | "<replacement meaning>", ...}, ...} using exactly the labels
(a word, or "word [n]" when the same word is listed more than once) and categories given. Replacement meanings follow the house style: 3 to 10 plain words, no trailing period,
lowercase start unless a name, never containing the word itself."""


def build_sense_request(batch):
    """batch: list of (word, meaning, [category, ...])"""
    lines = [f'- {word} | current meaning: "{meaning}" | categories: ' + "; ".join(cats) for word, meaning, cats in batch]
    return "Words:\n" + "\n".join(lines) + "\n\nReturn the JSON object."


def sense_check(candidates, cache, model, api_key, batch_size, workers, report):
    """candidates: dict label -> (label, meaning, [(category, key), ...]); a label is the word, or "word [n]" when
    the word has several shared meanings. Returns dict key -> replacement."""
    words = sorted(candidates)
    batches = [words[i:i + batch_size] for i in range(0, len(words), batch_size)]
    print(f"sense-checking {len(words)} word groups across {sum(len(candidates[w][2]) for w in words)} categories in {len(batches)} requests ...", flush=True)
    replaced = {}

    def run(batch_words):
        batch = [(candidates[w][0], candidates[w][1], [c for c, _ in candidates[w][2]]) for w in batch_words]
        body = json.dumps({"model": model, "max_tokens": 8192, "system": SENSE_SYSTEM_PROMPT,
                           "messages": [{"role": "user", "content": build_sense_request(batch)}]}).encode("utf-8")
        last = None
        for attempt in range(5):
            if attempt:
                time.sleep(min(30, 2 ** attempt))
            req = urllib.request.Request(API_URL, data=body, method="POST", headers={
                "content-type": "application/json", "x-api-key": api_key, "anthropic-version": API_VERSION})
            try:
                with urllib.request.urlopen(req, timeout=120, context=SSL_CONTEXT) as resp:
                    payload = json.load(resp)
                text = "".join(b.get("text", "") for b in payload.get("content", [])).strip()
                if text.startswith("```"):
                    text = text.removeprefix("```").removeprefix("json").rsplit("```", 1)[0].strip()
                result = json.loads(text)
                break
            except urllib.error.HTTPError as e:
                last = f"HTTP {e.code}: {e.read()[:200]!r}"
                if e.code in (400, 401, 403):
                    raise ApiError(last)
            except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
                last = repr(e)
        else:
            raise ApiError(f"gave up: {last}")
        out = {}
        lowered = {str(k).lower(): v for k, v in result.items()} if isinstance(result, dict) else {}
        for w in batch_words:
            display, meaning, cats = candidates[w]
            got = lowered.get(w) or lowered.get(display.lower())
            if not isinstance(got, dict):
                continue
            gotl = {str(k).lower(): v for k, v in got.items()}
            bare = re.sub(r"\s*\[\d+\]$", "", display)
            for cat, k in cats:
                v = gotl.get(cat.lower())
                if not isinstance(v, str) or v.strip().lower() in ("ok", "", meaning.lower()):
                    continue
                m, why = validate(bare, v)
                if m:
                    out[k] = m
        return out

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run, b): b for b in batches}
        for fut in as_completed(futures):
            try:
                out = fut.result()
            except ApiError as e:
                print(f"  sense batch failed: {e}", flush=True)
                continue
            replaced.update(out)
            cache.update(out)
            save_cache(cache)
            print(f"  {len(replaced)} category meanings replaced so far", flush=True)
    report.append(f"SENSE CHECK replaced {len(replaced)} category meanings")
    return replaced


# ----------------------------------------------------------------------------- writing

def with_meaning(entry, meaning):
    """Rebuild the word dict with `meaning` right after `fullWord`, like the variant_2 files."""
    out = OrderedDict()
    for k, v in entry.items():
        if k == "meaning":
            continue
        out[k] = v
        if k == "fullWord":
            out["meaning"] = meaning
    return out


def apply_to_file(path, resolve, overwrite_keys=frozenset()):
    """resolve(category, word) -> meaning or None. Pairs in overwrite_keys are replaced even when already
    filled. Returns (filled, missing)."""
    raw = open(path, encoding="utf-8").read()
    data = json.loads(raw, object_pairs_hook=OrderedDict)
    filled = missing = 0
    per_word = {}
    for cat in data["categories"]:
        for i, w in enumerate(cat["words"]):
            k = key(cat["category"], w["fullWord"])
            if (w.get("meaning") or "").strip() and k not in overwrite_keys:
                per_word.setdefault(w["fullWord"].strip().lower(), w["meaning"])
                continue
            m = resolve(cat["category"], w["fullWord"])
            if m:
                cat["words"][i] = with_meaning(w, m)
                per_word.setdefault(w["fullWord"].strip().lower(), m)
                filled += 1
            else:
                missing += 1
    for i, w in enumerate(data.get("allWordEntries", [])):
        if (w.get("meaning") or "").strip() and not overwrite_keys:
            continue
        m = per_word.get(w["fullWord"].strip().lower())
        if m:
            data["allWordEntries"][i] = with_meaning(w, m)
    out = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if out != raw:
        open(path, "w", encoding="utf-8").write(out)
    return filled, missing


# ----------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unity", default=DEFAULT_UNITY)
    ap.add_argument("--levels", default="1-1001", help="inclusive range, e.g. 51-1001")
    ap.add_argument("--dry-run", action="store_true", help="scan and report only")
    ap.add_argument("--generate", action="store_true", help="call the Claude API for missing meanings")
    ap.add_argument("--apply", action="store_true", help="write meanings into the level files")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--batch-size", type=int, default=40)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--reuse-word-level", action="store_true",
                    help="also reuse variant_2/curated text by word alone (category-specific text may not fit; off by default)")
    ap.add_argument("--sense-check", action="store_true",
                    help="words used under several categories with one identical meaning: ask the model per category and overwrite where the sense differs")
    ap.add_argument("--regenerate-word-fallbacks", action="store_true",
                    help="pairs already filled from a word-level variant_2/curated fallback are regenerated with their category and overwritten")
    args = ap.parse_args()

    lo, hi = (int(x) for x in args.levels.split("-"))
    folder = os.path.join(args.unity, "Assets", "Resources", "Levels")
    paths = load_levels(folder, lo, hi)
    if not paths:
        sys.exit(f"no level files in {folder} for {args.levels}")

    pairs = scan_pairs(paths)
    existing = existing_meanings(paths)
    v2_pair, v2_word = variant2_meanings(args.unity)
    curated, curated_word, baked = tool_meanings()
    cache = load_cache()

    # Pairs whose file text is a word-level copy of another category's variant_2/curated meaning.
    stale = set()
    if args.regenerate_word_fallbacks:
        for k, (cat, word, parent) in pairs.items():
            if k in v2_pair or k in curated:
                continue
            w, cur = word.lower(), existing.get(k)
            if cur and (v2_word.get(w) == cur or curated_word.get(w) == cur) and cache.get(k) != cur:
                stale.add(k)
        print(f"  stale word-level fallbacks to regenerate: {len(stale)}")

    word_sources = (v2_word, curated_word, baked) if args.reuse_word_level else (baked,)

    def resolve_key(k, word):
        w = word.strip().lower()
        for source in (existing, v2_pair, curated, cache):
            if k in source and not (k in stale and source is existing):
                return source[k]
        for source in word_sources:
            if w in source:
                return source[w]
        return None

    resolved, missing = {}, OrderedDict()
    for k, (cat, word, parent) in pairs.items():
        m = resolve_key(k, word)
        if m:
            resolved[k] = m
        else:
            missing[k] = (cat, word, parent)

    words_missing = {w.lower() for _, w, _ in missing.values()}
    print(f"levels {lo}-{hi}: {len(paths)} files, {len(pairs)} category|word pairs")
    print(f"  already in files: {len(existing)}")
    print(f"  resolvable from variant_2 / curated / baked / cache: {len(resolved) - sum(1 for k in resolved if k in existing)}")
    print(f"  missing: {len(missing)} pairs across {len(words_missing)} words")

    report = []
    if args.generate and missing:
        api_key = load_api_key()
        if not api_key:
            sys.exit("no API key: export ANTHROPIC_API_KEY or run `python3 level-generator/set_api_key.py` once, or run with --apply only")
        generate_missing(missing, cache, args.model, api_key, args.batch_size, args.workers, report)
        for k in list(missing):
            if k in cache:
                resolved[k] = cache[k]
                del missing[k]
        print(f"  after generation: {len(missing)} pairs still missing")

    if args.sense_check:
        api_key = load_api_key()
        if not api_key:
            sys.exit("no API key for --sense-check")
        per_word = defaultdict(dict)
        for k, (cat, word, parent) in pairs.items():
            m = resolved.get(k)
            if m:
                per_word[word.lower()][cat] = (m, k)
        candidates = {}
        display_of = {}
        for k2, (c2, word, p2) in pairs.items():
            display_of.setdefault(word.lower(), word)
        for w, cats in per_word.items():
            if len(cats) < 2:
                continue
            groups = defaultdict(list)
            for c, (m, k2) in cats.items():
                groups[m].append((c, k2))
            shared = [(m, cs) for m, cs in groups.items() if len(cs) >= 2]
            for i, (meaning, cs) in enumerate(shared):
                label = display_of[w] if len(shared) == 1 else f"{display_of[w]} [{i + 1}]"
                candidates[label.lower()] = (label, meaning, cs)
        replaced = sense_check(candidates, cache, args.model, api_key, min(args.batch_size, 30), args.workers, report)
        resolved.update(replaced)
        stale |= set(replaced)

    if args.apply:
        filled = still = 0
        for path in paths:
            f, m = apply_to_file(path, lambda c, w: resolved.get(key(c, w)), frozenset(stale))
            filled += f
            still += m
        print(f"wrote meanings: {filled} word slots filled, {still} left empty")
    elif not args.dry_run and not args.generate:
        print("nothing done: pass --dry-run, --generate and/or --apply")

    if missing:
        report.insert(0, f"MISSING ({len(missing)} pairs):")
        report[1:1] = [f"  {cat} | {word}" for cat, word, _ in missing.values()]
    if report:
        open(REPORT_PATH, "w", encoding="utf-8").write("\n".join(report) + "\n")
        print(f"report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
