from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    files = [
        *PROJECT_ROOT.joinpath("app").rglob("*.py"),
        *PROJECT_ROOT.joinpath("tests").rglob("*.py"),
        PROJECT_ROOT / "scripts" / "check.py",
    ]
    for path in files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(f"AST: OK ({len(files)} файлов)")
    return subprocess.call(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=PROJECT_ROOT,
    )


if __name__ == "__main__":
    raise SystemExit(main())
