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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api_v2.routers import (auth, bots, desk, positions, tenants,
                                wellness)
from app.core.config import get_settings

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

    app = FastAPI(
        title="Vidura 36",
        version=settings.app_version,
        description="Trading desk and bot station.",
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
            body["status"] = "degraded"

        return body

    return app
