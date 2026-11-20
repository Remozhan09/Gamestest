"""Находит YouTube-ролики для игр из site/games.json и site/specials.json.

Результат: site/videos.json = {"Название игры": {"t": "<id трейлера>", "s": "<id особой сцены>"}}
- Ищет через yt-dlp (поиск YouTube, без скачивания).
- Берёт первый ролик, который разрешено встраивать (проверка через oEmbed).
- Уже найденные ID не ищет повторно, поэтому скрипт можно запускать много раз.
"""
import json, os, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import yt_dlp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
OUT = os.path.join(SITE, "videos.json")
BUDGET_MIN = float(os.environ.get("BUDGET_MIN", "300"))   # сколько минут максимум
WORKERS = int(os.environ.get("WORKERS", "6"))

games = json.load(open(os.path.join(SITE, "games.json"), encoding="utf-8"))
specials = json.load(open(os.path.join(SITE, "specials.json"), encoding="utf-8"))
videos = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
lock = threading.Lock()
start = time.time()
session = requests.Session()
session.headers["User-Agent"] = "Mozilla/5.0"
YDL_OPTS = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}


def embeddable(vid):
    try:
        r = session.get("https://www.youtube.com/oembed",
                        params={"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"}, timeout=15)
        return r.status_code == 200
    except Exception:
        return False


def search(query, max_dur=1200):
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(f"ytsearch6:{query}", download=False)
    for e in (info or {}).get("entries") or []:
        vid, dur = e.get("id"), e.get("duration")
        if not vid or len(vid) != 11:
            continue
        if dur and dur > max_dur:          # пропускаем многочасовые прохождения
            continue
        if embeddable(vid):
            return vid
    return None


def task(title, year, kind):
    if kind == "t":
        queries = [f"{title} {year} official trailer", f"{title} trailer", f"{title} gameplay"]
        max_dur = 1200
    else:
        queries = [specials[title][1]]
        max_dur = 2400
    for q in queries:
        for attempt in range(2):
            try:
                vid = search(q, max_dur)
                if vid:
                    return title, kind, vid
                break
            except Exception as ex:
                print(f"  ! {title}: {ex}", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
    return title, kind, None


def save():
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, OUT)


jobs = []
for g in games:
    title, year = g[0], g[1]
    v = videos.get(title, {})
    if not v.get("t"):
        jobs.append((title, year, "t"))
    if title in specials and not v.get("s"):
        jobs.append((title, year, "s"))

print(f"Нужно найти: {len(jobs)} роликов, уже есть: {sum(1 for v in videos.values() if v.get('t'))}")
found = miss = 0
with ThreadPoolExecutor(WORKERS) as pool:
    futs = [pool.submit(task, *j) for j in jobs]
    for i, f in enumerate(as_completed(futs), 1):
        title, kind, vid = f.result()
        with lock:
            if vid:
                videos.setdefault(title, {})[kind] = vid
                found += 1
            else:
                miss += 1
            if i % 25 == 0:
                save()
                print(f"[{i}/{len(jobs)}] найдено {found}, не найдено {miss}, {int(time.time()-start)} c")
        if (time.time() - start) / 60 > BUDGET_MIN:
            print("Лимит времени, сохраняю и выхожу")
            for x in futs:
                x.cancel()
            break
save()
total = sum(1 for v in videos.values() if v.get("t"))
print(f"Готово: найдено {found}, не найдено {miss}. Всего с трейлером: {total} из {len(games)}")
