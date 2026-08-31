"""Walk every API route on an app, including routers included into routers.

Why this exists, written down because it was a near miss:

FastAPI 0.141 keeps an included router as a nested ``_IncludedRouter`` object
rather than copying its routes into ``app.routes``. The contract and isolation
tests were written to iterate ``app.routes`` directly, which on this version
sees 2 routes out of 16 — everything except ``/health`` and ``/readiness``.

The failure mode was silent and pointed the wrong way. ``test_no_endpoint_
accepts_a_tenant_selector`` is a SECURITY assertion, and it would have passed
green while inspecting almost nothing. A test that passes because it looked at
nothing is worse than one that fails, because it is believed.

So route enumeration lives in one place, recurses, and is used by every test
that reasons about the surface.
"""

from __future__ import annotations

from fastapi.routing import APIRoute


from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    """One served operation, with the path the CLIENT actually calls.

    ``_IncludedRouter.original_router`` holds the router exactly as it was
    written — so its paths carry the router's own prefix (``/auth/login``) but
    not the prefix it was mounted under (``/api/v1``). That prefix lives on
    the include context. Reading only one of the two gives paths that look
    plausible and match nothing, which is a worse failure than an error.
    """

    route: APIRoute
    path: str

    @property
    def methods(self) -> set[str]:
        return set(self.route.methods or set())

    @property
    def endpoint(self):
        return self.route.endpoint

    @property
    def dependant(self):
        return self.route.dependant


def _endpoints(app) -> list[Endpoint]:
    found: list[Endpoint] = []

    def walk(routes, prefix: str) -> None:
        for route in routes:
            if isinstance(route, APIRoute):
                found.append(Endpoint(route=route, path=prefix + route.path))
                continue

            # FastAPI 0.141: an included router stays nested.
            original = getattr(route, "original_router", None)
            if original is not None:
                context = getattr(route, "include_context", None)
                mounted = getattr(context, "prefix", "") or ""
                walk(original.routes, prefix + mounted)
                continue

            # Starlette Mount and anything else holding children.
            nested = getattr(route, "routes", None)
            if nested:
                walk(nested, prefix + (getattr(route, "path", "") or ""))

    walk(app.routes, "")
    return found


def api_routes(app) -> list[Endpoint]:
    """Every operation the app serves, at any nesting depth.

    Returns Endpoint rather than APIRoute so callers get the client-facing
    path; ``.endpoint`` and ``.dependant`` pass straight through for the tests
    that introspect parameters.
    """
    return _endpoints(app)


def served(app) -> set[tuple[str, str]]:
    """``{(METHOD, path)}`` for everything the app serves."""
    out: set[tuple[str, str]] = set()
    for ep in _endpoints(app):
        for method in ep.methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            out.add((method, ep.path))
    return out
