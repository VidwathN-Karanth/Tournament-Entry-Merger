"""Ordering (plan section 6) and duplicate collapsing (plan section 7)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import Config
from .normalize import DATE_KEY


@dataclass
class DuplicateHit:
    name: str
    platform: str
    matched_on: str
    value: str
    kept_name: str
    kept_platform: str


@dataclass
class SharedId:
    """One ID that two different players are registered under."""

    column: str
    value: str
    names: tuple[str, str]
    dobs: tuple[str, str]


def same_person(dob_a: str, dob_b: str) -> bool:
    """Whether two rows sharing an ID are really the same player.

    A matching ID normally settles it, but registration portals let a parent
    enter several children under one ID. Different dates of birth contradict
    the ID, and two entrants must never collapse into one -- somebody has
    paid for each. A blank DOB on either side proves nothing, so the ID
    still decides.
    """
    if not dob_a or not dob_b:
        return True
    return dob_a == dob_b


@dataclass
class MergeStats:
    rows_by_platform: dict[str, int] = field(default_factory=dict)
    dropped_by_platform: dict[str, int] = field(default_factory=dict)
    dated_rows: int = 0
    undated_rows: int = 0
    duplicates: list[DuplicateHit] = field(default_factory=list)
    shared_ids: list[SharedId] = field(default_factory=list)
    final_rows: int = 0
    new_rows: int = 0
    existing_rows: int = 0

    @property
    def total_in(self) -> int:
        return sum(self.rows_by_platform.values())

    @property
    def total_dropped(self) -> int:
        return sum(self.dropped_by_platform.values())


def order_rows(frame: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, int, int]:
    """Group rows by platform, in cfg's output order.

    Inside each group: rows carrying a payment date come first, earliest to
    latest; the rest keep the order they had in the input file.
    """
    has_date = frame[DATE_KEY].notna()
    groups = []
    for abbrev in cfg.output_abbrev_order:
        block = frame[frame["Platform"] == abbrev]
        if block.empty:
            continue
        dated = block[has_date.loc[block.index]].sort_values(DATE_KEY, kind="mergesort")
        undated = block[~has_date.loc[block.index]]  # left in input order
        groups.append(pd.concat([dated, undated]))

    ordered = (
        pd.concat(groups, ignore_index=True)
        if groups
        else frame.iloc[0:0].reset_index(drop=True)
    )
    return ordered, int(has_date.sum()), int((~has_date).sum())


def merge(frames: list[pd.DataFrame], cfg: Config) -> tuple[pd.DataFrame, MergeStats]:
    """Concatenate, order, and deduplicate every normalized frame."""
    stats = MergeStats()

    non_empty = [f for f in frames if len(f)]
    if not non_empty:
        empty = pd.DataFrame(columns=cfg.output_columns)
        return empty, stats

    combined = pd.concat(non_empty, ignore_index=True)
    for platform, count in combined["Platform"].value_counts().items():
        stats.rows_by_platform[str(platform)] = int(count)

    ordered, stats.dated_rows, stats.undated_rows = order_rows(combined, cfg)

    id_values = {col: ordered[col].astype(str).tolist() for col in cfg.id_columns}
    names = ordered[cfg.name_column].astype(str).tolist()
    platforms = ordered["Platform"].astype(str).tolist()
    dobs = (
        ordered["DOB"].astype(str).tolist()
        if "DOB" in ordered.columns
        else [""] * len(ordered)
    )

    seen: dict[str, dict[str, int]] = {col: {} for col in cfg.id_columns}
    keep: list[int] = []

    for position in range(len(ordered)):
        row_ids = {col: id_values[col][position] for col in cfg.id_columns}
        hit = None
        for column, value in row_ids.items():
            if not value or value not in seen[column]:
                continue
            other = seen[column][value]
            if same_person(dobs[position], dobs[other]):
                hit = (column, value)
                break
            # Same ID, different date of birth: siblings entered under one
            # parent's ID, or a portal typo. Two real entrants -- keep both.
            stats.shared_ids.append(
                SharedId(
                    column=column,
                    value=value,
                    names=(names[other], names[position]),
                    dobs=(dobs[other], dobs[position]),
                )
            )

        if hit is not None:
            column, value = hit
            kept_at = seen[column][value]
            platform = platforms[position]
            stats.dropped_by_platform[platform] = stats.dropped_by_platform.get(platform, 0) + 1
            stats.duplicates.append(
                DuplicateHit(
                    name=names[position],
                    platform=platform,
                    matched_on=column,
                    value=value,
                    kept_name=names[kept_at],
                    kept_platform=platforms[kept_at],
                )
            )
            continue

        for column, value in row_ids.items():
            if value:
                seen[column][value] = position
        keep.append(position)

    result = ordered.loc[keep, cfg.output_columns].reset_index(drop=True)
    stats.final_rows = len(result)
    return result, stats
