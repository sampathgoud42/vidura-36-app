"""Build the getgamma 0DTE bookmarklet from its readable source.

    python tools/make_bookmarklet.py

Reads tools/gex0dte_bookmarklet.js, substitutes THIS machine's API port and
push token from .env, strips comments and whitespace, and writes a single
`javascript:` line to var/gex0dte_bookmarklet.txt.

The point of generating it is that the one-liner can never drift from the
source, and the token in it is always the one the server will actually
accept. Re-run after editing either.
"""

from __future__ import annotations

import pathlib
import re
import sys
from urllib.parse import quote

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "gex0dte_bookmarklet.js"
OUT = ROOT / "var" / "gex0dte_bookmarklet.txt"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # pragma: no cover
    pass


def dotenv() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = (ROOT / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def strip_js(text: str) -> str:
    """Remove comments and collapse whitespace.

    Crude but sufficient: this file has no regex literals containing `//`
    and no template strings, which are what a naive stripper gets wrong.
    The one regex it does contain (the hostname test) has no slashes inside
    the pattern beyond its delimiters, and lives on a line that does not
    start with a comment.
    """
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        # Trailing comment, but never inside a string or the one regex.
        if "//" in line and "://" not in line and "/(^|" not in line:
            quotes = line.count("'") + line.count('"')
            if quotes % 2 == 0:
                line = line[:line.index("//")]
        out.append(line.strip())
    body = " ".join(p for p in out if p)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"\s+", " ", body)
    # Space around punctuation buys nothing in a bookmarklet.
    body = re.sub(r"\s*([{}();,:=><+])\s*", r"\1", body)
    return body.strip()


def main() -> int:
    if not SRC.is_file():
        raise SystemExit(f"missing {SRC}")
    env = dotenv()
    port = env.get("TBOT_PORT", "8790")
    token = env.get("TBOT_GEX_PUSH_TOKEN", "")

    if not token:
        print("WARNING: TBOT_GEX_PUSH_TOKEN is not set in .env.")
        print("         The push will be refused while login is required.")
        print("         Generate one:")
        print("           python -c \"import secrets;print(secrets.token_urlsafe(24))\"")
        print("         then add TBOT_GEX_PUSH_TOKEN=... to .env and restart.\n")

    text = SRC.read_text(encoding="utf-8")
    text = text.replace("'http://127.0.0.1:8791'", f"'http://127.0.0.1:{port}'")
    text = text.replace("'PASTE_TBOT_GEX_PUSH_TOKEN_HERE'", f"'{token}'")

    body = strip_js(text)
    # `javascript:` URLs are parsed as URLs, so a stray % or # in the token
    # or the code would truncate it. Encoding everything but the safe set
    # avoids depending on which characters happen to appear today.
    link = "javascript:" + quote(body, safe="")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(link, encoding="utf-8")

    print(f"[bookmarklet] api   http://127.0.0.1:{port}")
    print(f"[bookmarklet] token {'set (' + str(len(token)) + ' chars)' if token else 'MISSING'}")
    print(f"[bookmarklet] {len(link)} chars -> {OUT.relative_to(ROOT)}")
    print("\nCreate a bookmark, paste the file's contents as the URL, then")
    print("click it while on the getgamma.io dashboard tab.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
