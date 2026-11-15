"""포터블 exe 진입점.

개발 중에는 `python main.py`, 배포본에서는 `LegalDeid.exe`로 실행된다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap() -> None:
    root = Path(__file__).resolve().parent
    for candidate in (root / "src", root):
        if candidate.is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


_bootstrap()

from app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
