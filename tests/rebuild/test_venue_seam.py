"""The seam must call methods the vendor clients actually have.

This suite exists because of two real bugs found the same afternoon, both the
same shape and both invisible:

    venue.option_chain  called client.option_chain   (it is client.chain)
    venue.bid_for       called client.option_quote   (it is client.quote)

Neither raised anywhere anybody could see. Every caller wrapped the seam in
``except Exception``, so a Python AttributeError -- a straightforward
programmer error, detectable without a network -- came back as "no contracts
on this chain" and "no bid available". The first broke the chain board and
contract selection. The second was worse: bid_for is what the stop-loss
monitor compares against, so a stop could never read a price and could never
fire, while every log line said the market was simply quiet.

A unit test of each seam function would not have caught this. They all pass a
fake client, and a fake has whatever methods the test gives it -- the fake
agreed with the mistake. The only thing that catches it is comparing the seam
against the REAL client class, which is what this file does, without a
network and without credentials.
"""

from __future__ import annotations

import inspect
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

# (seam module path, the client class it drives)
SEAMS = [
    ("backend/app/domains/trading/execution/venue.py",
     "app.services.tradier_client", "TradierClient"),
    ("backend/app/domains/botstation/venue.py",
     "app.services.kalshi_client", "KalshiClient"),
]


def _methods_called(source: str) -> set[str]:
    """Every ``client.<name>(`` in a seam module."""
    return set(re.findall(r"\bclient\.([a-z_][a-z0-9_]*)\(", source))


def _methods_available(module_path: str, class_name: str) -> set[str]:
    import importlib

    klass = getattr(importlib.import_module(module_path), class_name)
    return {name for name, _ in inspect.getmembers(klass, inspect.isfunction)}


@pytest.mark.parametrize("seam_path,client_module,client_class", SEAMS)
def test_every_method_the_seam_calls_exists_on_the_client(
        seam_path, client_module, client_class):
    """Given the seam module for a venue,
    when every method it invokes on its client is listed,
    then the client class defines all of them.

    Fails by NAME, so the report says which call is wrong rather than that
    something somewhere is.
    """
    source = (ROOT / seam_path).read_text(encoding="utf-8")
    called = _methods_called(source)
    available = _methods_available(client_module, client_class)

    missing = sorted(called - available)
    assert not missing, (
        f"{seam_path} calls methods {client_class} does not define: "
        + ", ".join(missing)
        + "\n\nEvery caller of this seam catches Exception, so an "
          "AttributeError here is reported to the operator as missing market "
          "data rather than as a bug."
    )


def test_the_stop_loss_price_read_is_not_wrapped_in_a_bare_except():
    """The one seam call that must never fail silently.

    bid_for is what the monitored stop compares against. If it swallows
    everything and answers None, a broken price read is indistinguishable
    from a quiet market, and the stop simply never fires -- which is the
    single worst failure this system can have.

    So: it may absorb venue and parsing failures, which are ordinary and
    recur every pass. It may NOT absorb ``Exception``, which includes the
    programmer errors that have to be loud.

    Checked by parsing rather than by searching the text. The first version
    of this test grepped the function source and failed on its own docstring,
    which NAMES the bug it is guarding against -- a test that cannot tell code
    from prose about code is not checking what it claims to.
    """
    import ast

    source = (ROOT / "backend/app/domains/trading/execution/venue.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    func = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "bid_for")

    caught = []
    for node in ast.walk(func):
        if isinstance(node, ast.ExceptHandler):
            names = ([node.type] if not isinstance(node.type, ast.Tuple)
                     else node.type.elts) if node.type else []
            caught += [n.id for n in names if isinstance(n, ast.Name)]

    assert "Exception" not in caught and "BaseException" not in caught, (
        "bid_for absorbs Exception. It previously called a method that did "
        "not exist and returned None for every position on every pass; the "
        "stop monitor read that as 'no bid yet' and no stop could ever fire."
    )
    assert caught, "bid_for must still absorb ordinary venue failures"

    calls = {ast.unparse(n.func) for n in ast.walk(func)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "client.quote" in calls, (
        "bid_for must read the option quote from the client's real quote "
        f"method; it calls {sorted(calls)}"
    )
