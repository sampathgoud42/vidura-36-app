"""Which bots exist. Configuration, not code.

The old registry was already config-driven and that part was worth keeping.
What was not: everything around it. Four families each owned a near-identical
block of nine routes, an env mapper, an arm in a CSV-shape switch, nine client
wrappers and a UI panel. Adding a bot meant editing six files.

Here a bot is one config entry and one adapter class. Discovery is automatic,
so there is no registration list to edit and no dispatch switch to extend --
the two things the onboarding contract forbids by name.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BotVersion:
    version: str
    rel_script: str          # relative to the vendored runtime root
    default: bool = False


@dataclass(frozen=True)
class BotConfig:
    """Everything the shared machinery needs, declared rather than coded."""

    key: str
    name: str
    category: str
    cadence: str | None = None
    versions: tuple[BotVersion, ...] = ()
    # How the subprocess is handed its customer folder. The three styles are
    # the vendored scripts' own conventions, not a design of ours.
    launch_style: str = "cwd_customer"
    # The launch form renders itself from this. Without it, a new bot would
    # still need a hand-written UI panel -- which is the difference between
    # onboarding costing two files and onboarding costing six.
    options_schema: dict[str, dict] = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    def version_or_default(self, version: str | None) -> BotVersion:
        if not self.versions:
            raise KeyError(f"bot '{self.key}' declares no versions")
        if version is None:
            for v in self.versions:
                if v.default:
                    return v
            return self.versions[0]
        for v in self.versions:
            if v.version == version:
                return v
        known = ", ".join(v.version for v in self.versions)
        raise KeyError(f"unknown version '{version}' for bot '{self.key}' "
                       f"(known: {known})")


class UnknownBot(KeyError):
    pass


_REGISTRY: dict[str, BotConfig] = {}
_ADAPTERS: dict[str, Any] = {}
# Which modules a bot's registration reached. The onboarding test asserts this
# is only the bot's own files -- it is how "touched no shared library" is
# checked rather than asserted.
_TOUCHED: dict[str, set[str]] = {}


def register(config: BotConfig, adapter: Any) -> None:
    """Add a bot. This is the whole registration step."""
    from app.domains.botstation.adapters import is_adapter

    if not is_adapter(adapter):
        raise TypeError(
            f"{adapter!r} is not a bot adapter: it needs external_id() and "
            f"to_trade()")
    if config.key in _REGISTRY:
        raise ValueError(f"bot '{config.key}' is already registered")

    _REGISTRY[config.key] = config
    _ADAPTERS[config.key] = adapter() if isinstance(adapter, type) else adapter
    _TOUCHED[config.key] = {getattr(adapter, "__module__", "?")}
    logger.info("bot registered: %s (%s)", config.key, config.name)


def unregister(key: str) -> None:
    _REGISTRY.pop(key, None)
    _ADAPTERS.pop(key, None)
    _TOUCHED.pop(key, None)


def get(key: str) -> BotConfig:
    try:
        return _REGISTRY[key]
    except KeyError:
        raise UnknownBot(
            f"unknown bot '{key}' (known: {', '.join(sorted(_REGISTRY)) or 'none'})"
        ) from None


def adapter_for(key: str) -> Any:
    get(key)                    # raises UnknownBot with a useful message
    return _ADAPTERS[key]


def all_bots() -> list[BotConfig]:
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def modules_touched_by(key: str) -> set[str]:
    """Which modules this bot's registration reached.

    Used by the onboarding test to prove the plug point does not leak: a bot
    that reached into shared code is an architecture failure, and this is what
    makes it visible rather than a matter of opinion.
    """
    return set(_TOUCHED.get(key, set()))


def script_path(config: BotConfig, version: BotVersion) -> Path:
    from app.core.config import get_settings
    return get_settings().source_repo / version.rel_script


def report() -> list[dict]:
    """What GET /bots answers. ``exists`` is checked live, so the API says so
    honestly when a script has been renamed or is missing."""
    out = []
    for config in all_bots():
        out.append({
            "key": config.key,
            "name": config.name,
            "category": config.category,
            "cadence": config.cadence,
            "versions": [
                {"version": v.version,
                 "script": str(script_path(config, v)),
                 "exists": script_path(config, v).is_file(),
                 "default": v.default}
                for v in config.versions
            ],
        })
    return out


def validate_options(config: BotConfig, options: dict) -> dict:
    """Check launch options against the bot's OWN declared schema.

    One validator, every bot. The alternative is a hand-written validator per
    family, which is how four families ended up with four slightly different
    ideas of what a bankroll is.
    """
    cleaned: dict[str, Any] = {}
    for name, spec in config.options_schema.items():
        if name not in options or options[name] is None:
            if "default" in spec:
                cleaned[name] = spec["default"]
            continue
        value = options[name]
        kind = spec.get("type", "string")
        try:
            if kind == "number":
                value = float(value)
            elif kind == "integer":
                value = int(value)
            elif kind == "boolean":
                value = bool(value)
            else:
                value = str(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be a {kind}") from None

        if kind in ("number", "integer"):
            if "min" in spec and value < spec["min"]:
                raise ValueError(f"{name} must be at least {spec['min']}, got {value:g}")
            if "max" in spec and value > spec["max"]:
                raise ValueError(f"{name} must be at most {spec['max']}, got {value:g}")
        cleaned[name] = value

    unknown = set(options) - set(config.options_schema)
    if unknown:
        raise ValueError(
            f"{config.key} does not accept: {', '.join(sorted(unknown))}")
    return cleaned


def load_builtin_bots() -> None:
    """Register the bots that ship with this project.

    Kept in its own function rather than run at import so tests start from an
    empty registry and a throwaway bot is the only thing in it.
    """
    from app.domains.botstation import builtin

    builtin.register_all()
