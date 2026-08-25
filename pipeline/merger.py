"""Ties loader -> normalize -> dedupe -> writer together (plan section 6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping

import pandas as pd

from .baseline import Baseline, apply_status, load_baseline
from .config import Config, load_config
from .dedupe import MergeStats, merge
from .loader import LoadError, load_file
from .normalize import normalize_frame

Progress = Callable[[str, float], None]


@dataclass
class FileReport:
    path: Path
    platform_key: str
    rows: int = 0
    missing_columns: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class MergeResult:
    frame: pd.DataFrame
    stats: MergeStats
    files: list[FileReport]
    baseline: Baseline | None = None
    baseline_error: str | None = None

    @property
    def errors(self) -> list[FileReport]:
        return [f for f in self.files if not f.ok]

    @property
    def warnings(self) -> list[FileReport]:
        return [f for f in self.files if f.ok and f.missing_columns]


def merge_sources(
    sources: Mapping[str, Iterable[Path | str]],
    cfg: Config | None = None,
    progress: Progress | None = None,
    previous: Path | str | None = None,
) -> MergeResult:
    """`sources` maps a platform key to the files dropped into that platform's box.

    `previous` is an optional merged list exported earlier; when given, only
    players missing from it are marked NEW. Leaving it out is not an error --
    every row is then new.
    """
    cfg = cfg or load_config()

    jobs = [
        (key, Path(path))
        for key, paths in sources.items()
        for path in paths
    ]
    reports: list[FileReport] = []
    frames: list[pd.DataFrame] = []

    for index, (key, path) in enumerate(jobs):
        platform = cfg.platforms[key]
        if progress:
            progress(f"Reading {path.name} ({platform.name})", index / max(len(jobs), 1))

        report = FileReport(path=path, platform_key=key)
        try:
            raw = load_file(path, platform)
            result = normalize_frame(raw, platform, cfg, source_name=path.name)
        except LoadError as exc:
            report.error = str(exc)
        else:
            report.rows = result.rows_in
            report.missing_columns = result.missing_columns
            frames.append(result.frame)
        reports.append(report)

    if progress:
        progress("Merging and de-duplicating", 0.85)

    frame, stats = merge(frames, cfg)

    baseline: Baseline | None = None
    baseline_error: str | None = None
    if previous:
        if progress:
            progress("Comparing against the previous merged list", 0.95)
        try:
            baseline = load_baseline(previous, cfg)
        except LoadError as exc:
            baseline_error = str(exc)

    stats.new_rows, stats.existing_rows = apply_status(frame, baseline, cfg)

    return MergeResult(
        frame=frame,
        stats=stats,
        files=reports,
        baseline=baseline,
        baseline_error=baseline_error,
    )
