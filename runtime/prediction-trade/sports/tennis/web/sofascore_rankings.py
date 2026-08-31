#!/usr/bin/env python3
"""
sofascore_rankings.py — daily ATP/WTA/ITF tennis rankings scraper.
==================================================================
Scrapes https://www.sofascore.com/tennis/rankings/atp and /wta with Playwright
(headless Chromium) AND the ITF World Tennis Tour rankings (men + women) via
ITF's own public JSON API, then writes one clean CSV for the Kalshi sports bot.

ITF (07/10): the ITF pages render their table from a client-side widget, but
ITF also exposes the same data at a plain JSON endpoint
(``/tennis/api/PlayerRankApi/GetPlayerRankings?circuitCode=MT|WT&matchTypeCode=S``)
— fetched directly (no browser). MT = men's world tennis tour, WT = women's;
both are written with ``tour="ITF"``. ATP/WTA rows are written FIRST so that a
player who also holds an ITF rank resolves to their WTA/ATP entry (the bot's
loaders keep the first occurrence, and WTA/ATP outranks ITF for the favorite).

HOW IT WORKS
    SofaScore is a Next.js app that SERVER-RENDERS the rankings into the page's
    ``window.__NEXT_DATA__`` (its JSON API 403s to programmatic requests behind
    Cloudflare).  So we open the real page in a headless browser (passes the bot
    check) and read ``…pageProps.initialRankingsData.rankingRows`` — clean JSON
    with rank / player / country / points — instead of scraping obfuscated DOM.
    Fallback: a best-effort DOM scrape if that embedded data is ever missing.

OUTPUT  tennis_rankings.csv  columns: tour, rank, player, country, points
ARCHIVE Each run also copies the CSV to archive_data/tennis_rankings_MMDDYYYY.csv
        (same-day reruns overwrite that day's file); archives older than 15 days
        are deleted automatically.

INSTALL
    pip install playwright
    playwright install chromium          # one-time browser download

RUN
    python tennis/web/sofascore_rankings.py            # both ATP + WTA
    python tennis/web/sofascore_rankings.py atp        # one tour
    SOFA_HEADLESS=FALSE python tennis/web/sofascore_rankings.py   # debug (headful)

    Daily cron (Windows Task Scheduler / cron): just run the command above once
    a day; the CSV is overwritten each run.

ENV (all optional)
    SOFA_OUTPUT, SOFA_HEADLESS(TRUE), SOFA_NAV_TIMEOUT_MS(45000),
    SOFA_DATA_WAIT_S(20), SOFA_RETRIES(3), SOFA_UA,
    SOFA_ARCHIVE_DIR(<output dir>/archive_data), SOFA_ARCHIVE_DAYS(15)
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
BASE = "https://www.sofascore.com"
TOURS = ("ATP", "WTA", "ITF")

# ITF World Tennis Tour rankings — public JSON API (no browser/token needed).
# circuitCode: MT = men's, WT = women's; matchTypeCode S = singles. Both feed
# tour="ITF". Depth default 500/gender to mirror the ATP/WTA CSV depth.
ITF_API = "https://www.itftennis.com/tennis/api/PlayerRankApi/GetPlayerRankings"
ITF_CIRCUITS = (
    ("MT", "https://www.itftennis.com/en/rankings/mens-world-tennis-tour-rankings/"),
    ("WT", "https://www.itftennis.com/en/rankings/womens-world-tennis-tour-rankings/"),
)
ITF_TAKE = int(os.getenv("SOFA_ITF_TAKE", "500"))
ITF_TIMEOUT_S = float(os.getenv("SOFA_ITF_TIMEOUT_S", "30"))

UA = os.getenv("SOFA_UA",
               "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADLESS = os.getenv("SOFA_HEADLESS", "TRUE").strip().upper() != "FALSE"
OUTPUT = Path(os.getenv("SOFA_OUTPUT", str(_HERE / "tennis_rankings.csv")))
NAV_TIMEOUT = int(os.getenv("SOFA_NAV_TIMEOUT_MS", "45000"))
DATA_WAIT_S = float(os.getenv("SOFA_DATA_WAIT_S", "20"))
RETRIES = int(os.getenv("SOFA_RETRIES", "3"))

# Daily archive: ./archive_data/tennis_rankings_MMDDYYYY.csv, kept N days.
ARCHIVE_DIR = Path(os.getenv("SOFA_ARCHIVE_DIR", str(OUTPUT.parent / "archive_data")))
ARCHIVE_RETENTION_DAYS = int(os.getenv("SOFA_ARCHIVE_DAYS", "15"))

CSV_COLS = ["tour", "rank", "player", "country", "points"]

# Ad / analytics hosts and heavy resources to block (speed + avoid ad overlays).
_AD_HOSTS = ("doubleclick", "googlesyndication", "adservice", "amazon-adsystem",
             "adnxs", "taboola", "outbrain", "scorecardresearch", "quantserve",
             "hotjar", "sentry", "googletagmanager", "google-analytics",
             "facebook", "pubmatic", "rubiconproject", "criteo")
_BLOCK_TYPES = {"image", "media", "font"}


# ── data cleaning + parsing ───────────────────────────────────────────────────
def _to_int(v) -> Optional[int]:
    """'11,830' / ' 5 ' / 5.0 → int; junk → None."""
    if v is None:
        return None
    try:
        return int(float(str(v).replace(",", "").replace(" ", "").strip()))
    except (TypeError, ValueError):
        return None


def parse_rankings_json(data: dict, tour: str) -> list[dict]:
    """SofaScore ``{"rankings":[{ranking,points,team:{name,country}}...]}`` → rows."""
    rows: list[dict] = []
    seen: set = set()
    for e in (data.get("rankings") or []):
        team = e.get("team") or {}
        name = (team.get("name") or e.get("name") or "").strip()
        if not name:
            continue
        rank = _to_int(e.get("position") if e.get("position") is not None
                       else e.get("ranking") if e.get("ranking") is not None
                       else team.get("ranking"))
        points = _to_int(e.get("points"))
        ctry = team.get("country") or {}
        country = ((ctry.get("name") or ctry.get("alpha2") or "").strip()
                   if isinstance(ctry, dict) else "")
        key = (tour, rank, name)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"tour": tour, "rank": rank, "player": name,
                     "country": country, "points": points})
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 10 ** 9))
    return rows


# ── ITF World Tennis Tour (public JSON API; no browser) ───────────────────────
def parse_itf_json(data: dict) -> list[dict]:
    """ITF ``{"items":[{rank, playerGivenName, playerFamilyName, ...}]}`` → rows
    (all tagged tour="ITF")."""
    rows: list[dict] = []
    seen: set = set()
    for it in (data.get("items") or []):
        if it.get("hiddenPlayer"):
            continue
        given = (it.get("playerGivenName") or "").strip()
        family = (it.get("playerFamilyName") or "").strip()
        name = f"{given} {family}".strip()
        rank = _to_int(it.get("rank"))
        if not name or rank is None:
            continue
        key = (rank, name)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "tour": "ITF", "rank": rank, "player": name,
            "country": (it.get("playerNationality")
                        or it.get("playerNationalityCode") or "").strip(),
            "points": _to_int(it.get("points")),
        })
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 10 ** 9))
    return rows


def fetch_itf_circuit(circuit: str, referer: str, take: int) -> list[dict]:
    """Fetch one ITF circuit (MT men / WT women) singles rankings via the public
    JSON API. Synchronous (fast, no browser); raises on HTTP/JSON failure."""
    url = (f"{ITF_API}?circuitCode={circuit}&matchTypeCode=S"
           f"&take={take}&skip=0&isOrderAscending=true")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest", "Referer": referer})
    with urllib.request.urlopen(req, timeout=ITF_TIMEOUT_S) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    return parse_itf_json(data)


async def fetch_itf(take: int = ITF_TAKE) -> list[dict]:
    """Both ITF circuits (men + women singles) as tour="ITF" rows. Runs the
    blocking HTTP calls in a thread so it composes with the async pipeline."""
    loop = asyncio.get_event_loop()
    out: list[dict] = []
    for circuit, referer in ITF_CIRCUITS:
        try:
            rows = await loop.run_in_executor(None, fetch_itf_circuit, circuit, referer, take)
            print(f"[ITF/{circuit}] scraped {len(rows)} players")
            out.extend(rows)
        except Exception as e:
            print(f"[ITF/{circuit}] error: {e}", file=sys.stderr)
    return out


# ── browser helpers ───────────────────────────────────────────────────────────
async def _block_junk(page) -> None:
    """Abort ads/trackers and heavy media so the table loads fast and clean."""
    async def handler(route):
        req = route.request
        url = req.url.lower()
        try:
            if req.resource_type in _BLOCK_TYPES or any(h in url for h in _AD_HOSTS):
                await route.abort()
            else:
                await route.continue_()
        except Exception:
            pass
    await page.route("**/*", handler)


async def _scrape_dom(page, tour: str) -> list[dict]:
    """Last-resort DOM scrape (country left blank; verify quality if used)."""
    rows: list[dict] = []
    try:
        await page.wait_for_selector("a[href*='/player/']", timeout=15000)
    except Exception:
        print(f"[{tour}] DOM fallback: rankings table not found", file=sys.stderr)
        return rows
    links = await page.query_selector_all("a[href*='/player/']")
    seen: set = set()
    for a in links:
        name = ((await a.inner_text()) or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            row = await a.evaluate_handle("el => el.closest('li,tr,[class]')")
            txt = (await row.inner_text()) if row else name
        except Exception:
            txt = name
        nums = re.findall(r"\d[\d,]*", txt.replace(name, ""))
        rows.append({
            "tour": tour,
            "rank": _to_int(nums[0]) if nums else None,
            "player": name, "country": "",
            "points": _to_int(nums[-1]) if len(nums) >= 2 else None,
        })
    print(f"[{tour}] DOM fallback scraped {len(rows)} players (verify quality)",
          file=sys.stderr)
    return rows


_RANKING_ROWS_JS = """() => {
  try {
    const r = window.__NEXT_DATA__?.props?.pageProps?.initialRankingsData?.rankingRows;
    return (Array.isArray(r) && r.length) ? r : null;
  } catch (e) { return null; }
}"""


async def fetch_tour(context, tour: str) -> list[dict]:
    """
    Open the tour's rankings page and return cleaned rows.

    SofaScore is a Next.js app that server-renders the rankings into
    ``window.__NEXT_DATA__.props.pageProps.initialRankingsData.rankingRows`` —
    read that directly (the JSON API itself 403s to programmatic requests).
    Falls back to a best-effort DOM scrape if the embedded data is missing.
    """
    page = await context.new_page()
    await _block_junk(page)
    url = f"{BASE}/tennis/rankings/{tour.lower()}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        # explicit wait for the embedded rankings data to be present
        loop = asyncio.get_event_loop()
        deadline = loop.time() + DATA_WAIT_S
        ranking_rows = None
        while loop.time() < deadline:
            ranking_rows = await page.evaluate(_RANKING_ROWS_JS)
            if ranking_rows:
                break
            await page.wait_for_timeout(400)

        if ranking_rows:
            rows = parse_rankings_json({"rankings": ranking_rows}, tour)
            print(f"[{tour}] scraped {len(rows)} players")
            return rows

        print(f"[{tour}] embedded rankings not found — trying DOM fallback…",
              file=sys.stderr)
        return await _scrape_dom(page, tour)
    finally:
        await page.close()


# ── orchestration ─────────────────────────────────────────────────────────────
def write_csv(rows: list[dict]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in CSV_COLS})
    print(f"[OK] wrote {len(rows)} rows -> {OUTPUT}")


def _existing_rows_for_tour(tour: str) -> list[dict]:
    """Rows for ``tour`` from the CSV already on disk — used as a fallback so a
    temporary SofaScore block doesn't wipe ATP/WTA (we keep last-known values
    and still refresh the tours that succeeded)."""
    if not OUTPUT.exists():
        return []
    out: list[dict] = []
    try:
        with open(OUTPUT, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if (r.get("tour") or "").strip().upper() == tour.upper():
                    out.append({k: r.get(k) for k in CSV_COLS})
    except Exception:
        pass
    return out


def archive_and_prune() -> None:
    """
    Copy today's CSV to ``archive_data/tennis_rankings_MMDDYYYY.csv`` (same-day
    reruns overwrite that day's file), then delete archives older than
    ``ARCHIVE_RETENTION_DAYS`` days.
    """
    if not OUTPUT.exists():
        return
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%m%d%Y")
    dest = ARCHIVE_DIR / f"tennis_rankings_{stamp}.csv"
    try:
        shutil.copyfile(OUTPUT, dest)                 # overwrites if same day
        print(f"[ARCHIVE] saved {dest}")
    except Exception as e:
        print(f"[ARCHIVE] copy failed: {e}", file=sys.stderr)
        return

    today = datetime.now().date()
    for f in ARCHIVE_DIR.glob("tennis_rankings_*.csv"):
        m = re.match(r"tennis_rankings_(\d{8})\.csv$", f.name)
        if not m:
            continue
        try:
            d = datetime.strptime(m.group(1), "%m%d%Y").date()
        except ValueError:
            continue
        if (today - d).days > ARCHIVE_RETENTION_DAYS:
            try:
                f.unlink()
                print(f"[ARCHIVE] removed old {f.name}")
            except Exception as e:
                print(f"[ARCHIVE] could not remove {f.name}: {e}", file=sys.stderr)


async def run(tours: Optional[list[str]] = None) -> int:
    tours = tours or list(TOURS)
    browser_tours = [t for t in tours if t in ("ATP", "WTA")]   # SofaScore/Playwright
    want_itf = "ITF" in tours                                    # ITF public JSON API

    # ATP/WTA rows are written BEFORE ITF so a dual-ranked player resolves to
    # their WTA/ATP entry (loaders keep the first occurrence).
    all_rows: list[dict] = []

    if browser_tours:
        # Lazy import so ITF-only runs / parse helpers work without Playwright.
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("[ERROR] Playwright not installed (needed for ATP/WTA). Run:\n"
                  "    pip install playwright && playwright install chromium",
                  file=sys.stderr)
            if not want_itf:
                return 2
            print("[WARN] continuing with ITF only", file=sys.stderr)
            browser_tours = []

    empty_browser_tours: list[str] = []
    if browser_tours:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=HEADLESS,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
            context = await browser.new_context(
                user_agent=UA, locale="en-US", viewport={"width": 1366, "height": 900},
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
            try:
                for tour in browser_tours:
                    rows: list[dict] = []
                    for attempt in range(1, RETRIES + 1):
                        try:
                            rows = await fetch_tour(context, tour)
                            if rows:
                                break
                            print(f"[{tour}] attempt {attempt}/{RETRIES}: 0 rows, retrying…",
                                  file=sys.stderr)
                        except Exception as e:
                            print(f"[{tour}] attempt {attempt}/{RETRIES} error: {e}",
                                  file=sys.stderr)
                        await asyncio.sleep(2 * attempt)
                    if not rows:
                        # SofaScore block: reuse last-known rows so ATP/WTA is
                        # never wiped — the other tours (incl. ITF) still refresh.
                        rows = _existing_rows_for_tour(tour)
                        if rows:
                            print(f"[{tour}] scrape failed — kept {len(rows)} existing "
                                  f"rows from the CSV", file=sys.stderr)
                        else:
                            empty_browser_tours.append(tour)
                    all_rows.extend(rows)
            finally:
                await context.close()
                await browser.close()

    if want_itf:
        all_rows.extend(await fetch_itf())

    if empty_browser_tours:
        print(f"[WARN] {'/'.join(empty_browser_tours)} returned 0 rows and no existing "
              f"rows to fall back on", file=sys.stderr)

    if not all_rows:
        print("[ERROR] no rankings scraped (Cloudflare block? try SOFA_HEADLESS=FALSE)",
              file=sys.stderr)
        return 1
    write_csv(all_rows)
    archive_and_prune()
    return 0


def main() -> None:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sel = [t.strip().upper() for t in sys.argv[1:] if t.strip()]
    sel = ["WTA" if t in ("WTP", "WTA") else t for t in sel]   # accept the WTP typo
    tours = [t for t in sel if t in TOURS] or list(TOURS)       # ATP / WTA / ITF
    sys.exit(asyncio.run(run(tours)))


if __name__ == "__main__":
    main()
