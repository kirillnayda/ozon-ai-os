from __future__ import annotations

import asyncio
import logging

from app.developer_agent.service import DeveloperAgentService

logger = logging.getLogger(__name__)


class TaskQueue:
    """Один worker последовательно исполняет задачи и push-запросы."""

    def __init__(self, service: DeveloperAgentService, poll_seconds: float = 2.0) -> None:
        self.service, self.poll_seconds = service, poll_seconds
        self.running = True

    async def run(self) -> None:
        while self.running:
            try:
                await asyncio.to_thread(self.service.process_pushes)
                task = await asyncio.to_thread(self.service.process_one)
                if task is None:
                    await asyncio.sleep(self.poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Developer Agent worker iteration failed")
                await asyncio.sleep(self.poll_seconds)

    def stop(self) -> None:
        self.running = False

