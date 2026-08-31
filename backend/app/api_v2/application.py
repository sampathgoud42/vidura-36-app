"""The rebuilt application.

Deliberately assembled here rather than in ``app.main`` for now. The old app
still serves the live desk, and the two cannot coexist in one router table:
the Phase 4 contract test asserts that NOTHING is served which the contract
does not declare, and every legacy route would fail it. Cutover happens when
this app serves the whole contract; until then ``app.main`` is untouched and
sampath keeps trading.

What is different from the old assembly, and why:

  * There is no ``user_id`` anywhere. Identity comes from the session, once,
    in ``deps.current_tenant``.
  * The shared API key opens operational endpoints only. It resolves to no
    tenant, so it cannot reach tenant data by construction rather than by a
    check someone has to remember.
  * ``/readiness`` reports the risk-monitor heartbeat, which is what makes an
    unwatched stop-loss visible instead of silent.
"""

from __future__ import annotations

import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api_v2.routers import (auth, bots, desk, positions, research,
                                tenants,
                                wellness)
from app.core.config import get_settings
from app.platform.security.envelope import MasterKeyMissing

logger = logging.getLogger(__name__)

# Reachable without a session. Each entry is a hole, so the list is short and
# every one of them is something a browser must fetch BEFORE it can sign in,
# or something used to tell a running server from a dead one.
OPEN_PATHS = {
    "/health",
    "/readiness",
}


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """Start the loops that must run whether or not anyone is looking.

        The risk monitor was written, tested, and never started -- nothing in
        the application called sweep_all_tenants, so the heartbeat table was
        empty and no monitored stop could fire. Starting it here means it is
        alive for exactly as long as the server is, which is the only window
        in which it is any use.

        Disable with TBOT_NO_BACKGROUND=1 for a process that should serve
        requests without also managing positions (a one-off script, a test).
        """
        import os

        from app.api_v2 import background

        enabled = os.environ.get("TBOT_NO_BACKGROUND", "").strip() not in ("1", "true")
        if enabled:
            background.start_all()
        try:
            yield
        finally:
            if enabled:
                background.stop_all()

    app = FastAPI(
        title="Vidura 36",
        version=settings.app_version,
        description="Trading desk and bot station.",
        lifespan=lifespan,
    )

    # Auth is header-based and there are no cookies, so a permissive origin
    # policy cannot be used to ride a session: a hostile page cannot read the
    # token out of another origin's localStorage.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def guard(request: Request, call_next):
        """Authentication only. Authorisation is per-route, by dependency.

        The old build stopped here and let each endpoint decide whose data to
        return from a parameter. Passing this middleware now proves only that
        the caller is someone; WHICH someone is decided downstream, and only
        from the session.
        """
        path = request.url.path
        if request.method == "OPTIONS" or path in OPEN_PATHS:
            return await call_next(request)
        if not path.startswith("/api"):
            return await call_next(request)
        if path in (f"{settings.api_v1_prefix}/auth/login",
                    f"{settings.api_v1_prefix}/auth/status"):
            return await call_next(request)

        if not request.headers.get("X-API-Key"):
            return JSONResponse(
                status_code=401,
                content={"detail": "Sign in to use this desk",
                         "login_required": True},
            )
        return await call_next(request)

    # The bots this project ships with. Registered exactly the way a bot
    # added tomorrow is, so the onboarding contract is proven for real
    # bots and not only for the throwaway test one.
    from app.domains.botstation import registry as bot_registry
    bot_registry.load_builtin_bots()

    @app.exception_handler(RequestValidationError)
    async def _unprocessable(request: Request, exc: RequestValidationError):
        """A 422 that says which field, and what was sent.

        FastAPI rejects a malformed body before any handler runs, so the
        server log recorded only "422 Unprocessable Content" with no
        indication of what the client got wrong -- and the desk showed a
        launch that simply did not happen. The field and its value are the
        whole diagnosis.
        """
        logger.warning("422 on %s %s: %s", request.method, request.url.path,
                       exc.errors())
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "body": exc.body})

    @app.exception_handler(StarletteHTTPException)
    async def _unauthorised(request: Request, exc: StarletteHTTPException):
        """Every 401 says login_required, wherever it was raised.

        The desk routes to the sign-in form on that marker, not on the status
        code -- a wrong password is also a 401, and /auth must be free to
        report its own failures without tearing the desk down.

        The middleware set the marker and the dependencies did not, so a
        session that died under a running desk produced 401s the client could
        not recognise: every polling panel painted "Sign in to use this desk"
        in place of its data and the login form was never shown. Adding it
        here rather than at each raise means a 401 introduced later cannot
        forget it.
        """
        body = (exc.detail if isinstance(exc.detail, dict)
                else {"detail": exc.detail})
        # NOT on /auth. A 401 there means "those credentials are wrong",
        # which is the endpoint reporting its own result -- a different fact
        # from "you have no session", and the only one the desk must not
        # react to by throwing the operator back to a form they are already
        # looking at. The marker means exactly "you need to sign in", and it
        # is what both the desk and the contract test key on.
        gated = not request.url.path.startswith(
            f"{get_settings().api_v1_prefix}/auth/")
        if exc.status_code == 401 and gated:
            body = {**body, "login_required": True}
        return JSONResponse(status_code=exc.status_code, content=body,
                            headers=getattr(exc, "headers", None))

    @app.exception_handler(MasterKeyMissing)
    async def _no_master_key(request: Request, exc: MasterKeyMissing):
        """A missing master key is a DEPLOYMENT fault, not a bug.

        It surfaced as a bare 500 on four endpoints, which reads like the code
        is broken. 503 with the actual reason tells whoever is on call what to
        do, and never echoes the key or its absence beyond that.
        """
        logger.error("master key unavailable: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"detail": "credential store unavailable: the encryption "
                               "master key is not configured on this server"},
        )

    prefix = settings.api_v1_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(tenants.router, prefix=prefix)
    app.include_router(wellness.router, prefix=prefix)
    app.include_router(positions.router, prefix=prefix)
    app.include_router(positions.credentials_router, prefix=prefix)
    app.include_router(bots.router, prefix=prefix)
    app.include_router(desk.trades_router, prefix=prefix)
    app.include_router(desk.market_router, prefix=prefix)
    app.include_router(desk.desk36_router, prefix=prefix)
    app.include_router(desk.levels_router, prefix=prefix)
    app.include_router(research.router, prefix=prefix)

    @app.get("/health", operation_id="healthCheck")
    def health() -> dict:
        return {
            "status": "ok",
            "version": settings.app_version,
            "paper_only": settings.paper_only,
        }

    @app.get("/readiness", operation_id="readiness")
    def readiness() -> dict:
        """Is this process fit to be trusted with money right now.

        Health says the process is up. Readiness says the things that make it
        SAFE are up: the database answers, the schema is current, and the
        risk monitor has run recently enough that a stop-loss is actually
        being watched.
        """
        from app.platform.db import migrations

        body: dict = {"status": "ok"}
        try:
            current = migrations.current_revision()
            head = migrations.head_revision()
            body["migrations"] = {"current": current, "head": head,
                                  "up_to_date": current == head}
            if current != head:
                body["status"] = "degraded"
        except Exception as exc:                       # noqa: BLE001
            body["migrations"] = {"error": str(exc)}
            body["status"] = "degraded"

        try:
            from app.domains.trading.risk import heartbeat
            body["risk_monitor"] = heartbeat.summary()
        except Exception:                              # noqa: BLE001
            # Not built yet, or not running. Say so rather than implying a
            # stop is being watched when nothing is watching it.
            body["risk_monitor"] = {"available": False,
                                    "detail": "risk monitor not running"}
        try:
            from app.api_v2 import background

            body["background"] = background.status()
        except Exception:                               # noqa: BLE001
            body["background"] = {}
            body["status"] = "degraded"

        return body

    _serve_desk(app)
    return app


