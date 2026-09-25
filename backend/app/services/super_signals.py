"""The signal desk's read-only service, as this app reaches it.

One client for both callers -- the /super-signals proxy router and the
super_signals auto-trade strategy -- so they read the desk the same way: the
URL from settings, a hard timeout, no proxy taken from the environment, and a
failure that says which of down, slow or broken it was. The desk is a separate
project (vidura-super-signals); a URL rather than a folder keeps this one
reading nothing outside itself.
"""

from __future__ import annotations

import requests

from app.core.config import get_settings

OFFLINE = ("the super signals service is not answering -- it runs from the "
           "vidura-super-signals project (task Vidura_SignalAgents_API, or "
           "`python -m signal_agents.desk serve` there)")

# One pooled session, blind to proxy settings in the environment: the service
# is on loopback, and a machine-wide proxy would otherwise be asked to reach
# 127.0.0.1 on this process's behalf.
_http = requests.Session()
_http.trust_env = False


class Unavailable(Exception):
    """The desk could not answer usefully. `status` is the HTTP code to relay:
    503 down, 504 slow, 502 broken, or the desk's own 400/404."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _detail(r: requests.Response) -> str:
    try:
        return r.json().get("detail") or r.reason
    except ValueError:
        return r.reason


def get(path: str, params: dict | None = None) -> requests.Response:
    s = get_settings()
    try:
        r = _http.get(s.super_signals_url.rstrip("/") + path, params=params,
                      timeout=s.super_signals_timeout_s)
    except requests.Timeout as exc:
        raise Unavailable(504, "the super signals service did not answer in time") from exc
    except requests.RequestException as exc:
        raise Unavailable(503, OFFLINE) from exc
    if r.status_code in (400, 404):
        raise Unavailable(r.status_code, _detail(r))
    if not r.ok:
        raise Unavailable(502, f"the super signals service answered {r.status_code}: {_detail(r)}")
    return r


def get_json(path: str, params: dict | None = None) -> dict:
    return get(path, params).json()
