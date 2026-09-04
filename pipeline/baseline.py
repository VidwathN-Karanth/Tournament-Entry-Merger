"""Compare a merge against a previously exported merged list.

Rows that are not in the previous list are marked NEW (and shown green), so
only those still need entering into Swiss Manager.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import Config
from .loader import LoadError, read_workbook
from .normalize import clean_id, clean_text


@dataclass
class Baseline:
    """The IDs of everyone already present in a previous merged list."""

    path: Path
    rows: int = 0
    ids: dict[str, set[str]] = field(default_factory=dict)
    id_dobs: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    fallback_keys: set[tuple[str, str]] = field(default_factory=set)

    def contains(self, row_ids: dict[str, str], name: str, dob: str) -> bool:
        for column, value in row_ids.items():
            if not value or value not in self.ids.get(column, set()):
                continue
            # Siblings registered under one parent's ID: the ID matches but the
            # player is somebody else, and they still need entering.
            known = {d for d in self.id_dobs.get(column, {}).get(value, set()) if d}
            if dob and known and dob not in known:
                continue
            return True
        # Nobody can be matched on an ID they do not have, so fall back to
        # name + DOB for rows whose IDs are all blank.
        if not any(row_ids.values()):
            return (name.casefold(), dob) in self.fallback_keys
        return False


def load_baseline(path: Path | str, cfg: Config) -> Baseline:
    """Read a previously exported merged .xlsx and index the players in it."""
    path = Path(path)
    if not path.exists():
        raise LoadError(f"{path.name} no longer exists on disk.")
    if path.suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
        raise LoadError(
            f"{path.name}: the previous merged list must be a .xlsx file "
            "produced by this app."
        )

    book = read_workbook(path)
    if not book:
        raise LoadError(f"{path.name} has no sheets.")
    frame = next(iter(book.values()))

    frame.columns = [str(c).strip() for c in frame.columns]
    missing = [c for c in cfg.id_columns if c not in frame.columns]
    if missing or cfg.name_column not in frame.columns:
        raise LoadError(
            f"{path.name} does not look like a merged list from this app "
            f"(no {', '.join(missing or [cfg.name_column])} column). "
            "Choose the .xlsx this app exported previously."
        )

    baseline = Baseline(path=path, rows=len(frame))
    for column in cfg.id_columns:
        values = frame[column].map(lambda v: clean_id(v, cfg.placeholder_ids))
        baseline.ids[column] = {v for v in values if v}

    names = frame[cfg.name_column].map(clean_text)
    dobs = (
        frame["DOB"].map(clean_text)
        if "DOB" in frame.columns
        else pd.Series([""] * len(frame))
    )
    id_frame = frame[cfg.id_columns].map(lambda v: clean_id(v, cfg.placeholder_ids))
    for column in cfg.id_columns:
        baseline.id_dobs[column] = {}
    for position in range(len(frame)):
        row = id_frame.iloc[position]
        if not any(row):
            baseline.fallback_keys.add((names.iloc[position].casefold(), dobs.iloc[position]))
            continue
        for column in cfg.id_columns:
            value = row[column]
            if value:
                baseline.id_dobs[column].setdefault(value, set()).add(dobs.iloc[position])

    return baseline


def apply_status(
    frame: pd.DataFrame, baseline: Baseline | None, cfg: Config
) -> tuple[int, int]:
    """Fill the Status column; returns (new_rows, already_entered_rows).

    With no baseline every row counts as new -- a first run has nothing to
    compare against, which is not an error.
    """
    style = cfg.status
    if frame.empty:
        return 0, 0

    if baseline is None:
        frame[style.column] = style.new_label
        return len(frame), 0

    id_values = {
        column: frame[column].astype(str).tolist() for column in cfg.id_columns
    }
    names = frame[cfg.name_column].astype(str).tolist()
    dobs = frame["DOB"].astype(str).tolist() if "DOB" in frame.columns else [""] * len(frame)

    labels = []
    for position in range(len(frame)):
        row_ids = {column: id_values[column][position] for column in cfg.id_columns}
        known = baseline.contains(row_ids, names[position], dobs[position])
        labels.append(style.existing_label if known else style.new_label)

    frame[style.column] = labels
    new_rows = labels.count(style.new_label)
    return new_rows, len(labels) - new_rows
