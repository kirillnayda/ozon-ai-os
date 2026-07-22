from __future__ import annotations

import os
from pathlib import Path
import tempfile

from app.core.security import html_escape
from app.telegram.client import TelegramClient


class StartupUpdateNotifier:
    def __init__(self, client: TelegramClient, chat_id: int, version: str, state_file: Path) -> None:
        self.client = client
        self.chat_id = chat_id
        self.version = version
        self.state_file = state_file

    async def notify_once(self) -> bool:
        current = self.state_file.read_text(encoding="utf-8").strip() if self.state_file.is_file() else ""
        if current == self.version:
            return False
        await self.client.send_message(
            self.chat_id,
            f"✅ Ozon AI OS обновлён до <code>{html_escape(self.version)}</code>. Бот запущен и готов к работе.",
        )
        self._save()
        return True

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".update-notified-", dir=self.state_file.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(self.version + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.state_file)
        finally:
            temporary.unlink(missing_ok=True)
