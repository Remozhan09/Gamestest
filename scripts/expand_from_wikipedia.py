"""Добавляет игры из Википедии в site/games.json.

Берёт статьи из категорий «Category:YYYY video games» (год первого выхода),
сортирует по просмотрам статьи за 60 дней и добавляет самые популярные,
которых ещё нет в списке. Настройки — data/expand.json:
  {"years": [2004, 2010], "target_total": 2000}
Отчёт пишется в data/expand_report.txt. Повторный запуск с теми же
настройками ничего не делает (метка в data/expand_done.json).
"""
import json, os, re, sys, time
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "data", "expand.json")
DONE = os.path.join(ROOT, "data", "expand_done.json")
REPORT = os.path.join(ROOT, "data", "expand_report.txt")
GAMES = os.path.join(ROOT, "site", "games.json")
API = "https://en.wikipedia.org/w/api.php"
S = requests.Session()
S.headers["User-Agent"] = "GamestestBot/1.0 (https://github.com/Remozhan09/Gamestest; game list builder)"

if not os.path.exists(CFG):
    print("Нет data/expand.json — пропускаю"); sys.exit(0)
cfg = json.load(open(CFG, encoding="utf-8"))
done = json.load(open(DONE, encoding="utf-8")) if os.path.exists(DONE) else []
if cfg in done:
    print("Это расширение уже сделано — пропускаю"); sys.exit(0)

games = json.load(open(GAMES, encoding="utf-8"))
# Пересборка: убираем игры, добавленные прошлым расширением, и выбираем заново
if os.path.exists(REPORT):
    old = {l.rstrip("\n").split("\t")[3] for l in open(REPORT, encoding="utf-8") if l[:1].isdigit()}
    before = len(games)
    games = [g for g in games if g[0] not in old]
    print(f"Убрано прошлых добавлений: {before - len(games)}")
EXCLUDE_CAT = re.compile(r"eroge|pornograph|hentai|bish.jo|adult video game|visual novel|compilation|rom hack|"
                         r"alternate reality|educational|synthesi|science game|typing|art game", re.I)
EXCL_FILE = os.path.join(ROOT, "data", "expand_exclude.txt")
y0, y1 = cfg["years"]
years = list(range(y0, y1 + 1))
need = max(0, cfg["target_total"] - len(games))
print(f"Сейчас игр: {len(games)}, нужно добавить: {need}")
if not need:
    sys.exit(0)


def norm(s, strip_paren=True):
    s = s.lower().replace("&", "and")
    if strip_paren:
        s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^a-z0-9а-яё]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def clean_title(t):
    t = re.sub(r"\s*\((?:\d{4} )?(?:video ?game|game|series)\)$", "", t)
    return t.strip()


existing = [(norm(g[0]), g[1]) for g in games] + [(norm(g[0], False), g[1]) for g in games if "(" in g[0]]
exist_exact = {n for n, _ in existing}
manual = set()
if os.path.exists(EXCL_FILE):
    manual = {norm(l) for l in open(EXCL_FILE, encoding="utf-8") if l.strip() and not l.startswith("#")}


def is_dup(title, year):
    n = norm(title)
    if not n or n in exist_exact or n in manual:
        return True
    if len(n) >= 5:
        for e, ey in existing:
            if len(e) >= 5 and (abs(ey - year) <= 1 or min(len(n), len(e)) >= 10) and (n in e or e in n):
                return True
    return False


def api(params):
    params = dict(params, format="json", formatversion="2")
    out_pages = {}
    while True:
        for attempt in range(5):
            try:
                r = S.get(API, params=params, timeout=30)
                if r.status_code == 429:
                    time.sleep(10); continue
                r.raise_for_status()
                d = r.json(); break
            except Exception as ex:
                print("  повтор:", ex); time.sleep(5)
        else:
            raise RuntimeError("API недоступен")
        for p in d.get("query", {}).get("pages", []):
            cur = out_pages.setdefault(p["pageid"], {"title": p["title"], "views": 0, "cats": []})
            for v in (p.get("pageviews") or {}).values():
                cur["views"] += v or 0
            cur["cats"] += [c["title"] for c in p.get("categories") or []]
        if "continue" not in d:
            return out_pages
        params.update(d["continue"])
        time.sleep(0.2)


cands = {}
for y in years:
    pages = api({"action": "query", "generator": "categorymembers",
                 "gcmtitle": f"Category:{y} video games", "gcmnamespace": 0,
                 "gcmlimit": 50, "prop": "pageviews|categories", "pvipdays": 60,
                 "clshow": "!hidden", "cllimit": "max"})
    lst = []
    for p in pages.values():
        t = p["title"]
        if t.lower().startswith(("list of", "category:")):
            continue
        if any(EXCLUDE_CAT.search(c) for c in p["cats"]):
            continue
        lst.append((p["views"], clean_title(t), y))
    lst.sort(reverse=True)
    cands[y] = lst
    print(f"{y}: в категории {len(lst)} статей")

per_year = need // len(years)
extra = need - per_year * len(years)
added, report = [], []
for i, y in enumerate(years):
    quota = per_year + (1 if i < extra else 0)
    picked = []
    for views, title, yy in cands[y]:
        if len(picked) >= quota:
            break
        if is_dup(title, yy) or any(norm(title) == norm(t) for t, _ in picked):
            continue
        picked.append((title, views))
        existing.append((norm(title), yy)); exist_exact.add(norm(title))
    if picked:
        med = sorted(v for _, v in picked)[len(picked) // 2]
    for title, views in picked:
        odd = views < med * 0.5
        added.append([title, y, 1] if odd else [title, y])
        report.append(f"{y}\t{views}\t{'*' if odd else ' '}\t{title}")

games.extend(added)
json.dump(games, open(GAMES, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
open(REPORT, "w", encoding="utf-8").write(
    f"# Добавлено {len(added)} игр из Википедии ({y0}–{y1}), сортировка по просмотрам за 60 дней\n"
    "# год\tпросмотры\t*=необычная\tназвание\n" + "\n".join(report) + "\n")
done.append(cfg)
json.dump(done, open(DONE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"Добавлено {len(added)}, всего игр: {len(games)}")
