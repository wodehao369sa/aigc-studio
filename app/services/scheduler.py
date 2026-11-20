"""In-process task poller.

A single background asyncio task polls one task per tick.  The same operation
is exposed through ``POST /api/internal/poll`` for the systemd timer, guarded
by an asyncio lock so both paths never work on the same task concurrently.
"""

from __future__ import annotations

import asyncio
import logging

from ..config import POLL_BATCH_SIZE, POLL_INTERVAL_SECONDS
from .tasks import poll_one_task

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, ctx, interval: float = POLL_INTERVAL_SECONDS, batch_size: int = POLL_BATCH_SIZE) -> None:
        self.ctx = ctx
        self.interval = interval
        self.batch_size = batch_size
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    async def run(self) -> None:
        logger.info("task scheduler started (interval=%.1fs)", self.interval)
        while True:
            await self.tick()
            await asyncio.sleep(self.interval)

    async def tick(self) -> None:
        async with self._lock:
            for _ in range(self.batch_size):
                try:
                    await poll_one_task(self.ctx)
                except Exception:  # noqa: BLE001 - scheduler must never die
                    logger.exception("poll tick failed")

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def poll_once(self):
        """Used by the internal HTTP endpoint; returns the polled task or None."""
        async with self._lock:
            return await poll_one_task(self.ctx)
