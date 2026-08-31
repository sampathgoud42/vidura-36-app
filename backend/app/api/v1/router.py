from fastapi import APIRouter

from app.api.v1 import (auth, bots, desk36, kalshi, levels, super, tradier,
                        trades, users, worlds)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(kalshi.router)
api_router.include_router(bots.router)
api_router.include_router(trades.router)
api_router.include_router(super.router)
api_router.include_router(tradier.router)
api_router.include_router(levels.router)
api_router.include_router(desk36.router)
api_router.include_router(worlds.router)
