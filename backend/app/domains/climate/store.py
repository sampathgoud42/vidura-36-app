"""The ``climate`` schema: today's rain calls, and every call ever made.

Two tables, the same shape the monitor schema uses (see
app.domains.botstation.monitor for the reasoning):

    Postgres   CREATE SCHEMA climate, tables inside it
    SQLite     a separate file, var/climate.db, attached under that name:

                   ATTACH 'var/climate.db' AS climate;
                   SELECT city, decision FROM climate.rain_forecast;

rain_forecast       one row per city, the latest refresh only. TRUNCATE AND
                    LOAD: every refresh replaces the whole table.
rain_forecast_hist  every row rain_forecast ever held, copied in just before
                    it is replaced, plus what actually happened that day
                    (actual_outcome), filled in once weather.com/kalshi -- the
                    settlement source -- publishes the official report.

The archive, the truncate and the load are ONE transaction. A reader never
sees an empty board, and a refresh that fails halfway leaves yesterday's rows
where they were rather than a table with half the cities in it.
"""

from __future__ import annotations

import json
import threading

from sqlalchemy import create_engine, text

SCHEMA = "climate"
FORECAST = "rain_forecast"
HIST = "rain_forecast_hist"
CLIMO = "rain_climatology"

# Column order is the table's, and the insert's. JSON columns hold lists.
COLUMNS: list[tuple[str, str]] = [
    ("city_code", "TEXT NOT NULL"),         # Kalshi's: NOLA, HOU, ...
    ("city", "TEXT NOT NULL"),
    ("market_ticker", "TEXT"),              # KXRAIN-26OCT05-NOLA
    ("station", "TEXT"),                    # settlement CLI id: MSY
    ("icao", "TEXT"),                       # KMSY
    ("time_zone", "TEXT"),
    ("forecast_date", "TEXT NOT NULL"),     # the city's local date
    ("local_time", "TEXT"),                 # when the call was made, local
    ("decision", "TEXT NOT NULL"),          # TRUE | FALSE
    ("confidence", "TEXT"),                 # settled | high | medium | low
    ("observed_in", "REAL"),                # measurable so far, climate day
    ("observed_trace", "INTEGER"),          # 1 when only a trace so far
    ("nws_max_pop", "INTEGER"),             # highest hourly PoP left today
    ("nws_pops", "TEXT"),                   # JSON [[hour, pop], ...]
    ("nws_qpf_in", "REAL"),
    ("nws_forecast", "TEXT"),               # today's detailed forecast
    ("hrrr_in", "REAL"),                    # model rain left today, inches
    ("hrrr_max_pop", "INTEGER"),
    ("nam_in", "REAL"),
    ("gfs_in", "REAL"),
    ("ecmwf_in", "REAL"),
    ("current_wx", "TEXT"),
    ("wind_dir_deg", "INTEGER"),
    ("wind_mph", "REAL"),
    ("humidity_pct", "INTEGER"),
    ("pressure_hpa", "REAL"),
    ("pressure_tend_hpa", "REAL"),          # change over ~3h, + is rising
    ("climo_pct", "REAL"),                  # wet days near this date, 30y
    ("kalshi_yes_bid", "REAL"),             # dollars
    ("kalshi_yes_ask", "REAL"),
    ("kalshi_last", "REAL"),
    ("kalshi_volume", "REAL"),
    ("historical_context", "TEXT"),
    ("current_dynamics", "TEXT"),
    ("model_trend", "TEXT"),
    ("reasons", "TEXT"),                    # JSON list of sentences
    ("error", "TEXT"),                      # a source that could not be read
    ("loaded_at", "TEXT NOT NULL"),         # the refresh, UTC ISO
]
NAMES = [c for c, _ in COLUMNS]
JSON_COLUMNS = {"nws_pops", "reasons"}

