#!/usr/bin/env python3
"""Build pool51.js (categories + meanings for variant_2 levels 51-100) from the authored text files.

Source of truth: pool/pool_51_100_*.txt   (hand-authored; see the header of each file for the format)
Output:          pool51.js                (window.POOL_51 / window.MEANINGS_51, loaded by index.html)

Checks: tier/domain present, 4+ single-token capitalised words of <= 12 letters, no duplicate words inside a
category, no clash with a category name already in the tool, every sprite id exists in the Word Solitaire
illustration library (skipped with a warning when the library is not on this machine).

Usage: python3 pool/build_pool.py [--library "<card illustrations dir>"]
"""
import argparse, glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_LIB = os.path.expanduser('~/Desktop/Projects/word-solitaire/Assets/Art/Common/Sprites/Game Assets/card illustrations')

# Authored but held back. The pool's standing rule is "nothing dark or anatomical" (design review 2026-09-08).
EXCLUDE = {
    'Vampires', 'Burial Places', 'Tarot Cards',                                  # dark
    'Bones', 'Muscles', 'Body Tissues', 'Heart Anatomy', 'Brain Parts',          # anatomical
    'Organ Systems', 'Teeth', 'Eye Parts', 'Human Organs', 'Hormones',
    'Blades', 'Navy', 'Battles',                                                 # weapons / war
}

def parse(path):
    cats, cur = [], None
    for ln, raw in enumerate(open(path, encoding='utf-8'), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if '|' in line and '=' not in line.split('|')[0]:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) not in (3, 4):
                sys.exit(f'{path}:{ln}: header needs "Name | tier | domain [| set]"')
            cur = {'name': parts[0], 'tier': int(parts[1]), 'domain': parts[2], 'set': parts[3] if len(parts) == 4 else None,
                   'words': [], 'src': f'{os.path.basename(path)}:{ln}'}
            cats.append(cur)
            continue
        if cur is None or '=' not in line:
            sys.exit(f'{path}:{ln}: expected Word=meaning')
        left, meaning = line.split('=', 1)
        word, _, wset = left.partition('@')
        cur['words'].append({'word': word.strip(), 'set': (wset.strip() or cur['set']), 'meaning': meaning.strip()})
    return cats

def existing_names(index_html):
    h = open(index_html, encoding='utf-8').read()
    names = set()
    i = h.index('const CURATED_POOL=[')
    seg = h[i:h.index('\n', i)]
    names |= {m.group(1).lower() for m in re.finditer(r'\["([^"\]]+)",\[', seg)}
    j = h.index('const CURATED_NEW={'); k = h.index('\nconst CURATED_MEANINGS', j)
    names |= {m.group(1).lower() for m in re.finditer(r"\['([^']+)',\[", h[j:k])}          # ['Name',[words…]] only, never the words
    return names

def library_ids(lib):
    if not os.path.isdir(lib):
        return None
    ids = set()
    for root, _, files in os.walk(lib):
        ids |= {f[:-4] for f in files if f.endswith('.png') and '__' in f}
    return ids

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--library', default=DEFAULT_LIB); a = ap.parse_args()
    cats = []
    for f in sorted(glob.glob(os.path.join(HERE, 'pool_51_100_*.txt'))):
        cats += parse(f)
    held = [c['name'] for c in cats if c['name'] in EXCLUDE]
    cats = [c for c in cats if c['name'] not in EXCLUDE]
    lib = library_ids(a.library)
    if lib is None:
        print(f'WARNING: illustration library not found at {a.library}; sprite ids not checked')
    taken = existing_names(os.path.join(ROOT, 'index.html'))
    errors, seen = [], set()
    for c in cats:
        key = c['name'].lower()
        if key in seen: errors.append(f"{c['src']}: duplicate category {c['name']}")
        if key in taken: errors.append(f"{c['src']}: {c['name']} already exists in the tool's pool")
        seen.add(key)
        if c['tier'] not in (1, 2, 3, 4): errors.append(f"{c['src']}: bad tier")
        if len(c['words']) < 4: errors.append(f"{c['src']}: {c['name']} needs 4+ words")
        ws = [w['word'] for w in c['words']]
        if len({w.lower() for w in ws}) != len(ws): errors.append(f"{c['src']}: {c['name']} repeats a word")
        for w in c['words']:
            if not re.fullmatch(r"[A-Z][A-Za-z]{1,11}", w['word']): errors.append(f"{c['src']}: {c['name']} / {w['word']}: single capitalised word of 2-12 letters expected")
            if not w['meaning'] or '"' in w['meaning']: errors.append(f"{c['src']}: {c['name']} / {w['word']}: meaning missing or contains a double quote")
            if w['set']:
                w['icon'] = f"{w['set']}__{w['word'].lower()}"
                if lib is not None and w['icon'] not in lib: errors.append(f"{c['src']}: {c['name']} / {w['word']}: sprite {w['icon']} not in the library")
        if c['set'] and any(not w.get('icon') for w in c['words']): errors.append(f"{c['src']}: {c['name']} mixes pictured and plain words")
    if errors:
        print('\n'.join(errors)); sys.exit(f'{len(errors)} problem(s); pool51.js not written')

    pool, meanings = [], {}
    for c in cats:
        entry = [c['name'], [w['word'] for w in c['words']], c['tier'], c['domain']]
        if c['set']: entry.append([w['icon'] for w in c['words']])
        pool.append(entry)
        for w in c['words']: meanings[f"{c['name']}|{w['word']}"] = w['meaning']
    out = os.path.join(ROOT, 'pool51.js')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('/* Generated by pool/build_pool.py from pool/pool_51_100_*.txt. Do not edit by hand. */\n')
        f.write('window.POOL_51=' + json.dumps(pool, ensure_ascii=False, separators=(',', ':')) + ';\n')
        f.write('window.MEANINGS_51=' + json.dumps(meanings, ensure_ascii=False, separators=(',', ':')) + ';\n')
    tiers = {t: sum(1 for c in cats if c['tier'] == t) for t in (1, 2, 3, 4)}
    print(f"pool51.js: {len(pool)} categories (Easy {tiers[1]}, Medium {tiers[2]}, Hard {tiers[3]}, Expert {tiers[4]}), "
          f"{sum(1 for c in cats if c['set'])} with pictures, {len(meanings)} meanings, {len({c['domain'] for c in cats})} domains; held back: {len(held)}")
    icons = sorted({w['icon'] for c in cats for w in c['words'] if w.get('icon')})
    json.dump(icons, open(os.path.join(HERE, 'pool51_icons.json'), 'w'))
    print(f'{len(icons)} distinct sprites listed in pool/pool51_icons.json')

if __name__ == '__main__':
    main()
