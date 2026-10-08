"""Will it rain today? One TRUE/FALSE per Kalshi KXRAIN city.

THE LOADER (refresh)
Every city Kalshi lists under KXRAIN is read from five public sources, a call
is made, and the result replaces climate.rain_forecast (archived first -- see
store.py). Nothing here needs a credential:

    Kalshi         the markets, their settlement station (rules_primary names
                   it: "at CLIMSY in New Orleans") and their prices
    NWS            the station's observations so far today, its hourly PoP,
                   its gridded QPF and the forecast text
    Open-Meteo     HRRR, NAM, GFS and ECMWF rain for the rest of the day, and
                   the 30-year ERA5 record for the climatology
    weather.com    /kalshi/api/climate/primary -- the settlement source --
                   for the actual outcome of days already archived

HOW A DAY IS COUNTED
As the market settles it: the NWS climate day, which is LOCAL STANDARD TIME
all year. In October Chicago the day runs 1:00 AM CDT to 12:59 AM CDT, so
rain at 12:30 AM CDT belongs to YESTERDAY. weather.com/kalshi agrees (New
Orleans 2026-10-04: 0.59" on both), which is the check this rests on.
A trace is not rain: the market reads "T" as 0.

THE CALL
    already measured >= 0.01" today              TRUE   settled
    HRRR >= 0.01" left AND another model agrees  TRUE   (HRRR leads a split)
    HRRR >= 0.05" left on its own                TRUE   low
    NWS hourly PoP >= 60% AND NWS QPF >= 0.05"   TRUE
    otherwise                                    FALSE
A binary call on a 35% chance is FALSE: it is the likelier side, and the
reasons say so in as many words.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from app.domains.climate import store

logger = logging.getLogger(__name__)

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
NWS = "https://api.weather.gov"
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
ERA5 = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_COM = "https://weather.com/kalshi/api/climate/primary"
SERIES = "KXRAIN"
TICKER_RE = re.compile(r"^KXRAIN-\d{2}[A-Z]{3}\d{2}-[A-Z]{2,6}$")

# api.weather.gov refuses requests without a User-Agent naming the caller.
_UA = {"User-Agent": "vidura36 climate desk (rain forecast)",
       "Accept": "application/geo+json, application/json"}
# weather.com's edge turns away a bare client; a browser UA and the page's
# own referer are all it needs. No cookies: none are required, and a
# browser's session cookies do not belong in this code.
_WC_HEADERS = {"Accept": "*/*", "Referer": "https://weather.com/kalshi",
               "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/154.0.0.0 Safari/537.36")}
MODELS = {"hrrr": "gfs_hrrr", "nam": "ncep_nam_conus",
          "gfs": "gfs_global", "ecmwf": "ecmwf_ifs025"}
MM = 25.4
MEASURABLE = 0.01           # inches
CLIMO_MM = 1.0              # ERA5 wet-day proxy; it drizzles too often at 0.25
CLIMO_WINDOW = 3            # days either side of today, over 30 years

_refresh_lock = threading.Lock()
# One 30-year archive pull at a time: eight at once come back 429.
_climo_lock = threading.Lock()


class RefreshBusy(RuntimeError):
    """A refresh is already running; a second one would race it."""


def _get(url: str, *, params: dict | None = None, headers: dict | None = None,
         timeout: float = 25) -> dict:
    r = requests.get(url, params=params, headers=headers or _UA, timeout=timeout)
    r.raise_for_status()
    return r.json()


# ---- Kalshi ---------------------------------------------------------------

def _dollars(v) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def kalshi_markets() -> dict[str, dict]:
    """Every open KXRAIN market, by ticker, with its settlement station."""
    out: dict[str, dict] = {}
    cursor = None
    while True:
        params = {"series_ticker": SERIES, "status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        d = _get(f"{KALSHI}/markets", params=params, headers={})
        for m in d.get("markets") or []:
            hit = re.search(r"\bat CLI([A-Z]{3})\b", m.get("rules_primary") or "")
            out[m["ticker"]] = {
                "ticker": m["ticker"],
                "code": m["ticker"].rsplit("-", 1)[-1],
                "city": m.get("yes_sub_title") or m.get("title"),
                "station": hit.group(1) if hit else None,
                "yes_bid": _dollars(m.get("yes_bid_dollars")),
                "yes_ask": _dollars(m.get("yes_ask_dollars")),
                "no_bid": _dollars(m.get("no_bid_dollars")),
                "no_ask": _dollars(m.get("no_ask_dollars")),
                "last": _dollars(m.get("last_price_dollars")),
                "volume": _dollars(m.get("volume_fp")),
                "close_time": m.get("close_time"),
                "status": m.get("status"),
            }
        cursor = d.get("cursor")
        if not cursor:
            return out


def market(ticker: str) -> dict:
    """One market, live, for the trade form."""
    d = _get(f"{KALSHI}/markets/{ticker}", headers={})["market"]
    return {"ticker": d["ticker"], "status": d.get("status"),
            "city": d.get("yes_sub_title") or d.get("title"),
            "yes_bid": _dollars(d.get("yes_bid_dollars")),
            "yes_ask": _dollars(d.get("yes_ask_dollars")),
            "no_bid": _dollars(d.get("no_bid_dollars")),
            "no_ask": _dollars(d.get("no_ask_dollars")),
            "last": _dollars(d.get("last_price_dollars")),
            "close_time": d.get("close_time")}


def event_ticker(day: date) -> str:
    return f"{SERIES}-{day:%y}{day.strftime('%b').upper()}{day:%d}"


# ---- the climate day --------------------------------------------------------

def climate_day_start(tz: ZoneInfo, day: date) -> datetime:
    """Midnight LOCAL STANDARD TIME on ``day``, as an aware UTC datetime."""
    noon = datetime(day.year, day.month, day.day, 12, tzinfo=tz)
    std = noon.utcoffset() - (noon.dst() or timedelta(0))
    return datetime(day.year, day.month, day.day,
                    tzinfo=timezone(std)).astimezone(timezone.utc)


def climate_today(tz: ZoneInfo, now_utc: datetime) -> date:
    """Today's climate date: the local date on standard time."""
    noon = now_utc.astimezone(tz)
    std = noon.utcoffset() - (noon.dst() or timedelta(0))
    return now_utc.astimezone(timezone(std)).date()


