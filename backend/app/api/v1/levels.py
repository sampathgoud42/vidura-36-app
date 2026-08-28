"""Level-cross watcher endpoints (SPY / QQQ / SPX index basket).

Thin HTTP face over ``services.levels``: read the watcher's own status
snapshot, start it, stop it. The engine logic lives entirely in
levels_watcher.py in the day-trade folder.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.cloud import require_local_runtime
from app.services import levels as svc

router = APIRouter(prefix="/levels", tags=["levels"])


@router.get("/status", operation_id="getLevelsStatus")
def levels_status() -> dict:
    """Marked levels + latest cross per level, plus watcher liveness."""
    return svc.status()


@router.post("/start", operation_id="startLevelsWatcher")
def levels_start() -> dict:
    require_local_runtime("Starting the levels watcher")
    try:
        return svc.start()
    except svc.LevelsError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"start failed: {exc}") from exc


@router.post("/stop", operation_id="stopLevelsWatcher")
def levels_stop() -> dict:
    require_local_runtime("Stopping the levels watcher")
    return svc.stop()
