"""Application settings.

Every value can be overridden with a ``TBOT_``-prefixed environment
variable (or the project-root ``.env``), e.g.
``TBOT_DATABASE_PATH=/home/app/data/app.db``. Legacy ``VIDURA_``-prefixed
names are still honoured (see ``get_settings``) so a machine's existing
.env keeps working.

EVERY default path is project-relative and paper-only, so a fresh clone of
this folder runs anywhere with nothing outside it — that is the whole point
of this project. Machine-specific overrides belong in that machine's
``.env`` (see .env.example and README.md).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# <project>/backend/app/core/config.py -> <project>
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TBOT_",
        env_file=str(PROJECT_ROOT / ".env"),
        extra="ignore",
    )

    app_name: str = "Tradier Bot API"
    app_version: str = "1.0.0"
    api_v1_prefix: str = "/api/v1"

    # --- persistence ---------------------------------------------------
    # Portable default: the project's own var/ folder. Deployments that keep
    # the DB elsewhere set TBOT_DATABASE_PATH (see .env / README.md).
    database_path: Path = PROJECT_ROOT / "var" / "app.db"
    # Full SQLAlchemy URL override — set this to run on Postgres in the
    # cloud (e.g. Render/Neon: postgresql+psycopg://user:pw@host/db).
    # Empty = use the SQLite file above.
    database_url_override: str = ""

    # --- cloud profile ---------------------------------------------------
    # True on Render / Cloud Run: there is no bot repo and no place to spawn
    # long-running trading processes, so execution endpoints answer 503 and
    # only the DB-backed read APIs are served. Auto-enabled when the
    # platform sets PORT (Render/Cloud Run both do) unless set explicitly.
    cloud_mode: bool = False

    # --- trading runtime (vendored) --------------------------------------
    # The signal engines and their config live INSIDE this project under
    # runtime/ — nothing is read from the checkouts this was extracted from.
    # Override only if you keep the runtime somewhere else.
    source_repo: Path = PROJECT_ROOT / "runtime"
    # Portable default: a customers/ folder next to the app. Point
    # TBOT_CUSTOMERS_ROOT wherever the secrets folders actually live.
    customers_root: Path = PROJECT_ROOT / "customers"

    # Python used to launch bot-station subprocesses (defaults to this app's
    # own interpreter; the bots only need requests/cryptography, which are
    # installed here).
    bot_python: Path | None = None

    # Python for super_research supervisors/workers (needs yfinance etc.).
    # None -> this API's own interpreter; set TBOT_SUPER_PYTHON to a
    # separate install when the engines' deps live elsewhere. Every call
    # site falls back to sys.executable when the path is missing.
    super_python: Path | None = None

    # Background ingest: continuously mirror every signal the super_research
    # service generates (central ledgers + per-ticker worker CSVs + gex/econ
    # snapshots) into SQLite. Interval matches the supervisors' 60s poll.
    super_auto_sync: bool = True
    super_sync_interval: int = 60

    @property
    def super_dir(self) -> Path:
        return self.source_repo / "super_research"

    # Folder holding levels_watcher.py (SPY/QQQ/SPX level crosses), which
    # the opening-range auto-trader reads. Vendored under runtime/ like
    # everything else. OPTIONAL: when the folder is absent the desk degrades
    # gracefully ("watcher not running").
    #
    # The watcher appends to its own folder's day_trade.csv and dedupes
    # against its own levels_state.json, so exactly ONE instance may run per
    # folder. If this machine also runs the original bot repo's watcher,
    # point TBOT_LEVELS_DIR at that folder rather than running both.
    levels_dir: Path = PROJECT_ROOT / "runtime" / "stock-trade"

    # --- runtime dirs ---------------------------------------------------
    var_dir: Path = PROJECT_ROOT / "var"

    # --- flashAlpha GEX ---------------------------------------------------
    # FREE plan = 5 requests/day TOTAL. The API is now the ONLY fetcher (the
    # FlashAlphaGEX_Daily Windows task was retired 2026-07-28 in favour of
    # the in-process 09:00 CST loop), so it owns the whole budget. Every call
    # is counted in the DB and refused past this cap. Lower it back to 3 if
    # you ever re-create that scheduled task.
    flashalpha_daily_cap: int = 5
    # Daily 09:00 CST snapshot inside the API — the replacement for the
    # FlashAlphaGEX_Daily Windows task. Disable if that task still exists,
    # or both will spend quota.
    gex_daily_enabled: bool = True
    flashalpha_api_key: str = ""  # else read from <source_repo>/super_research/flashalpha.env
    gex_tickers: str = "spy,qqq"

    # --- earnings calendar -------------------------------------------------
    # Keyless (yfinance), so no budget to ration — but a sweep is ~100 HTTP
    # calls, so a background loop keeps the cache warm and requests only ever
    # read it. Disable in tests / air-gapped hosts.
    earnings_enabled: bool = True

    # --- Tradier desk (env: TBOT_TRADIER_*) ------------------------------
    # Position monitor: sweeps managed options positions for buy fills, TP
    # fills and SL breaches. The TP rests on the venue; the SL is THIS loop,
    # so the interval is the SL's reaction time.
    tradier_enabled: bool = True
    tradier_monitor_interval_s: int = 10

    # Desk-wide defaults for the executor (composer + auto-trader fall back
    # to these when a request does not spell its own out).
    tradier_delta_min: float = 0.25
    tradier_delta_max: float = 0.50
    tradier_buy_pct: float = 50.0        # % of option buying power per trade
    # Contracts are indivisible, so buy_pct is a target rather than a cap:
    # the total may land this far either side of it. Without the band a
    # contract priced over the budget sizes to zero and never trades.
    tradier_size_tolerance_pct: float = 25.0
    tradier_tp_pct: float = 15.0         # resting sell above entry
    tradier_sl_pct: float = 30.0         # monitored stop below entry

    # Opening-range auto-trader (the AUTO TRADE button).
    tradier_auto_strategy: str = "10min_intraday_move"
    tradier_auto_tickers: str = "SPY,QQQ,SPX"
    tradier_auto_window_open: str = "08:30"    # CST — crosses before are stale
    tradier_auto_window_close: str = "09:30"   # CST — crosses after are ignored
    tradier_auto_confirm_s: int = 300          # signal must still hold after this
    tradier_auto_poll_s: int = 20              # level-snapshot poll cadence
    tradier_auto_min_contracts: int = 1        # sized below this -> skip trade

    # --- auto-trade: A/B super-signal options strategy -------------------
    # LONG signal -> CALL, SHORT -> PUT. The entry is not taken on the
    # signal itself: the chosen contract's BID is sampled for a while and
    # bought only while it is holding up, never into a fade.
    tradier_ab_books: str = "A,B"              # which super-signal books to act on
    tradier_ab_sample_s: int = 15              # bid sampling cadence
    tradier_ab_observe_min_s: int = 300        # 5m: earliest a decision is made
    tradier_ab_observe_max_s: int = 600        # 10m: end of the first look
    tradier_ab_stable_s: int = 150             # 2.5m trailing window in the rescue phase
    tradier_ab_max_wait_s: int = 1800          # 30m: give up on a fading bid
    tradier_ab_tol_pct: float = 2.0            # move under this is "stable", not a trend
    tradier_ab_dte_max: int = 6                # today .. today+6 expirations
    tradier_ab_zero_dte_cutoff: str = "13:00"  # CST — no 0DTE entry after this
    tradier_ab_cooldown_s: int = 3600          # 60m before this strategy re-enters a ticker

    # --- options flow board (unusual activity across the large caps) ------
    # Streaming carries no open interest, so this is chain data on a timer.
    # One chain call per symbol per expiration: keep the universe and the
    # expiration count honest about what that costs.
    tradier_flow_universe: str = (
        "AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AVGO,LLY,JPM,"
        "V,UNH,XOM,MA,COST,HD,PG,JNJ,ABBV,WMT,"
        "NFLX,BAC,CRM,AMD,KO,PEP,TMO,ADBE,CSCO,MRK,"
        "ORCL,ACN,MCD,ABT,DIS,QCOM,INTC,VZ,TXN,IBM,"
        "PFE,GE,CAT,NOW,UBER,BA,MU,PLTR,COIN,SMCI"
    )
    tradier_flow_expirations: int = 2          # nearest N expirations per symbol
    tradier_flow_top: int = 25                 # contracts shown
    tradier_flow_max_per_ticker: int = 5        # cap per underlying symbol
    tradier_flow_min_volume: int = 100         # ignore untraded contracts
    # Cheap contracts dominate a volume ranking — a 4-cent option trades in
    # enormous size and cannot be managed with a percentage TP. Priced below
    # this, a contract is a lottery ticket, not flow worth acting on.
    tradier_flow_min_price: float = 0.30

    # --- HOT scan (trend strength across the top 100) --------------------
    # Wilder DMI/ADX over the same bars the desk charts draw, so a name that
    # is HOT here shows the matching B marker on its own chart.
    tradier_hot_universe: str = (
        "AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,AVGO,LLY,JPM,"
        "V,UNH,XOM,MA,COST,HD,PG,JNJ,ABBV,WMT,"
        "NFLX,BAC,CRM,AMD,KO,PEP,TMO,ADBE,CSCO,MRK,"
        "ORCL,ACN,MCD,ABT,DIS,QCOM,INTC,VZ,TXN,IBM,"
        "PFE,GE,CAT,NOW,UBER,BA,MU,PLTR,COIN,SMCI,"
        "GS,MS,BLK,SCHW,AXP,C,WFC,SPGI,BX,PGR,"
        "AMAT,LRCX,KLAC,ADI,SNPS,CDNS,MRVL,ARM,DELL,TMUS,"
        "CMCSA,T,LOW,TGT,NKE,SBUX,MDLZ,AMGN,GILD,BMY,"
        "CVS,ELV,ISRG,SYK,VRTX,REGN,CVX,COP,SLB,EOG,"
        "NEE,DUK,UNP,HON,RTX,LMT,DE,GEV,ANET,PANW"
    )
    tradier_hot_interval: str = "5min"    # the desk's default granularity
    # Lookback per interval, tuned so every choice lands on 150-250 regular
    # session bars. The DMI needs 30 to say anything at all, and near that
    # floor the ADX is mostly its own seed — measured against the live venue,
    # where 5min/5d gives 248 RTH bars, 15min/10d 166, 30min/20d 198 and
    # 1h/40d 197. Tradier serves all four natively; none is resampled.
    tradier_hot_days_by_interval: str = "5min:5,15min:10,30min:20,1h:40"
    # The gates, as the desk stated them: a substantial up-move (+DI > 25)
    # that dominates rather than merely leads (+DI >= -DI x 2), inside a real
    # trend (ADX > 34 — well past Wilder's 20-25 "a trend exists" line).
    tradier_hot_min_pdi: float = 25.0
    tradier_hot_di_ratio: float = 2.0
    tradier_hot_min_adx: float = 34.0
    # A sweep is 100 timesales calls, so it runs on a timer rather than on
    # every look: once a snapshot is this old the next request kicks a fresh
    # one off in the background. The desk's own poll is the heartbeat that
    # makes that happen on schedule — it must stay well UNDER this number, or
    # a sweep only starts on the first poll after the snapshot went stale and
    # the data ends up nearly twice this age (user 08/17).
    tradier_hot_ttl_s: int = 900          # 15 minutes

    # --- SUPERHOT scan (the tighter tier above HOT) -------------------------
    # Period-9 DMI halves the lag versus period-14, catching trend onset faster.
    # Five gates, all of which must hold:
    #   1. ADX(9) in [min, max]  — trending but not exhausted
    #   2. ADX slope > 0         — trend is STRENGTHENING, not fading
    #   3. |DXS| >= min_dxs      — directional efficiency (one side dominates)
    #   4. dominant DI > min_pdi  — the winning side is substantial
    #   5. DI ratio >= di_ratio   — and it leads by this factor
    tradier_superhot_di_period: int = 9
    tradier_superhot_adx_period: int = 9
    tradier_superhot_min_adx: float = 20.0
    tradier_superhot_max_adx: float = 50.0
    tradier_superhot_slope_lb: int = 3       # bars for ADX slope lookback
    tradier_superhot_min_dxs: float = 0.35   # |(+DI - -DI)/(+DI + -DI)|
    tradier_superhot_min_pdi: float = 20.0
    tradier_superhot_di_ratio: float = 2.0

    # --- commodities (API Ninjas, off-hours) --------------------------------
    # No default: a secret is never defaulted in source. The value lives in
    # the operator's own credential file (customers/<user>/.env) as
    # APININJAS_API_KEY. Empty here means "not configured".
    #
    # NOTE: nothing in this codebase reads this field today -- see
    # docs/shared/secret-relocation.md. It is kept (empty) rather than
    # deleted so removal goes through the Phase 9 dead-code review.
    apininjas_api_key: str = ""

    # --- exits -----------------------------------------------------------
    # A buy reporting "filled" is not the same as the position being on the
    # books. Selling into that gap is what Tradier rejects, so the exits wait
    # this long AND until the holding is visible before they are armed.
    tradier_fee_per_contract: float = 0.35
    tradier_arm_delay_s: int = 30
    tradier_flow_ttl_s: int = 300              # snapshot age before a refresh
    tradier_flow_workers: int = 6              # parallel chain fetches

    # --- bot station: trade mirror ---------------------------------------
    # Read endpoints refresh the trades table from the bots' CSVs before
    # answering, so an open position shows up without anyone pressing "sync".
    # Disable only if the CSVs live somewhere the API cannot read.
    trades_auto_sync: bool = True

    # --- bot station: reconcile ------------------------------------------
    # Sweep for ledger rows still `open` that the exchange says are finished,
    # and settle them from fills+settlements. Reads Kalshi read-only and never
    # touches a ticker that is still an active position. Off in tests and on
    # hosts with no credentials, where every call would just fail.
    reconcile_enabled: bool = True
    reconcile_interval_s: int = 3600
    # Matches the endpoint default: younger than this and the bot is probably
    # just still holding.
    reconcile_stale_hours: int = 24
    reconcile_fast_interval_s: int = 1800
    reconcile_fast_stale_minutes: int = 30

    # --- safety ---------------------------------------------------------
    # When True (default) bots are always launched in paper/mock mode and
    # order-placing endpoints record trades locally instead of hitting the
    # exchange. Flip to False deliberately, never by accident — the CODE
    # default stays True so a fresh deployment can never go live by surprise;
    # unlock per machine via TBOT_PAPER_ONLY=false in its .env.
    paper_only: bool = True

    # Optional shared API key. When set, a request may authenticate with it
    # in the X-API-Key header INSTEAD of logging in — for scripts and cron,
    # which have no way to type a password. Empty (default) = only login
    # sessions are accepted.
    api_key: str = ""

    # --- desk login (env: TBOT_LOGIN_REQUIRED) ---------------------------
    # Every /api call must carry a session token from POST /auth/login, in
    # the X-API-Key header. The password is the operator's own
    # customers/<username>/.sam - nothing about it lives in this project.
    #
    # ON by default, and that is deliberate: this desk places real options
    # orders, binds 0.0.0.0 so it is reachable across the LAN, and its
    # exposure should not depend on someone remembering to switch a gate on.
    # Turn it off only for a throwaway localhost session.
    login_required: bool = True
    # 12h: long enough for a full trading day without re-typing, short
    # enough that a forgotten browser does not stay live all week. Sessions
    # are in-memory, so a restart ends all of them regardless.
    session_ttl_s: int = 43200

    # Scoped credential for the getgamma.io 0DTE bookmarklet, which runs on
    # someone else's page and so must never carry a key that could trade.
    # Authorises POST /super/gex0dte/refresh and /heartbeat, nothing else.
    # Empty = that feed cannot push while login is required.
    gex_push_token: str = ""

    # By default user_root_folder must live under customers_root so the API
    # cannot be pointed at arbitrary filesystem folders holding secrets.
    allow_any_root: bool = False

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            # Render hands out legacy 'postgres://' URLs; SQLAlchemy 2 needs
            # an explicit driver.
            url = self.database_url_override
            if url.startswith("postgres://"):
                url = "postgresql+psycopg://" + url[len("postgres://"):]
            return url
        return f"sqlite:///{self.database_path.as_posix()}"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def log_dir(self) -> Path:
        return self.var_dir / "logs"


def _bridge_legacy_env() -> None:
    """Accept the old VIDURA_* names for every TBOT_* setting.

    This project was carved out of vidura-world, so a machine that already
    runs that app has VIDURA_* exported or sitting in a .env. Mapping them
    across means an operator never has to migrate anything by hand; an
    explicit TBOT_* always wins.
    """
    import os

    for key, value in list(os.environ.items()):
        if key.startswith("VIDURA_"):
            os.environ.setdefault("TBOT_" + key[len("VIDURA_"):], value)


@lru_cache
def get_settings() -> Settings:
    import os

    _bridge_legacy_env()
    settings = Settings()
    # PORT is injected by Render and Cloud Run; treat that as "cloud" unless
    # the operator said otherwise.
    if "TBOT_CLOUD_MODE" not in os.environ and os.environ.get("PORT"):
        settings.cloud_mode = True
    if settings.cloud_mode:
        # Never auto-ingest from a bot repo that does not exist in a
        # container, and never try to run engines there.
        settings.super_auto_sync = False
        # No credential folders in a container, so every reconcile pass
        # would just log a failure per user.
        settings.reconcile_enabled = False
    if settings.is_sqlite:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # read-only container filesystem
    return settings