_P_GROUP = re.compile(r"\sP(\d{4})(?=\s|$)")


def observed_so_far(icao: str, start_utc: datetime) -> tuple[float, bool, list[dict]]:
    """Measurable rain since ``start_utc`` from the hourly METARs' P group.

    Only the routine hourly reports are summed: a SPECI's P group is the
    running total since the last routine one, so adding it double-counts.
    Returns (inches, trace_seen, observations newest first)."""
    d = _get(f"{NWS}/stations/{icao}/observations",
             params={"start": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")})
    obs = [f["properties"] for f in d.get("features") or []]
    total, trace = 0.0, False
    for o in obs:
        raw = o.get("rawMessage") or ""
        ts = datetime.fromisoformat(o["timestamp"])
        if not raw or "SPECI" in raw or not 45 <= ts.minute <= 59:
            continue
        m = _P_GROUP.search(raw)
        if m:
            v = int(m.group(1)) / 100
            total += v
            trace |= v == 0
    return round(total, 2), trace and total == 0, obs


def _val(o: dict, key: str):
    v = (o.get(key) or {}).get("value")
    return v


# ---- the forecast -----------------------------------------------------------

def nws_forecast(lat: float, lon: float, tz: ZoneInfo, now: datetime,
                 day: date) -> dict:
    pt = _get(f"{NWS}/points/{lat:.4f},{lon:.4f}")["properties"]
    hours = _get(pt["forecastHourly"])["properties"]["periods"]
    pops = []
    for h in hours:
        start = datetime.fromisoformat(h["startTime"]).astimezone(tz)
        if start.date() == day and start + timedelta(hours=1) > now:
            pops.append([start.hour, (h.get("probabilityOfPrecipitation") or {}).get("value") or 0])
    qpf = 0.0
    grid = _get(pt["forecastGridData"])["properties"]
    for v in (grid.get("quantitativePrecipitation") or {}).get("values") or []:
        t, dur = v["validTime"].split("/")
        start = datetime.fromisoformat(t).astimezone(tz)
        span = _iso_hours(dur)
        end = start + timedelta(hours=span)
        if end <= now or start.date() != day and end.astimezone(tz).date() != day:
            continue
        # A 6-hour block half gone counts for its remaining half.
        left = (end - max(start, now)).total_seconds() / 3600
        qpf += (v.get("value") or 0) / MM * max(0.0, min(1.0, left / span))
    periods = _get(pt["forecast"])["properties"]["periods"]
    text = next((p["detailedForecast"] for p in periods
                 if datetime.fromisoformat(p["startTime"]).astimezone(tz).date() == day),
                periods[0]["detailedForecast"] if periods else None)
    return {"pops": pops, "max_pop": max((p for _, p in pops), default=0),
            "qpf_in": round(qpf, 2), "text": text}


def _iso_hours(dur: str) -> int:
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?", dur)
    return max(1, int(m.group(1) or 0) * 24 + int(m.group(2) or 0)) if m else 1


def model_rain(lat: float, lon: float, tz_name: str, now: datetime,
               day: date) -> dict:
    """Rain left today per model, inches, and HRRR's own hourly chance.

    Open-Meteo stamps each hour with the hour that ENDS there, so an hour is
    still to come only if its stamp is after now -- the 11:00 value at 11:10
    already happened (or did not)."""
    d = _get(OPEN_METEO, params={
        "latitude": lat, "longitude": lon, "timezone": tz_name,
        "hourly": "precipitation,precipitation_probability",
        "models": ",".join(MODELS.values()), "forecast_days": 2}, headers={})
    hourly = d["hourly"]
    tz = ZoneInfo(tz_name)
    keep = []
    for i, t in enumerate(hourly["time"]):
        end = datetime.fromisoformat(t).replace(tzinfo=tz)
        if end > now and (end - timedelta(minutes=1)).date() == day:
            keep.append(i)
    out: dict = {}
    for name, model in MODELS.items():
        vals = hourly.get(f"precipitation_{model}") or []
        got = [vals[i] for i in keep if i < len(vals) and vals[i] is not None]
        out[name] = round(sum(got) / MM, 2) if got else None
    pops = hourly.get(f"precipitation_probability_{MODELS['hrrr']}") or []
    hp = [pops[i] for i in keep if i < len(pops) and pops[i] is not None]
    out["hrrr_max_pop"] = max(hp) if hp else None
    return out


def climatology(station: str, lat: float, lon: float, day: date) -> float | None:
    """Share of days within three of this date, 1996-2025, with >= 1 mm in
    ERA5. A reanalysis grid, not the gauge: it runs wetter than the station
    record, and the UI says so.

    The 30-year record does not change, so each station is pulled ONCE and
    every date of the year is stored (climate.rain_climatology). Pulled per
    date it cost 30 heavy archive calls a refresh and the archive answered
    429 to a fifth of them."""
    mmdd = day.strftime("%m-%d")
    hit = store.climatology(station, mmdd)
    if hit is not None:
        return hit
    # Waited for briefly, not forever: a refresh is not held hostage to the
    # archive. A station that misses its turn shows "n/a" and is filled next
    # time; once every station is stored this path is never taken.
    if not _climo_lock.acquire(timeout=20):
        return None
    try:
        hit = store.climatology(station, mmdd)
        if hit is not None:
            return hit
        table = _climatology_year(station, lat, lon)
        if table:
            store.save_climatology(station, table)
        return table.get(mmdd)
    finally:
        _climo_lock.release()


def _climatology_year(station: str, lat: float, lon: float) -> dict[str, float]:
    """Every MM-DD's wet-day share for one point. Empty when the archive
    could not be read -- asked again on the next refresh."""
    d = None
    for attempt in range(2):
        try:
            d = _get(ERA5, params={"latitude": lat, "longitude": lon,
                                   "start_date": "1996-01-01", "end_date": "2025-12-31",
                                   "daily": "precipitation_sum", "timezone": "auto"},
                     headers={}, timeout=40)["daily"]
            break
        except Exception as exc:                        # noqa: BLE001
            logger.info("climatology %s (try %d): %s", station, attempt + 1, exc)
            time.sleep(3)
    if d is None:
        return {}
    days = [(date.fromisoformat(t), p) for t, p in zip(d["time"], d["precipitation_sum"])
            if p is not None]
    out: dict[str, float] = {}
    ref = date(2000, 1, 1)                  # a leap year, so Feb 29 has a row
    for k in range(366):
        anchor = ref + timedelta(days=k)
        wet = n = 0
        for x, p in days:
            try:
                a = x.replace(month=anchor.month, day=anchor.day)
            except ValueError:              # Feb 29 asked of a common year
                a = x.replace(month=2, day=28)
            if abs((x - a).days) <= CLIMO_WINDOW:
                n += 1
                wet += p >= CLIMO_MM
        if n:
            out[anchor.strftime("%m-%d")] = round(100 * wet / n, 1)
    return out


# ---- the call -----------------------------------------------------------------

def decide(*, observed: float, trace: bool, hrrr, nam, gfs, ecmwf,
           nws_pop: int, nws_qpf: float, hrrr_pop, hours_left: float) -> tuple[str, str, list[str]]:
    """TRUE/FALSE, a confidence, and the reasons in plain sentences."""
    why: list[str] = []
    fmt = lambda v: "n/a" if v is None else f'{v:.2f}"'         # noqa: E731
    models = {"HRRR": hrrr, "NAM": nam, "GFS": gfs, "ECMWF": ecmwf}
    others_wet = [k for k, v in models.items() if k != "HRRR" and (v or 0) >= MEASURABLE]
    why.append("Models, rain left today: " + ", ".join(f"{k} {fmt(v)}" for k, v in models.items())
               + f". NWS hourly PoP peaks at {nws_pop}%, NWS QPF {nws_qpf:.2f}\".")

    if observed >= MEASURABLE:
        why.insert(0, f'{observed:.2f}" has already been measured on today\'s climate day '
                      f"-- the market settles YES on anything above zero.")
        return "TRUE", "settled", why
    if trace:
        why.insert(0, "Only a trace so far today, which settles as 0.")
    if hours_left <= 0.25:
        why.insert(0, "The climate day is over with nothing measurable.")
        return "FALSE", "high", why

    h = hrrr or 0
    if h >= MEASURABLE and others_wet:
        why.insert(0, f"HRRR shows {h:.2f}\" still to come and {', '.join(others_wet)} agree "
                      f"on measurable rain; HRRR leads when sources split.")
        conf = "high" if nws_pop >= 50 else "medium" if nws_pop >= 25 else "low"
        if conf == "low":
            why.append(f"NWS is far drier at {nws_pop}%, so this is a low-confidence TRUE.")
        return "TRUE", conf, why
    if h >= 0.05:
        why.insert(0, f"HRRR alone shows {h:.2f}\" -- enough to register -- and the "
                      "rule leans on HRRR when the sources disagree.")
        return "TRUE", "low", why
    if nws_pop >= 60 and nws_qpf >= 0.05:
        why.insert(0, f"NWS puts the chance at {nws_pop}% with {nws_qpf:.2f}\" expected, "
                      "even though HRRR is dry.")
        return "TRUE", "medium" if h > 0 else "low", why

    lead = (f"A {nws_pop}% chance is a {100 - nws_pop}% chance of no measurable rain; "
            "the likelier side is FALSE.") if nws_pop >= 20 else \
        f"NWS gives at most {nws_pop}% for the rest of the day."
    if h < MEASURABLE:
        lead += " HRRR, the short-range model, has nothing measurable left."
        if hrrr_pop is not None:
            lead += f" Its own hourly chance peaks at {hrrr_pop}%."
    else:
        lead += f" HRRR's {h:.2f}\" alone is too little to trust over the rest."
    if others_wet:
        lead += f" {', '.join(others_wet)} disagree{'s' if len(others_wet) == 1 else ''} and stay wet."
    why.insert(0, lead)
    wet_votes = len(others_wet) + (h >= MEASURABLE)
    conf = ("high" if nws_pop < 20 and wet_votes == 0
            else "medium" if nws_pop < 40 and wet_votes <= 1 else "low")
    return "FALSE", conf, why


# ---- one city -----------------------------------------------------------------

def _compass(deg) -> str:
    if deg is None:
        return "calm/variable"
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((deg + 22.5) % 360 // 45)]


def analyse(m: dict, now_utc: datetime) -> dict:
    """Everything for one market. A source that fails is recorded in
    ``error`` and the call is still made from what was read."""
    icao = f"K{m['station']}" if m.get("station") else None
    row: dict = {"city_code": m["code"], "city": m["city"], "market_ticker": m["ticker"],
                 "station": m.get("station"), "icao": icao,
                 "kalshi_yes_bid": m.get("yes_bid"), "kalshi_yes_ask": m.get("yes_ask"),
                 "kalshi_last": m.get("last"), "kalshi_volume": m.get("volume"),
                 "loaded_at": now_utc.isoformat(timespec="seconds")}
    errors: list[str] = []
    if not icao:
        row.update(decision="FALSE", confidence="low", forecast_date=now_utc.date().isoformat(),
                   error="no settlement station in the market's rules",
                   reasons=["The market names no station, so nothing could be read."])
        return row
    info = _get(f"{NWS}/stations/{icao}")
    tz_name = info["properties"]["timeZone"]
    tz = ZoneInfo(tz_name)
    lon, lat = info["geometry"]["coordinates"][:2]
    now = now_utc.astimezone(tz)
    day = climate_today(tz, now_utc)
    start = climate_day_start(tz, day)
    end = climate_day_start(tz, day + timedelta(days=1))
    hours_left = (end - now_utc).total_seconds() / 3600
    row.update(time_zone=tz_name, forecast_date=day.isoformat(),
               local_time=now.strftime("%Y-%m-%d %H:%M %Z"))

    observed, trace, obs = 0.0, False, []
    try:
        observed, trace, obs = observed_so_far(icao, start)
    except Exception as exc:                            # noqa: BLE001
        errors.append(f"observations: {type(exc).__name__}")
    latest = obs[0] if obs else {}
    pres = [(_val(o, "barometricPressure"), o["timestamp"]) for o in obs
            if _val(o, "barometricPressure")]
    tend = None
    if len(pres) > 1:
        t0 = datetime.fromisoformat(pres[0][1])
        old = next((p for p in pres if t0 - datetime.fromisoformat(p[1]) >= timedelta(hours=3)),
                   pres[-1])
        tend = round((pres[0][0] - old[0]) / 100, 1)
    wind_kmh = _val(latest, "windSpeed")
    row.update(observed_in=observed, observed_trace=int(trace),
               current_wx=latest.get("textDescription"),
               wind_dir_deg=_val(latest, "windDirection"),
               wind_mph=None if wind_kmh is None else round(wind_kmh / 1.609, 1),
               humidity_pct=None if _val(latest, "relativeHumidity") is None
               else round(_val(latest, "relativeHumidity")),
               pressure_hpa=None if not pres else round(pres[0][0] / 100, 1),
               pressure_tend_hpa=tend)

    fc = {"pops": [], "max_pop": 0, "qpf_in": 0.0, "text": None}
    try:
        fc = nws_forecast(lat, lon, tz, now, now.date())
    except Exception as exc:                            # noqa: BLE001
        errors.append(f"NWS forecast: {type(exc).__name__}")
    mr = {k: None for k in MODELS} | {"hrrr_max_pop": None}
    try:
        mr = model_rain(lat, lon, tz_name, now, now.date())
    except Exception as exc:                            # noqa: BLE001
        errors.append(f"models: {type(exc).__name__}")
    climo = climatology(m["station"], lat, lon, day)
    row.update(nws_max_pop=fc["max_pop"], nws_pops=fc["pops"], nws_qpf_in=fc["qpf_in"],
               nws_forecast=fc["text"], hrrr_in=mr["hrrr"], hrrr_max_pop=mr["hrrr_max_pop"],
               nam_in=mr["nam"], gfs_in=mr["gfs"], ecmwf_in=mr["ecmwf"], climo_pct=climo)

    decision, conf, why = decide(
        observed=observed, trace=trace, hrrr=mr["hrrr"], nam=mr["nam"], gfs=mr["gfs"],
        ecmwf=mr["ecmwf"], nws_pop=fc["max_pop"], nws_qpf=fc["qpf_in"],
        hrrr_pop=mr["hrrr_max_pop"], hours_left=hours_left)
    if m.get("yes_ask") is not None:
        implied = round(100 * ((m.get("yes_bid") or 0) + m["yes_ask"]) / 2)
        lean = "agrees" if (implied >= 50) == (decision == "TRUE") else "DISAGREES"
        why.append(f"Kalshi trades YES around {implied}c, so the market {lean} with this call.")
    if errors:
        why.append("Not read this time: " + "; ".join(errors) + ".")

    row["historical_context"] = (
        f"About {climo:.0f}% of days within {CLIMO_WINDOW} of {day:%b} {day.day} had >= 1 mm "
        f"in the 1996-2025 ERA5 record (a reanalysis; the gauge record runs lower)."
        if climo is not None else "The 30-year record could not be read.")
    tend_txt = ("steady" if tend is None or abs(tend) < 0.5
                else f"{'rising' if tend > 0 else 'falling'} {abs(tend):.1f} hPa/3h")
    row["current_dynamics"] = (
        f"{row['current_wx'] or 'No current report'}; wind {_compass(row['wind_dir_deg'])} "
        f"{row['wind_mph'] if row['wind_mph'] is not None else '?'} mph; humidity "
        f"{row['humidity_pct'] if row['humidity_pct'] is not None else '?'}%; pressure {tend_txt}; "
        + (f'{observed:.2f}" measured so far today.' if observed else
           "a trace so far today." if trace else "nothing measured so far today."))
    wet = [k.upper() for k in MODELS if (mr[k] or 0) >= MEASURABLE]
    row["model_trend"] = (
        f"{'Wet' if wet else 'Dry'} for the rest of the day: "
        + (f"{', '.join(wet)} show measurable rain" if wet else "no model shows measurable rain")
        + f"; NWS hourly PoP peaks at {fc['max_pop']}%"
        + (f", HRRR's own at {mr['hrrr_max_pop']}%." if mr["hrrr_max_pop"] is not None else "."))
    row.update(decision=decision, confidence=conf, reasons=why,
               error="; ".join(errors) or None)
    return row


# ---- actual outcomes --------------------------------------------------------------

def outcomes(day: str) -> dict[str, dict]:
    """What the settlement source reports for ``day``, by station. Stations
    with no report yet are left out, so they are asked again next time."""
    d = _get(WEATHER_COM, params={"date": day}, headers=_WC_HEADERS)
    out: dict[str, dict] = {}
    for r in d.get("results") or []:
        status = r.get("status")
        data = r.get("data") or {}
        station = data.get("stationId") or (r.get("station") or {}).get("cliId")
        if status not in ("official", "revised") or not station:
            continue
        p = data.get("precipitation")
        if p is None:
            continue
        try:
            wet = float(p) > 0              # "T" -> ValueError -> dry
        except (TypeError, ValueError):
            wet = False
        out[station] = {"actual_outcome": "TRUE" if wet else "FALSE",
                        "actual_precip": str(p), "actual_status": status}
    return out


def settle_history(today: str) -> dict:
    """Fill actual_outcome on every archived day that is over and still
    waiting. A day the source has not finalised is tried again next time."""
    settled = {}
    for day in store.unsettled_dates(before=today):
        try:
            settled[day] = store.settle(day, outcomes(day))
        except Exception as exc:                        # noqa: BLE001
            logger.info("rain outcome %s: %s", day, exc)
    return settled


# ---- refresh -----------------------------------------------------------------------

def refresh() -> dict:
    """Read everything, make every call, archive + truncate + load."""
    if not _refresh_lock.acquire(blocking=False):
        raise RefreshBusy("a refresh is already running")
    try:
        now_utc = datetime.now(timezone.utc)
        markets = kalshi_markets()
        # One market per city: the one for the city's own date. Pacific
        # cities are still on yesterday's event after 9 PM Pacific's midnight
        # passes in New York, so the event is chosen per city, not once.
        by_city: dict[str, list[dict]] = {}
        for m in markets.values():
            by_city.setdefault(m["code"], []).append(m)
        chosen = [min(ms, key=lambda m: m["close_time"] or "") for ms in by_city.values()]
        rows, failed = [], []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(analyse, m, now_utc): m for m in chosen}
            for f, m in futures.items():
                try:
                    rows.append(f.result())
                except Exception as exc:                # noqa: BLE001
                    logger.warning("rain %s: %s", m["ticker"], exc)
                    failed.append(m["code"])
        if not rows:
            raise RuntimeError("no city could be analysed -- the table was left as it was")
        loaded = store.truncate_and_load(rows, archived_at=now_utc.isoformat(timespec="seconds"))
        today = min(r["forecast_date"] for r in rows)
        settled = settle_history(today)
        return {"loaded": loaded, "failed": failed, "settled": settled,
                "loaded_at": now_utc.isoformat(timespec="seconds")}
    finally:
        _refresh_lock.release()


# ---- reading (the second service) ------------------------------------------------

def board() -> dict:
    rows = store.forecast_rows()
    hist = {h["city_code"]: h for h in store.history_summary()}
    for r in rows:
        r["history"] = hist.get(r["city_code"])
    return {"rows": rows,
            "loaded_at": max((r["loaded_at"] for r in rows), default=None),
            "true_count": sum(r["decision"] == "TRUE" for r in rows),
            "refreshing": _refresh_lock.locked()}
