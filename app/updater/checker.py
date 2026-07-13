from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

import httpx

from app.core.errors import ExternalServiceError

VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    notes: str
    url: str


class GitHubReleaseChecker:
    def __init__(self, repository: str, current_version: str) -> None:
        self.repository, self.current_version = repository, current_version

    @staticmethod
    def _tuple(version: str) -> tuple[int, int, int]:
        match = VERSION.match(version)
        if not match:
            raise ValueError(f"Некорректная версия: {version}")
        return tuple(map(int, match.groups()))

    async def check(self) -> ReleaseInfo | None:
        if not self.repository:
            return None
        async with httpx.AsyncClient(timeout=15, headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}) as client:
            response = await client.get(f"https://api.github.com/repos/{self.repository}/releases/latest")
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise ExternalServiceError(f"GitHub вернул HTTP {response.status_code}")
        data: dict[str, Any] = response.json()
        version = str(data.get("tag_name", ""))
        if self._tuple(version) <= self._tuple(self.current_version):
            return None
        return ReleaseInfo(version, str(data.get("body") or "Без описания")[:1500], str(data.get("html_url") or ""))

