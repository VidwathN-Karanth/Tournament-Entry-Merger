"""Loads config/platforms.json and exposes it as light-weight objects."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _bundle_dir() -> Path:
    """Where bundled resources live (the temp unpack dir under PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def config_path() -> Path:
    """Prefer a config/platforms.json sitting next to the .exe, so abbreviations,
    colours and column mappings stay editable after packaging."""
    if getattr(sys, "frozen", False):
        beside_exe = Path(sys.executable).resolve().parent / "config" / "platforms.json"
        if beside_exe.exists():
            return beside_exe
    return _bundle_dir() / "config" / "platforms.json"

def asset_path(name: str) -> Path:
    """A file bundled under assets/ (the app icon, for instance)."""
    return _bundle_dir() / "assets" / name


PAYMENT_DATE = "Payment Date"


@dataclass(frozen=True)
class StatusStyle:
    """The trailing Status column: labels and cell fills."""

    column: str = "Status"
    new_label: str = "NEW"
    existing_label: str = "ALREADY ENTERED"
    new_fill_rgb: str = "FF9BE7A8"
    existing_fill_rgb: str = "FFF0F0F0"


@dataclass(frozen=True)
class Platform:
    key: str
    name: str
    abbrev: str
    ui_color: str
    ui_border: str
    fill_rgb: str
    sheet: str | None
    columns: dict[str, list[str]] = field(default_factory=dict)

    def sources_for(self, canonical: str) -> list[str]:
        return self.columns.get(canonical, [])

    @property
    def has_payment_date(self) -> bool:
        return bool(self.sources_for(PAYMENT_DATE))


@dataclass(frozen=True)
class Config:
    output_columns: list[str]
    id_columns: list[str]
    name_column: str
    placeholder_ids: set[str]
    platforms: dict[str, Platform]
    output_platform_order: list[str] = field(default_factory=list)
    status: StatusStyle = field(default_factory=StatusStyle)

    @property
    def platform_list(self) -> list[Platform]:
        """Declaration order -- drives the left-to-right order of the GUI boxes."""
        return list(self.platforms.values())

    @property
    def output_platform_list(self) -> list[Platform]:
        """The order platform groups appear in the merged sheet.

        Any platform missing from output_platform_order is appended in
        declaration order, so adding a 4th platform can never drop its rows.
        """
        chosen = [
            self.platforms[key]
            for key in self.output_platform_order
            if key in self.platforms
        ]
        chosen += [p for p in self.platform_list if p not in chosen]
        return chosen

    @property
    def output_abbrev_order(self) -> list[str]:
        return [p.abbrev for p in self.output_platform_list]


def load_config(path: Path | str | None = None) -> Config:
    path = Path(path) if path else config_path()
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)

    platforms: dict[str, Platform] = {}
    for entry in raw["platforms"]:
        columns = {
            canonical: ([sources] if isinstance(sources, str) else list(sources))
            for canonical, sources in entry["columns"].items()
        }
        platforms[entry["key"]] = Platform(
            key=entry["key"],
            name=entry["name"],
            abbrev=entry["abbrev"],
            ui_color=entry["ui_color"],
            ui_border=entry["ui_border"],
            fill_rgb=entry["fill_rgb"],
            sheet=entry.get("sheet"),
            columns=columns,
        )

    return Config(
        output_columns=list(raw["output_columns"]),
        id_columns=list(raw["id_columns"]),
        name_column=raw["name_column"],
        placeholder_ids={p.strip().lower() for p in raw["placeholder_ids"]},
        platforms=platforms,
        output_platform_order=list(raw.get("output_platform_order", [])),
        status=StatusStyle(**raw.get("status", {})),
    )
