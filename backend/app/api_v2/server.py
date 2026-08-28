"""Entry point for the rebuilt app.

Separate from app.main on purpose. The old app is still serving the live desk,
and until cutover both have to be able to run at once on different ports --
which also makes them comparable side by side rather than one replacing the
other on trust.

    .venv\\Scripts\\python -m app.api_v2.server
    TBOT_V2_PORT=8792 .venv\\Scripts\\python -m app.api_v2.server

Startup runs migrations and then refuses to serve if the schema is not current.
A desk that boots against a half-migrated database is worse than one that does
not boot: it answers, and the answers are wrong.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("app.v2")


def prepare() -> None:
    """Migrate, then verify. Refuse to serve a schema we are not sure of."""
    from app.platform.db import migrations

    migrations.upgrade_to_head()
    current, head = migrations.current_revision(), migrations.head_revision()
    if current != head:
        raise SystemExit(
            f"schema is at {current}, head is {head}. Refusing to serve: an "
            f"application on a half-migrated database answers, and the "
            f"answers are wrong."
        )
    logger.info("schema at %s", current)

    from app.tenancy import bootstrap

    if not bootstrap.has_any_tenant():
        logger.warning(
            "no operators exist. Nobody can sign in. Create the first one:\n"
            "    python -c \"import sys; sys.path.insert(0,'backend'); "
            "from app.tenancy import bootstrap; "
            "bootstrap.create_first_admin(slug='you', password='...')\"")


def main() -> int:
    import uvicorn

    from app.api_v2.application import create_app

    prepare()
    port = int(os.environ.get("TBOT_V2_PORT", "8792"))
    # 127.0.0.1, not 0.0.0.0. The old app binds every interface; this one is
    # for testing and has no business being reachable from the LAN until
    # somebody decides it should be.
    host = os.environ.get("TBOT_V2_HOST", "127.0.0.1")
    logger.info("desk on http://%s:%s", host, port)
    uvicorn.run(create_app(), host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