HIST_EXTRA: list[tuple[str, str]] = [
    ("archived_at", "TEXT NOT NULL"),
    ("actual_outcome", "TEXT"),             # TRUE | FALSE, NULL until known
    ("actual_precip", "TEXT"),              # as reported: 0.36, T, 0
    ("actual_status", "TEXT"),              # official | revised | preliminary
    ("correct", "INTEGER"),                 # decision == actual_outcome
]

_engine = None
_lock = threading.Lock()
_ready = False


def _is_sqlite() -> bool:
    from app.core.config import get_settings
    return get_settings().is_sqlite


def engine():
    global _engine
    with _lock:
        if _engine is not None:
            return _engine
        from app.core.config import get_settings

        settings = get_settings()
        if settings.is_sqlite:
            path = settings.var_dir / "climate.db"
            path.parent.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(f"sqlite:///{path.as_posix()}",
                                    connect_args={"check_same_thread": False},
                                    future=True)
        else:
            _engine = create_engine(settings.database_url, future=True)
            with _engine.begin() as cx:
                cx.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
        return _engine


def _q(table: str) -> str:
    """The table as written in SQL here: bare in its own SQLite file,
    schema-qualified on Postgres."""
    return f'"{table}"' if _is_sqlite() else f'"{SCHEMA}"."{table}"'


def ensure_tables() -> None:
    global _ready
    if _ready:
        return
    cols = ",\n".join(f'"{n}" {t}' for n, t in COLUMNS)
    hist_id = ('"hist_id" INTEGER PRIMARY KEY AUTOINCREMENT' if _is_sqlite()
               else '"hist_id" BIGSERIAL PRIMARY KEY')
    extra = ",\n".join(f'"{n}" {t}' for n, t in HIST_EXTRA)
    with engine().begin() as cx:
        cx.execute(text(f"CREATE TABLE IF NOT EXISTS {_q(FORECAST)} (\n{cols},\n"
                        f'PRIMARY KEY ("city_code"))'))
        cx.execute(text(f"CREATE TABLE IF NOT EXISTS {_q(HIST)} (\n{hist_id},\n"
                        f"{cols},\n{extra})"))
        cx.execute(text(f'CREATE INDEX IF NOT EXISTS "ix_{HIST}_day" '
                        f'ON {_q(HIST)} ("forecast_date", "station")'))
        cx.execute(text(f'CREATE TABLE IF NOT EXISTS {_q(CLIMO)} ('
                        f'"station" TEXT NOT NULL, "mmdd" TEXT NOT NULL, '
                        f'"wet_pct" REAL NOT NULL, PRIMARY KEY ("station", "mmdd"))'))
    _ready = True


def _encode(row: dict) -> dict:
    out = {n: row.get(n) for n in NAMES}
    for n in JSON_COLUMNS:
        if out[n] is not None and not isinstance(out[n], str):
            out[n] = json.dumps(out[n])
    return out


def _decode(row) -> dict:
    out = dict(row)
    for n in JSON_COLUMNS:
        if isinstance(out.get(n), str):
            try:
                out[n] = json.loads(out[n])
            except ValueError:
                pass
    return out


def truncate_and_load(rows: list[dict], *, archived_at: str) -> int:
    """Archive what rain_forecast holds, empty it, load ``rows``. One
    transaction: all of it happens or none of it does."""
    ensure_tables()
    names = ", ".join(f'"{n}"' for n in NAMES)
    params = ", ".join(f":{n}" for n in NAMES)
    with engine().begin() as cx:
        cx.execute(text(
            f'INSERT INTO {_q(HIST)} ({names}, "archived_at") '
            f"SELECT {names}, :at FROM {_q(FORECAST)}"), {"at": archived_at})
        # DELETE rather than TRUNCATE: SQLite has no TRUNCATE, and on
        # Postgres a TRUNCATE would take a lock the readers then queue on.
        cx.execute(text(f"DELETE FROM {_q(FORECAST)}"))
        if rows:
            cx.execute(text(f"INSERT INTO {_q(FORECAST)} ({names}) VALUES ({params})"),
                       [_encode(r) for r in rows])
    return len(rows)


