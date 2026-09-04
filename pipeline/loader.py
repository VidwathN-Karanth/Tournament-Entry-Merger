"""Read a single entry file, knowing up-front which platform it belongs to."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import Platform

CSV_SUFFIXES = {".csv"}
EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}


class LoadError(Exception):
    """A file could not be read, or does not look like this platform's export."""


def _read_csv(path: Path) -> pd.DataFrame:
    last: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, dtype=str, keep_default_na=False, encoding=encoding)
        except UnicodeDecodeError as exc:
            last = exc
        except pd.errors.EmptyDataError as exc:
            raise LoadError(f"{path.name} is empty.") from exc
        except Exception as exc:  # malformed rows, bad delimiters, ...
            raise LoadError(f"{path.name} could not be parsed as CSV: {exc}") from exc
    raise LoadError(f"{path.name} could not be decoded as text: {last}")


def read_workbook(path: Path) -> dict:
    """Read every sheet of an .xlsx, tolerating workbooks openpyxl chokes on.

    Portals that generate their exports with a non-Excel library often emit
    style definitions openpyxl rejects outright (a bare <fill/> raises
    "expected <class 'openpyxl.styles.fills.Fill'>"). The cell values are
    perfectly fine, so fall back to a reader that ignores styling entirely.
    """
    errors = []
    for engine in (None, "calamine"):
        try:
            return pd.read_excel(
                path,
                sheet_name=None,
                dtype=str,
                keep_default_na=False,
                **({"engine": engine} if engine else {}),
            )
        except ImportError:
            continue  # calamine not installed in this environment
        except Exception as exc:
            errors.append(exc)
    raise LoadError(f"{path.name} could not be read as a workbook: {errors[0]}")


def _read_excel(path: Path, platform: Platform) -> pd.DataFrame:
    book = read_workbook(path)

    if not book:
        raise LoadError(f"{path.name} has no sheets.")

    if platform.sheet:
        wanted = platform.sheet.strip().lower()
        for sheet_name, frame in book.items():
            if str(sheet_name).strip().lower() == wanted:
                return frame
        raise LoadError(
            f"{path.name} has no '{platform.sheet}' sheet "
            f"(found: {', '.join(map(str, book))}). "
            f"{platform.name} files must contain that sheet."
        )

    return next(iter(book.values()))


def load_file(path: Path | str, platform: Platform) -> pd.DataFrame:
    """Return the raw rows of `path`, read with `platform`'s conventions."""
    path = Path(path)
    if not path.exists():
        raise LoadError(f"{path.name} no longer exists on disk.")

    suffix = path.suffix.lower()
    if suffix in CSV_SUFFIXES:
        frame = _read_csv(path)
    elif suffix in EXCEL_SUFFIXES:
        frame = _read_excel(path, platform)
    else:
        raise LoadError(
            f"{path.name}: unsupported file type '{suffix or path.name}'. "
            "Expected a .csv or .xlsx file."
        )

    frame.columns = [str(c).strip() for c in frame.columns]
    return frame
