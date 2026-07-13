from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[None]] = []

    def every(self, seconds: float, job: Callable[[], Awaitable[None]], name: str) -> None:
        self._tasks.append(asyncio.create_task(self._loop(seconds, job), name=name))

    def daily(self, hour: int, timezone: str, job: Callable[[], Awaitable[None]], name: str) -> None:
        self._tasks.append(asyncio.create_task(self._daily_loop(hour, ZoneInfo(timezone), job), name=name))

    async def _loop(self, seconds: float, job: Callable[[], Awaitable[None]]) -> None:
        while True:
            try:
                await job()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Ошибка фонового задания")
            await asyncio.sleep(seconds)

    async def _daily_loop(self, hour: int, timezone: ZoneInfo, job: Callable[[], Awaitable[None]]) -> None:
        while True:
            now = datetime.now(timezone)
            target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            await asyncio.sleep((target - now).total_seconds())
            try:
                await job()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Ошибка ежедневного задания")

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
