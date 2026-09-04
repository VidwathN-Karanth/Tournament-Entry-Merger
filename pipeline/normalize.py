"""Turn a raw platform export into canonical 13-column rows."""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass

import pandas as pd

from .config import PAYMENT_DATE, Config, Platform
from .loader import LoadError

SORT_KEY = "__sort_name"
DATE_KEY = "__payment_date"
SOURCE_KEY = "__source_file"

_WHITESPACE = re.compile(r"\s+")
_TRAILING_FLOAT = re.compile(r"^(-?\d+)\.0+$")
_AMOUNT_JUNK = re.compile(r"[^\d.\-]")
# Excel hands back ISO timestamps; those are year-first, never day-first.
_ISO_DATE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}")
_DATE_SEP = re.compile(r"[/\-.]")


class ShapeError(LoadError):
    """The file loaded fine but does not carry this platform's columns."""


@dataclass
class FileResult:
    frame: pd.DataFrame
    rows_in: int
    missing_columns: list[str]


def clean_text(value: object) -> str:
    """Trim, collapse internal whitespace, and undo float-ified integers."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = _WHITESPACE.sub(" ", str(value)).strip()
    if text.lower() in {"nan", "nat", "none"}:
        return ""
    match = _TRAILING_FLOAT.match(text)
    return match.group(1) if match else text


def clean_id(value: object, placeholders: set[str]) -> str:
    """Clean an ID and blank it out if it is a placeholder (see plan section 2)."""
    text = clean_text(value)
    return "" if text.lower() in placeholders else text


def clean_amount(value: object) -> object:
    """Return a number when the fee parses, otherwise the cleaned text."""
    text = clean_text(value)
    if not text:
        return ""
    stripped = _AMOUNT_JUNK.sub("", text)
    try:
        number = float(stripped)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def parse_date(value: object, day_first: bool | None = None) -> pd.Timestamp | None:
    text = clean_text(value)
    if not text:
        return None
    if day_first is None or _ISO_DATE.match(text):
        day_first = not _ISO_DATE.match(text)
    with warnings.catch_warnings():
        # The column's format is chosen deliberately in infer_day_first;
        # pandas warning about each value that disagrees is just noise.
        warnings.simplefilter("ignore", UserWarning)
        stamp = pd.to_datetime(text, errors="coerce", dayfirst=day_first)
        if stamp is pd.NaT or pd.isna(stamp):
            stamp = pd.to_datetime(text, errors="coerce")
    return None if pd.isna(stamp) else stamp


def infer_day_first(values) -> bool | None:
    """Decide whether a whole column is DD/MM or MM/DD.

    A single value like "9/4/2026" is genuinely ambiguous, but a column
    almost never is: one "31/08" proves day-first, one "8/31" proves
    month-first. Guessing per value silently mixes the two -- ChessWorld
    writes M/D/YYYY, so day-first turned 9/4/2026 into 9 April.
    Returns None when the column gives no evidence either way.
    """
    day_first = month_first = 0
    for value in values:
        text = clean_text(value)
        if not text or _ISO_DATE.match(text):
            continue
        parts = _DATE_SEP.split(text.split()[0])
        if len(parts) < 2:
            continue
        try:
            first, second = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if first > 12:
            day_first += 1
        if second > 12:
            month_first += 1

    if day_first and not month_first:
        return True
    if month_first and not day_first:
        return False
    return None  # no evidence, or genuinely mixed formats


def parse_date_series(values: pd.Series) -> pd.Series:
    """Parse a date column using one format decided from the whole column."""
    day_first = infer_day_first(values)
    if day_first is None:
        day_first = True  # Indian exports are day-first far more often than not
    return values.map(lambda v: parse_date(v, day_first))


def format_payment(stamp: pd.Timestamp | None) -> str:
    """Render a payment timestamp, keeping the time only when the source had one."""
    if stamp is None or stamp is pd.NaT or pd.isna(stamp):
        return ""
    if (stamp.hour, stamp.minute, stamp.second) == (0, 0, 0):
        return stamp.strftime("%d-%m-%Y")
    if stamp.second:
        return stamp.strftime("%d-%m-%Y %H:%M:%S")
    return stamp.strftime("%d-%m-%Y %H:%M")


def clean_dob(value: object) -> str:
    """Normalize recognisable dates to DD-MM-YYYY; leave anything else as typed."""
    text = clean_text(value)
    if not text:
        return ""
    stamp = parse_date(text)
    return stamp.strftime("%d-%m-%Y") if stamp is not None else text


def clean_dob_series(values: pd.Series) -> pd.Series:
    """Normalize a DOB column, deciding DD/MM vs MM/DD once for the column."""
    day_first = infer_day_first(values)
    if day_first is None:
        day_first = True

    def one(value: object) -> str:
        text = clean_text(value)
        if not text:
            return ""
        stamp = parse_date(text, day_first)
        return stamp.strftime("%d-%m-%Y") if stamp is not None else text

    return values.map(one)


def resolve_columns(frame: pd.DataFrame, platform: Platform) -> dict[str, str | None]:
    """Match this platform's expected source headers against the file's headers."""
    lookup = {str(col).strip().lower(): col for col in frame.columns}
    resolved: dict[str, str | None] = {}
    for canonical, candidates in platform.columns.items():
        resolved[canonical] = next(
            (lookup[c.strip().lower()] for c in candidates if c.strip().lower() in lookup),
            None,
        )
    return resolved


def exact_header_score(frame: pd.DataFrame, platform: Platform) -> int:
    """How many of `platform`'s source headers appear verbatim in `frame`."""
    headers = {str(col).strip() for col in frame.columns}
    return sum(
        1
        for sources in platform.columns.values()
        for source in sources
        if source.strip() in headers
    )


