"""thrice.report <attempt-dir>... : write report.html for each attempt."""
from __future__ import annotations

import sys
from pathlib import Path

from .html import render

if __name__ == "__main__":
    targets = sys.argv[1:] or sorted(str(p) for p in Path("artifacts").glob("*/"))
    for t in targets:
        d = Path(t)
        if not (d / "attempt.json").exists():
            continue
        print(render(d))
