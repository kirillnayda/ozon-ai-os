from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys


def main() -> int:
    files = [*Path("app").rglob("*.py"), *Path("tests").rglob("*.py"), Path("scripts/check.py")]
    for path in files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(f"AST: OK ({len(files)} файлов)")
    return subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])


if __name__ == "__main__":
    raise SystemExit(main())