def _serve_desk(app: FastAPI) -> None:
    """Serve the built desk, if there is one.

    Its own build directory rather than the one app.main serves. The two
    frontends are NOT interchangeable -- this build talks to a session-scoped
    API with no user_id, the other to one that requires it -- so sharing a
    directory would mean whichever built last broke the other desk. That
    matters while the old app is still serving live money.
    """
    from pathlib import Path

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    root = Path(__file__).resolve().parents[3]
    dist = root / "frontend" / "dist-v2"
    index = dist / "index.html"
    if not index.is_file():
        logger.warning("no desk build at %s; the API is up and the UI is not "
                       "(run: npm run build -- --outDir dist-v2)", dist)
        return

    for name in ("assets", "img"):
        folder = dist / name
        if folder.is_dir():
            app.mount(f"/{name}", StaticFiles(directory=folder), name=name)

    @app.get("/{full_path:path}", include_in_schema=False)
    def desk(full_path: str):
        """Single-page app: every unmatched path returns index.html.

        EXCEPT under /api, which must 404. Serving index.html there meant an
        endpoint that does not exist answered 200 with HTML -- so a missing
        route was indistinguishable from a working one, and the only symptom
        was a panel quietly showing nothing. /api/v1/worlds did exactly that
        after it was folded into /auth/me.

        Deliberately last, so it can never shadow a real API route, and
        excluded from the schema so the contract test does not see a
        catch-all where an endpoint should be.
        """
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404,
                                content={"detail": f"no such endpoint: /{full_path}"})
        candidate = dist / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        # index.html is never cached. Its asset filenames carry a content hash
        # -- those are safe to cache forever -- but the HTML that NAMES them
        # is the one file that must never be stale, or a browser keeps loading
        # yesterday's bundle from a page it thinks is fresh and the desk
        # silently runs old code against a new API.
        return FileResponse(index, headers={
            "Cache-Control": "no-store, must-revalidate",
            "Pragma": "no-cache",
        })

    logger.info("serving desk from %s", dist)
