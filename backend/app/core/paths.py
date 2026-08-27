"""Cross-platform path handling for user root folders.

User root folders may be recorded in the database in either Windows form
(``D:\\data\\customers\\sampath``) or POSIX form
(``/home/sampath/customers/sampath``) because the same database file can be
copied between a Windows workstation and a Linux server.  Everything that
touches the filesystem goes through this module so the rest of the codebase
never has to care which convention a stored path uses.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath, PureWindowsPath

# A Windows-style path starts with a drive letter ("D:\" / "D:/") or a UNC
# prefix ("\\server\share").  Anything else is treated as POSIX-style.
_WINDOWS_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")


class PathSecurityError(ValueError):
    """Raised when a resolved path would escape its user root folder."""


def is_windows_style(raw: str) -> bool:
    """True if *raw* is written in Windows drive/UNC notation."""
    return bool(_WINDOWS_PATH_RE.match(raw))


def normalize_root(raw: str) -> Path:
    """Convert a stored root-folder string into a native ``Path``.

    The string is first parsed with the pure-path flavour matching its own
    notation (so backslashes vs. forward slashes are interpreted correctly),
    then re-assembled as a native path for the current OS.  On the OS the
    path was written for this is a no-op; on the other OS it at least yields
    a well-formed native path that callers can check with ``exists()``.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("user_root_folder must not be empty")
    pure = PureWindowsPath(raw) if is_windows_style(raw) else PurePosixPath(raw)
    return Path(*pure.parts)


def canonical_str(raw: str) -> str:
    """Stable string form used for storage/comparison (forward slashes)."""
    pure = PureWindowsPath(raw) if is_windows_style(raw) else PurePosixPath(raw)
    return pure.as_posix()


def resolve_user_file(root: str | Path, *parts: str) -> Path:
    """Resolve ``root/parts...`` and guarantee the result stays inside root.

    Guards against path traversal: a stored filename such as
    ``..\\..\\other-user\\secrets.env`` must never escape the user's folder.
    """
    root_path = normalize_root(str(root)).resolve()
    candidate = root_path.joinpath(*parts).resolve()
    if candidate != root_path and root_path not in candidate.parents:
        raise PathSecurityError(
            f"Resolved path {candidate} escapes user root {root_path}"
        )
    return candidate


def validate_root_exists(raw: str) -> tuple[bool, str]:
    """Best-effort existence check, returning (exists, native_form)."""
    try:
        native = normalize_root(raw)
    except (ValueError, OSError) as exc:
        return False, f"invalid path: {exc}"
    return native.is_dir(), str(native)
