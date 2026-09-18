#!/usr/bin/env python3
"""Validate generated variant_2 level files the way the game's editor tests do, plus the design rules.

Usage: python3 pool/validate_levels.py <dir with Level_N.json> [--first 51 --last 100] [--control levels.json]
Checks per level: every word unique on the board (the Unity test builds a word->category dictionary and throws on a
repeat), words capitalised, every word has a meaning, chain link words are not spawned, chunk pieces unique, frozen
bubbles are whole spawned words, separator links name faces that exist, mechanics match the control level of the same
number (chunks / separator / frozen), picture share ~30%. Prints a tier/picture/repetition summary.
"""
import argparse, collections, json, os, sys
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.dirname(HERE)
ap=argparse.ArgumentParser(); ap.add_argument('dir'); ap.add_argument('--first',type=int,default=51); ap.add_argument('--last',type=int,default=100)
ap.add_argument('--control',default=os.path.join(ROOT,'levels.json')); ap.add_argument('--prior',default=os.path.join(ROOT,'variant2.json')); a=ap.parse_args()
control={x['n']:x['level'] for x in json.load(open(a.control))}
tiers={}
js=open(os.path.join(ROOT,'pool51.js')).read(); pool51=json.loads(js[js.index('window.POOL_51=')+15:js.index(';\nwindow.MEANINGS_51')])
for e in pool51: tiers[e[0]]=e[2]
import re
h=open(os.path.join(ROOT,'index.html')).read(); i=h.index('const CURATED_POOL=['); seg=h[i+19:h.index('\n',i)].rstrip(';')
for e in json.loads(seg): tiers.setdefault(e[0],e[2])
def mech(L): return (any(w['chunks'] for c in L['categories'] for w in c['words']), bool(L['useBubbleSeparator']), bool(L['frozenBubbles']))
problems=[]; use=collections.Counter(); last={}; gaps=[]; rows=[]
prior=json.load(open(a.prior)) if os.path.exists(a.prior) else {'levels':[]}
for x in prior['levels']:
    if x['n']<a.first:
        for c in x['level']['categories']: use[c['category']]+=1; last[c['category']]=x['n']
