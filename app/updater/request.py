from __future__ import annotations

from pathlib import Path
import json
import os
import re
from uuid import uuid4

VERSION = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


class UpdateRequestWriter:
    def __init__(self, directory: Path = Path("/run/ozon-ai-os/update-requests")) -> None:
        self.directory = directory

    def create(self, version: str, chat_id: int) -> Path:
        if not VERSION.match(version):
            raise ValueError("Некорректная версия")
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"{uuid4()}.json"
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps({"version": version, "chat_id": chat_id}), encoding="utf-8")
        os.chmod(temp, 0o600)
        temp.replace(target)
        return target

