#!/usr/bin/env python3
"""Bundle the Unity variant_2 level files into variant2.json for the level-generator tool.

The Compare 1-50 tab shows this bundle as the third column ("variant_2 as in Unity") and exports it
byte-for-byte, so the tool always reflects what the game actually loads. Re-run after the levels
change in the game repo, then bump VARIANT2_VERSION in index.html so browsers refetch it.

Usage:
  python3 bundle-variant2.py [--repo ../../bubble-word] [--ref origin/feature/CPBAWG-175-levels] [--levels 1-50]
Reads the files straight from git (the game checkout can be on any branch).
"""
import argparse, json, os, subprocess

def git(repo, *args):
    return subprocess.check_output(['git', '-C', repo, *args]).decode()

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default=os.path.join(here, '..', '..', 'bubble-word'))
    ap.add_argument('--ref', default='origin/feature/CPBAWG-175-levels')
    ap.add_argument('--levels', default='1-50')
    ap.add_argument('--out', default=os.path.join(here, 'variant2.json'))
    a = ap.parse_args()
    first, _, last = a.levels.partition('-')
    path = 'Assets/Resources/LevelSets/variant_2'
    levels = []
    for n in range(int(first), int(last or first) + 1):
        raw = git(a.repo, 'show', f'{a.ref}:{path}/Level_{n}.json')
        levels.append({'n': n, 'level': json.loads(raw)})
    source = {
        'repo': 'chardonnay-partners/bubble-word',
        'branch': a.ref.split('/', 1)[1] if a.ref.startswith('origin/') else a.ref,
        'commit': git(a.repo, 'rev-parse', '--short', a.ref).strip(),
        'date': git(a.repo, 'log', '-1', '--format=%cs', a.ref).strip(),
        'path': path,
    }
    with open(a.out, 'w') as f:
        json.dump({'source': source, 'levels': levels}, f, separators=(',', ':'), ensure_ascii=False)
    print(f"wrote {a.out}: {len(levels)} levels from {a.ref} @ {source['commit']} ({source['date']})")

if __name__ == '__main__':
    main()