def forecast_rows() -> list[dict]:
    ensure_tables()
    with engine().begin() as cx:
        rows = cx.execute(text(
            f'SELECT * FROM {_q(FORECAST)} ORDER BY "city"')).mappings().all()
    return [_decode(r) for r in rows]


def unsettled_dates(before: str) -> list[str]:
    """Days in the archive still waiting for their outcome, oldest first.
    ``before`` is excluded: a day not over yet has no outcome to read."""
    ensure_tables()
    with engine().begin() as cx:
        return [r[0] for r in cx.execute(text(
            f'SELECT DISTINCT "forecast_date" FROM {_q(HIST)} '
            f'WHERE "actual_outcome" IS NULL AND "forecast_date" < :d '
            f'ORDER BY 1'), {"d": before})]


def settle(day: str, outcomes: dict[str, dict]) -> int:
    """Write what happened on ``day`` onto its archived calls.

    ``outcomes`` is keyed by settlement station (MSY) and carries
    actual_outcome / actual_precip / actual_status. A station with no
    official report yet is simply absent and stays NULL for the next try."""
    ensure_tables()
    n = 0
    with engine().begin() as cx:
        for station, o in outcomes.items():
            res = cx.execute(text(
                f'UPDATE {_q(HIST)} SET "actual_outcome" = :out, '
                f'"actual_precip" = :p, "actual_status" = :st, '
                f'"correct" = CASE WHEN "decision" = :out THEN 1 ELSE 0 END '
                f'WHERE "forecast_date" = :d AND "station" = :s'),
                {"out": o["actual_outcome"], "p": o["actual_precip"],
                 "st": o["actual_status"], "d": day, "s": station})
            n += res.rowcount or 0
    return n


def history_summary(limit_days: int = 14) -> list[dict]:
    """Per city: settled calls, how many were right -- the last call made
    each day counts, since that is the one an operator would have traded."""
    ensure_tables()
    with engine().begin() as cx:
        rows = cx.execute(text(f'''
            SELECT h."city_code", h."forecast_date", h."decision",
                   h."actual_outcome", h."actual_precip", h."correct"
            FROM {_q(HIST)} h
            JOIN (SELECT "city_code", "forecast_date", MAX("hist_id") AS hid
                  FROM {_q(HIST)} GROUP BY "city_code", "forecast_date") last
              ON last.hid = h."hist_id"
            ORDER BY h."forecast_date" DESC''')).mappings().all()
    out: dict[str, dict] = {}
    for r in rows:
        c = out.setdefault(r["city_code"], {"settled": 0, "correct": 0, "days": []})
        if len(c["days"]) < limit_days:
            c["days"].append({"date": r["forecast_date"], "decision": r["decision"],
                              "actual": r["actual_outcome"],
                              "precip": r["actual_precip"]})
        if r["actual_outcome"] is not None:
            c["settled"] += 1
            c["correct"] += int(r["correct"] or 0)
    return [{"city_code": k, **v} for k, v in out.items()]


def climatology(station: str, mmdd: str) -> float | None:
    ensure_tables()
    with engine().begin() as cx:
        return cx.execute(text(
            f'SELECT "wet_pct" FROM {_q(CLIMO)} WHERE "station" = :s AND "mmdd" = :d'),
            {"s": station, "d": mmdd}).scalar()


def save_climatology(station: str, table: dict[str, float]) -> None:
    ensure_tables()
    with engine().begin() as cx:
        cx.execute(text(f'DELETE FROM {_q(CLIMO)} WHERE "station" = :s'), {"s": station})
        cx.execute(text(f'INSERT INTO {_q(CLIMO)} ("station", "mmdd", "wet_pct") '
                        f"VALUES (:s, :d, :p)"),
                   [{"s": station, "d": d, "p": p} for d, p in table.items()])