prior_use=dict(use)
for n in range(a.first,a.last+1):
    p=os.path.join(a.dir,f'Level_{n}.json')
    if not os.path.exists(p): problems.append(f'L{n}: file missing'); continue
    L=json.load(open(p)); cats=L['categories']; names={c['category'].lower() for c in cats}
    words=[w['fullWord'] for c in cats for w in c['words']]
    dup=[w for w,k in collections.Counter(x.lower() for x in words).items() if k>1]
    if dup: problems.append(f'L{n}: repeated word(s) {dup}')
    for c in cats:
        if len(c['words'])!=4: problems.append(f"L{n}: {c['category']} has {len(c['words'])} words")
        for w in c['words']:
            if not w['fullWord'][0].isupper(): problems.append(f"L{n}: {w['fullWord']} not capitalised")
            if not w.get('meaning'): problems.append(f"L{n}: {c['category']}/{w['fullWord']} has no meaning")
        if c['parentCategory'] and c['parentCategory'].lower() not in names: problems.append(f"L{n}: {c['category']} parent {c['parentCategory']} not on the board")
    spawn=[w['fullWord'] for w in L['allWordEntries']]; spawnset=set(spawn)
    children={c['category'] for c in cats if c['parentCategory']}
    for c in cats:
        for w in c['words']:
            is_link = w['fullWord'] in children and any(ch['category']==w['fullWord'] and ch['parentCategory']==c['category'] for ch in cats)
            if is_link and w['fullWord'] in spawnset: problems.append(f"L{n}: chain link {w['fullWord']} is spawned")
            if not is_link and w['fullWord'] not in spawnset: problems.append(f"L{n}: {w['fullWord']} never spawns")
            if w['fullWord'].lower() in names and not is_link: problems.append(f"L{n}: word {w['fullWord']} equals a category name without being its chain link")
    pieces=[p.lower() for w in L['allWordEntries'] for p in w['chunks']]
    if len(set(pieces))!=len(pieces): problems.append(f'L{n}: duplicate chunk piece {[p for p,k in collections.Counter(pieces).items() if k>1]}')
    clash=[p for p in pieces if p in {x.lower() for x in words}]
    if clash: problems.append(f'L{n}: chunk piece equals a word {clash}')
    chunked={w['fullWord'] for w in L['allWordEntries'] if w['chunks']}
    for f in L['frozenBubbles']:
        if f['word'] not in spawnset: problems.append(f"L{n}: frozen {f['word']} not spawned")
        if f['word'] in chunked: problems.append(f"L{n}: frozen {f['word']} is a split word")
    faces={p for w in L['allWordEntries'] for p in (w['chunks'] or [w['fullWord']])}
    for lw in L['bubbleSeparatorData']['linkedWords']:
        if lw not in faces: problems.append(f'L{n}: separator link {lw} is not a face on the board')
    cm,vm=mech(control[n]),mech(L)
    for k,(cv,vv) in zip(('chunks','separator','frozen'),zip(cm,vm)):
        if cv and not vv: problems.append(f'L{n}: control has {k}, variant does not')
    pics=sum(1 for c in cats if all(w['icon'] for w in c['words'])); mixed=[c['category'] for c in cats if any(w['icon'] for w in c['words']) and not all(w['icon'] for w in c['words']) and not any(ch['parentCategory']==c['category'] for ch in cats)]
    if mixed: problems.append(f'L{n}: partly pictured {mixed}')
    want=max(1,round(0.3*len(cats)))
    t=collections.Counter(tiers.get(c['category'],0) for c in cats)
    for c in cats:
        if c['category'] in last: gaps.append((n-last[c['category']],c['category'],n))
        use[c['category']]+=1; last[c['category']]=n
    rows.append((n,len(cats),len(control[n]['categories']),pics,want,t[1],t[2],t[3],t[4],t[0],sum(1 for c in cats if c['parentCategory']),len(chunked),len(L['frozenBubbles']),int(L['useBubbleSeparator']),len(spawn),L['maxBubblesInScene'],L['moveLimit']))
print('n  cats ctl pics/want  E  M  H  X  ?  chains chunks frozen sep spawn maxB moves')
for r in rows: print(f'{r[0]:<3}{r[1]:>4}{r[2]:>4}{r[3]:>5}/{r[4]:<3}{r[5]:>4}{r[6]:>3}{r[7]:>3}{r[8]:>3}{r[9]:>3}{r[10]:>7}{r[11]:>7}{r[12]:>7}{r[13]:>4}{r[14]:>6}{r[15]:>5}{r[16]:>6}')
new_use=collections.Counter({k:v-prior_use.get(k,0) for k,v in use.items() if v-prior_use.get(k,0)>0})
print(f"\ncategories used in {a.first}-{a.last}: {len(new_use)} distinct for {sum(new_use.values())} slots | from the new pool: {sum(1 for k in new_use if k in {e[0] for e in pool51})}")
print('times used within this range:', dict(sorted(collections.Counter(new_use.values()).items())))
print('total uses across 1-100 :', dict(sorted(collections.Counter(use[k] for k in new_use).items())), '| 3+ uses:', sorted([(k,use[k]) for k in new_use if use[k]>=3],key=lambda x:-x[1])[:20])
print('smallest gaps between repeats:', sorted(gaps)[:12])
print('picture share:', sum(r[3] for r in rows),'/',sum(r[1] for r in rows), f'= {sum(r[3] for r in rows)/sum(r[1] for r in rows):.0%}', '| tier totals E/M/H/X:', [sum(r[i] for r in rows) for i in (5,6,7,8)])
print(f'\n{len(problems)} problem(s)'); [print(' ',p) for p in problems[:60]]
