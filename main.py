"""Entry point for the packaged Tournament Entry Merger app.

Set TEM_SELFTEST=<path> to write a diagnostics line and exit instead of
opening the window -- handy for checking a fresh install without a screen.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _calamine_status() -> str:
    """The reader used for .xlsx files openpyxl refuses to parse."""
    try:
        import python_calamine  # noqa: F401
    except ImportError:
        return "MISSING - portal exports with odd styling will fail"
    return "available"


def selftest(target: str) -> int:
    import gui
    from pipeline.config import config_path, load_config

    cfg = load_config()
    lines = [
        f"python           {sys.version.split()[0]}",
        f"frozen           {getattr(sys, 'frozen', False)}",
        f"config           {config_path()}",
        f"platforms        {', '.join(p.abbrev for p in cfg.platform_list)}",
        f"output columns   {len(cfg.output_columns)}",
        f"drag and drop    {'available' if gui.DND_AVAILABLE else 'UNAVAILABLE'}",
        f"xlsx fallback    {_calamine_status()}",
    ]
    Path(target).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    target = os.environ.get("TEM_SELFTEST")
    if target:
        return selftest(target)

    from gui import main as run_gui

    run_gui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
