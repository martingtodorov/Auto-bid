"""Simple in-memory WebSocket broadcaster per auction."""
import asyncio
import logging
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class AuctionHub:
    def __init__(self):
        self._rooms: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def join(self, auction_id: str, ws: WebSocket):
        async with self._lock:
            self._rooms.setdefault(auction_id, set()).add(ws)

    async def leave(self, auction_id: str, ws: WebSocket):
        async with self._lock:
            if auction_id in self._rooms:
                self._rooms[auction_id].discard(ws)
                if not self._rooms[auction_id]:
                    self._rooms.pop(auction_id, None)

    async def broadcast(self, auction_id: str, message: dict):
        sockets = list(self._rooms.get(auction_id, set()))
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning("ws broadcast error: %s", e)


hub = AuctionHub()
