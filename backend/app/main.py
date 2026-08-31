"""Tradier Bot API — FastAPI application factory.

Run locally:
    .venv\\Scripts\\uvicorn app.main:app --host 0.0.0.0 --port 8790

Interactive docs:
    Swagger UI  http://127.0.0.1:8790/docs
    ReDoc       http://127.0.0.1:8790/redoc
    OpenAPI     http://127.0.0.1:8790/openapi.json
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse, Response

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def _run_super_sync() -> dict:
    """One forced-off (incremental) ingest pass in a worker thread."""
    from app.core.database import SessionLocal
    from app.services import super_research as svc

    db = SessionLocal()
    try:
        return svc.sync_everything(db, include_archive=True, force=False)
    finally:
        db.close()


async def _super_sync_loop(interval: int) -> None:
    """Continuously mirror every super_research signal into SQLite so the
    DB is the durable record even if nobody ever calls /super/sync."""
    from app.services import super_research as svc

    log = logging.getLogger("app.super_sync")
    svc.AUTO_SYNC_STATUS.update(enabled=True, interval_s=interval)
    await asyncio.sleep(5)  # let startup settle before the first pass
    while True:
        try:
            result = await asyncio.to_thread(_run_super_sync)
            svc.AUTO_SYNC_STATUS.update(
                runs=svc.AUTO_SYNC_STATUS["runs"] + 1,
                last_run_at=datetime.now(timezone.utc).isoformat(),
                last_result=result,
            )
            new = (result.get("signals", {}).get("inserted", 0) or 0) + (
                result.get("workers", {}).get("inserted", 0) or 0
            )
            if new:
                log.info("auto-sync stored %s new signal(s)", new)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # keep the loop alive on any single failure
            svc.AUTO_SYNC_STATUS.update(
                errors=svc.AUTO_SYNC_STATUS["errors"] + 1, last_error=str(exc)
            )
            log.warning("auto-sync pass failed: %s", exc)
        await asyncio.sleep(interval)


# This project's own folder: used to tell our uvicorn processes apart
# from any other app on the machine launched the same way, and to
# locate the built desk.
# <project>/backend/app/main.py -> <project>
_PROJECT_ROOT_PATH = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = str(_PROJECT_ROOT_PATH)


def _warn_on_duplicate_server(port: int) -> None:
    """A second uvicorn on the same port fails to bind but keeps running its
    background loops — that happened here and pegged the CPU. Shout early."""
    try:
        import psutil  # local-runtime only; absent in the cloud image

        me = os.getpid()
        others = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if proc.info["pid"] == me:
                    continue
                if not (proc.info.get("name") or "").lower().startswith("python"):
                    continue
                cmd = " ".join(proc.cmdline())
                if (
                    "uvicorn" in cmd
                    and "app.main:app" in cmd
                    and _PROJECT_ROOT in cmd.replace("/", os.sep)
                ):
                    others.append(proc.info["pid"])
            except psutil.Error:
                continue
        if others:
            logging.getLogger("app").warning(
                "Another Tradier Bot API process is already running (pid %s). Two servers "
                "double every background loop — stop the old one.", others
            )
    except Exception:  # never block startup on a diagnostic
        pass


def _run_gex_refresh() -> dict:
    from app.core.database import SessionLocal
    from app.services import gex as gex_svc

    db = SessionLocal()
    try:
        return gex_svc.refresh(db)
    finally:
        db.close()


async def _gex_daily_loop() -> None:
    """Daily GEX snapshot at 09:00 CST — the in-process replacement for the
    FlashAlphaGEX_Daily scheduled task. Fires once per calendar day (CST);
    a restart after 09:00 catches up the same day if it has not run yet."""
    from zoneinfo import ZoneInfo

    from app.core.database import SessionLocal
    from app.services import gex as gex_svc

    log = logging.getLogger("app.gex_daily")
    cst = ZoneInfo("America/Chicago")
    while True:
        try:
            now = datetime.now(cst)
            db = SessionLocal()
            try:
                already = gex_svc.quota_state(db)["used_by_api"] > 0
                snap = gex_svc.latest_gex_date(db)
            finally:
                db.close()
            due = now.hour >= 9 and snap != now.date().isoformat() and not already
            if due:
                result = await asyncio.to_thread(_run_gex_refresh)
                log.info(
                    "daily GEX snapshot: %s call(s), stale=%s",
                    result["calls_made"], result["gex"]["stale"],
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logging.getLogger("app.gex_daily").warning("daily GEX pass failed: %s", exc)
        await asyncio.sleep(600)  # re-check every 10 minutes


async def _earnings_warm_loop() -> None:
    """Keep the earnings sweep warm.

    A cold sweep is ~100 yfinance calls (~45s) — far past any browser client's
    timeout — so the endpoint must always be answering from cache. This warms
    it shortly after boot and then tops it up well inside the 12h staleness
    window. Keyless, so unlike GEX there is no budget to ration.
    """
    from app.core.database import SessionLocal
    from app.services import earnings as earnings_svc

    log = logging.getLogger("app.earnings")
    await asyncio.sleep(20)  # let startup settle; this is not urgent
    while True:
        try:
            def _sweep() -> dict:
                db = SessionLocal()
                try:
                    return earnings_svc.get_earnings(db, hours=48)
                finally:
                    db.close()

            payload = await asyncio.to_thread(_sweep)
            log.info(
                "earnings cache warm: %s print(s) in 48h%s",
                payload["count"], " (cached)" if payload.get("cached") else "",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("earnings warm failed: %s", exc)
        await asyncio.sleep(6 * 3600)  # half the staleness window


def _run_reconcile(hours: int) -> list[dict]:
    """One reconcile pass per user, in a worker thread."""
    from app.core.database import SessionLocal
    from app.models import User
    from app.services import reconcile as rec

    out = []
    db = SessionLocal()
    try:
        for user in db.query(User).all():
            try:
                out.append(rec.reconcile(db, user, hours=hours, dry_run=False))
            except rec.ReconcileError as exc:
                # No credentials, or Kalshi unreachable. Expected on hosts
                # without a funded account — never a reason to kill the loop.
                out.append({"user": user.username, "error": str(exc)})
            except Exception as exc:              # noqa: BLE001
                # An API blip mid-pass must not starve the REMAINING users;
                # per-row commits inside reconcile keep finished work.
                logging.getLogger("app.reconcile").warning(
                    "reconcile failed for %s: %s", user.username, exc)
                out.append({"user": user.username, "error": str(exc)})
    finally:
        db.close()
    return out


async def _reconcile_loop(interval: int, hours: int) -> None:
    """Settle rows the exchange has finished but the bot never closed.

    A bot can miss its own exit — it crashes mid-close, or the market settles
    between cycles — leaving a row `open` forever with its cost booked and no
    P&L. Hourly is plenty: the rows this catches have already been stranded
    for a day, and each pass costs one positions call plus a few fills reads.
    """
    log = logging.getLogger("app.reconcile")
    await asyncio.sleep(45)  # let startup and the first CSV sync settle
    while True:
        try:
            for result in await asyncio.to_thread(_run_reconcile, hours):
                if result.get("error"):
                    log.debug("reconcile skipped: %s", result["error"])
                elif result.get("updated"):
                    log.info("reconcile settled %s stranded row(s) from the exchange",
                             result["updated"])
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # keep the loop alive on any single failure
            log.warning("reconcile pass failed: %s", exc)
        await asyncio.sleep(interval)


def _run_fast_reconcile(minutes: int) -> list[dict]:
    from app.core.database import SessionLocal
    from app.models import User
    from app.services import reconcile as rec

    out = []
    db = SessionLocal()
    try:
        for user in db.query(User).all():
            try:
                out.append(rec.reconcile_fast(db, user, minutes=minutes))
            except rec.ReconcileError as exc:
                out.append({"user": user.username, "error": str(exc)})
            except Exception as exc:
                logging.getLogger("app.reconcile_fast").warning(
                    "fast reconcile failed for %s: %s", user.username, exc)
                out.append({"user": user.username, "error": str(exc)})
    finally:
        db.close()
    return out


async def _fast_reconcile_loop(interval: int, minutes: int) -> None:
    """Close open positions that have been sitting for > 30 min.

    Checks Kalshi order history every 30 min. If a position is resolved on
    Kalshi, closes the ledger row with true P&L. If it stays unresolved for
    24h, marks it "not_found" so it stops blocking the ledger.
    """
    log = logging.getLogger("app.reconcile_fast")
    await asyncio.sleep(60)
    while True:
        try:
            for result in await asyncio.to_thread(_run_fast_reconcile, minutes):
                if result.get("error"):
                    log.debug("fast reconcile skipped: %s", result["error"])
                elif result.get("resolved") or result.get("not_found"):
                    log.info("fast reconcile: %s resolved, %s not_found, %s retried",
                             result.get("resolved", 0), result.get("not_found", 0),
                             result.get("retried", 0))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("fast reconcile pass failed: %s", exc)
        await asyncio.sleep(interval)

def _run_tradier_monitor() -> list[dict]:
    from app.core.database import SessionLocal
    from app.models import User
    from app.models.tradier import TradierPosition
    from app.services import tradier_bot
    from sqlalchemy import select

    out = []
    db = SessionLocal()
    try:
        # only users with something at risk — no credentials are touched for
        # anyone whose position table is empty
        user_ids = {
            r[0] for r in db.execute(
                select(TradierPosition.user_id).where(
                    TradierPosition.status.in_(tradier_bot.ACTIVE_STATUSES)
                )
            )
        }
        for uid in user_ids:
            user = db.get(User, uid)
            if user is None:
                continue
            try:
                out.append(tradier_bot.monitor_pass(db, user))
            except Exception as exc:              # noqa: BLE001
                out.append({"user": uid, "error": str(exc)})
    finally:
        db.close()
    return out


async def _tradier_loop(interval: int) -> None:
    """The SL half of the Tradier exit pair. The TP half rests on the venue
    and needs nothing from us; this loop is what turns a stored sl_price
    into an actual sell, so its cadence IS the stop's reaction time."""
    log = logging.getLogger("app.tradier")
    await asyncio.sleep(15)
    while True:
        try:
            for result in await asyncio.to_thread(_run_tradier_monitor):
                for ev in result.get("events") or []:
                    log.info("tradier %s", ev)
                if result.get("error"):
                    log.debug("tradier sweep skipped: %s", result["error"])
        except asyncio.CancelledError:
            raise
        except Exception as exc:                  # keep the loop alive
            log.warning("tradier sweep failed: %s", exc)
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    _warn_on_duplicate_server(8790)
    tasks: list[asyncio.Task] = []
    if settings.super_auto_sync and settings.super_dir.is_dir():
        tasks.append(asyncio.create_task(_super_sync_loop(settings.super_sync_interval)))
    if settings.gex_daily_enabled and not settings.cloud_mode:
        tasks.append(asyncio.create_task(_gex_daily_loop()))
    if settings.earnings_enabled:
        tasks.append(asyncio.create_task(_earnings_warm_loop()))
    if settings.reconcile_enabled and not settings.cloud_mode:
        tasks.append(asyncio.create_task(
            _reconcile_loop(settings.reconcile_interval_s, settings.reconcile_stale_hours)
        ))
        tasks.append(asyncio.create_task(
            _fast_reconcile_loop(settings.reconcile_fast_interval_s,
                                 settings.reconcile_fast_stale_minutes)
        ))
    if settings.tradier_enabled and not settings.cloud_mode:
        tasks.append(asyncio.create_task(
            _tradier_loop(settings.tradier_monitor_interval_s)
        ))
    yield
    for task in tasks:
        task.cancel()
    for task in tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Standalone backend for three worlds on one process: the Tradier "
            "options desk (balance, chain preview, managed positions with "
            "TP/SL, the opening-range and A/B auto-traders, the HOT scan and "
            "the options-flow board), the 36 Trade Desk that fronts it on a "
            "phone, and the Bot Station that launches, supervises and settles "
            "the vendored Kalshi bots (btc15, btc60, sports, parlay, gold15, "
            "silver15, oil15). Plus the super_research signal engines and the "
            "SPY/QQQ/SPX level watcher they read. SQLite persistence, "
            "per-user credential folders, paper-only by default."
        ),
        lifespan=lifespan,
    )

    # Mobile/web clients are cross-origin; auth is header-based (no cookies),
    # so a permissive CORS policy is safe here.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Chrome's Private Network Access: a PUBLIC https page fetching a LOOPBACK
    # address gets an extra preflight carrying
    # Access-Control-Request-Private-Network, which must be answered with the
    # matching Allow header. Starlette's CORSMiddleware does not implement PNA
    # and rejects that preflight outright with "400 Disallowed CORS
    # private-network", which kills the getgamma 0DTE pusher SILENTLY — the
    # POST never leaves the browser and the tab-side catch swallows it.
    #
    # Deliberately narrow. PNA is the only thing standing between allow_origins
    # ["*"] and any site the user happens to visit POSTing to a local API that
    # can start and stop trading bots. So it is granted for exactly the origin
    # that needs it, on exactly the one endpoint that origin pushes to, and
    # nowhere else.
    PNA_ORIGINS = {"https://www.getgamma.io", "https://getgamma.io"}
    PNA_PATHS = {
        "/api/v1/super/gex0dte/refresh",
        "/api/v1/super/gex0dte/heartbeat",
    }

    @app.middleware("http")
    async def private_network_preflight(request: Request, call_next):
        if (
            request.method == "OPTIONS"
            and request.headers.get("access-control-request-private-network") == "true"
        ):
            origin = request.headers.get("origin", "")
            if origin in PNA_ORIGINS and request.url.path in PNA_PATHS:
                return Response(
                    status_code=200,
                    headers={
                        "Access-Control-Allow-Origin": origin,
                        "Access-Control-Allow-Methods": "POST, OPTIONS",
                        "Access-Control-Allow-Headers":
                            request.headers.get("access-control-request-headers", "content-type"),
                        "Access-Control-Allow-Private-Network": "true",
                        "Access-Control-Max-Age": "600",
                        "Vary": "Origin",
                    },
                )
        return await call_next(request)

    # Reachable without any credential. Everything else under /api needs
    # one. Kept deliberately short: each entry is a hole, and the only
    # things that belong here are what a browser must fetch BEFORE it can
    # log in, plus the endpoints used to tell a running server from a dead
    # one.
    OPEN_API_PATHS = {
        f"{settings.api_v1_prefix}/auth/login",
        f"{settings.api_v1_prefix}/auth/status",
    }

    # The 0DTE gamma feed is pushed in by a bookmarklet running on
    # getgamma.io, which cannot log in and must not be handed a key that
    # opens the whole API. TBOT_GEX_PUSH_TOKEN authorises these two paths
    # and nothing else: worst case for a leaked push token is poisoned
    # gamma data, not a placed order.
    PUSH_ONLY_PATHS = {
        f"{settings.api_v1_prefix}/super/gex0dte/refresh",
        f"{settings.api_v1_prefix}/super/gex0dte/heartbeat",
    }

    @app.middleware("http")
    async def api_credential_guard(request: Request, call_next):
        """Accept a login session OR the fixed shared key.

        A person signs in and gets a token; a script carries TBOT_API_KEY.
        Both travel in X-API-Key, so there is one code path and one header
        to explain. The static desk (served at /) is never gated — the
        login screen has to load before anyone can authenticate.
        """
        path = request.url.path
        if not path.startswith("/api"):
            return await call_next(request)
        # CORS preflights carry no headers to check, and refusing them
        # breaks the browser before the real request is ever sent.
        if request.method == "OPTIONS" or path in OPEN_API_PATHS:
            return await call_next(request)

        current = get_settings()
        if not (current.login_required or current.api_key):
            return await call_next(request)

        provided = request.headers.get("X-API-Key", "")
        import hmac as _hmac

        # Least privilege first: a push token is accepted ONLY on the two
        # ingest paths, so it can never stand in for a session anywhere else.
        if current.gex_push_token and path in PUSH_ONLY_PATHS:
            if _hmac.compare_digest(provided.encode(),
                                    current.gex_push_token.encode()):
                return await call_next(request)

        if current.api_key:
            if _hmac.compare_digest(provided.encode(), current.api_key.encode()):
                return await call_next(request)

        if current.login_required:
            from app.services import sessions as _sessions

            if _sessions.validate(provided) is not None:
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content={"detail": "Sign in to use this desk", "login_required": True},
            )

        return JSONResponse(
            status_code=401, content={"detail": "Missing or invalid X-API-Key"})

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    # Legacy-compatible /api/super/* aliases: exact vite-middleware shapes so
    # the existing SuperSite frontend can point straight at this backend.
    from app.api.v1.super import compat_router

    app.include_router(compat_router, prefix="/api")

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Frontends detect "backend present" by JSON content type — every
        # response, including errors, must be JSON.
        logging.getLogger("app").exception("Unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": f"Internal error: {exc}"})

    @app.get("/api", include_in_schema=False)
    def api_root():
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "openapi": "/openapi.json",
            "api": settings.api_v1_prefix,
        }

    @app.get("/health", tags=["system"], operation_id="healthCheck")
    def health():
        return {"status": "ok", "database": str(settings.database_path), "paper_only": settings.paper_only}

    _mount_desk(app)
    return app


def _mount_desk(app: FastAPI) -> None:
    """Serve frontend/dist at / when it has been built.

    Absent (a dev checkout that has not run `npm run build`, or an
    API-only deployment) this is a no-op and / answers with the same JSON
    banner the API always did — nothing breaks, there is just no UI.
    """
    from fastapi.staticfiles import StaticFiles

    dist = _PROJECT_ROOT_PATH / "frontend" / "dist"
    index = dist / "index.html"
    if not index.is_file():
        @app.get("/", include_in_schema=False)
        def no_desk():
            return {
                "app": get_settings().app_name,
                "desk": "not built - run `npm run build` in frontend/",
                "docs": "/docs",
                "api": get_settings().api_v1_prefix,
            }
        return

    # Hashed asset filenames, so the bundle is immutable and cacheable.
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    for extra in ("img",):
        if (dist / extra).is_dir():
            app.mount(f"/{extra}", StaticFiles(directory=dist / extra), name=extra)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # Client-side routing: any path the API did not claim is a desk
        # route, and index.html resolves it. Registered last, so every
        # real endpoint above still wins.
        candidate = (dist / full_path).resolve()
        if full_path and dist in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    logging.getLogger("app").info("serving desk from %s", dist)


app = create_app()