def check_right_box(frame: pd.DataFrame, platform: Platform, cfg: Config, source_name: str):
    """Reject a file whose headers clearly belong to a different platform.

    Column matching is case-insensitive so that minor header drift within one
    platform still works -- but the three platforms differ mostly by case, so a
    verbatim-header fingerprint is what actually tells the boxes apart.
    """
    mine = exact_header_score(frame, platform)
    for other in cfg.platform_list:
        if other.key == platform.key:
            continue
        theirs = exact_header_score(frame, other)
        if theirs >= mine + 2 and theirs >= len(other.columns) / 2:
            raise ShapeError(
                f"{source_name or 'This file'} looks like a {other.name} export, "
                f"not a {platform.name} one. Drop it in the {other.name} box instead."
            )


def normalize_frame(
    frame: pd.DataFrame,
    platform: Platform,
    cfg: Config,
    source_name: str = "",
) -> FileResult:
    """Map, clean, and reduce one loaded file to the canonical output columns."""
    check_right_box(frame, platform, cfg, source_name)
    resolved = resolve_columns(frame, platform)

    expected = [c for c, sources in platform.columns.items() if sources]
    missing = [c for c in expected if resolved.get(c) is None]

    if resolved.get(cfg.name_column) is None:
        raise ShapeError(
            f"{source_name or 'This file'} has no "
            f"'{platform.columns[cfg.name_column][0]}' column, so it does not look like a "
            f"{platform.name} export. Found: {', '.join(map(str, frame.columns[:8]))}"
            + ("..." if len(frame.columns) > 8 else "")
        )
    if len(missing) > len(expected) / 2:
        raise ShapeError(
            f"{source_name or 'This file'} is missing {len(missing)} of "
            f"{len(expected)} expected {platform.name} columns "
            f"({', '.join(missing[:6])}). Is it in the right box?"
        )

    out = pd.DataFrame(index=frame.index)
    out["Platform"] = platform.abbrev

    for canonical in cfg.output_columns:
        if canonical in {"Platform", PAYMENT_DATE, cfg.status.column}:
            # Platform is fixed, Payment Date is derived below, and Status is
            # filled in against the previous merged list once rows are merged.
            continue
        column = resolved.get(canonical)
        values = frame[column] if column is not None else pd.Series("", index=frame.index)
        if canonical in cfg.id_columns:
            out[canonical] = values.map(lambda v: clean_id(v, cfg.placeholder_ids))
        elif canonical == "DOB":
            out[canonical] = clean_dob_series(values)
        elif canonical == "Entry Fee":
            out[canonical] = values.map(clean_amount)
        else:
            out[canonical] = values.map(clean_text)

    date_column = resolved.get(PAYMENT_DATE)
    if date_column is not None:
        out[DATE_KEY] = parse_date_series(frame[date_column])
    else:
        out[DATE_KEY] = None
    out[PAYMENT_DATE] = out[DATE_KEY].map(format_payment)
    out[cfg.status.column] = ""

    out[SORT_KEY] = out[cfg.name_column].str.casefold()
    out[SOURCE_KEY] = source_name

    # Drop rows that carry no name and no identifiers at all (trailing blank rows).
    identifying = out[[cfg.name_column, *cfg.id_columns]].apply(
        lambda col: col.astype(str).str.strip()
    )
    out = out[identifying.ne("").any(axis=1)].reset_index(drop=True)

    return FileResult(frame=out, rows_in=len(out), missing_columns=missing)
