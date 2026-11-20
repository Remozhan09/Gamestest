"""Собирает плюсы/минусы из data/pc_*.txt в site/proscons.json.
Формат строки: Название|плюс;плюс;плюс|минус;минус  (строки с # — комментарии)"""
import glob, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
titles = {g[0] for g in json.load(open(os.path.join(ROOT, 'site', 'games.json'), encoding='utf-8'))}
out, bad = {}, []
for f in sorted(glob.glob(os.path.join(ROOT, 'data', 'pc_*.txt'))):
    for n, line in enumerate(open(f, encoding='utf-8'), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('|')
        if len(parts) != 3 or parts[0] not in titles:
            bad.append(f'{os.path.basename(f)}:{n}: {parts[0]}'); continue
        p = [x.strip() for x in parts[1].split(';') if x.strip()]
        m = [x.strip() for x in parts[2].split(';') if x.strip()]
        out[parts[0]] = {'p': p, 'm': m}
json.dump(out, open(os.path.join(ROOT, 'site', 'proscons.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f'описаний: {len(out)} из {len(titles)}; ошибок: {len(bad)}')
for b in bad: print('  ', b)
missing = sorted(titles - set(out))
if '-v' in sys.argv: print('нет описания:', missing)
