"""Workbooks that openpyxl refuses to parse must still be readable.

Registration portals generate their .xlsx exports with non-Excel libraries,
which regularly emit style definitions openpyxl rejects -- a bare <fill/>
raises TypeError("expected <class 'openpyxl.styles.fills.Fill'>") before a
single cell is read. The values are fine, so the app falls back to a reader
that ignores styling.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.baseline import load_baseline
from pipeline.config import load_config
from pipeline.loader import load_file, read_workbook
from pipeline.normalize import normalize_frame
from pipeline.writer import write_xlsx

CFG = load_config()
SAMPLES = ROOT / "samples"


def break_styles(source: Path, target: Path) -> Path:
    """Copy an .xlsx, injecting the empty <fill/> that openpyxl chokes on."""
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(
        target, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/styles.xml":
                text = data.decode("utf-8")
                text = text.replace('<fills count="2">', '<fills count="3"><fill/>', 1)
                data = text.encode("utf-8")
            zout.writestr(item, data)
    return target


class TestUnparseableStyles(unittest.TestCase):
    def setUp(self):
        if not (SAMPLES / "CircleChess.xlsx").exists():
            self.skipTest("sample files missing -- run samples/make_samples.py")
        self.tmp = tempfile.TemporaryDirectory()
        self.broken = break_styles(
            SAMPLES / "CircleChess.xlsx", Path(self.tmp.name) / "Portal Export.xlsx"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_openpyxl_alone_really_does_fail(self):
        """Guards the test itself: if this stops failing, the fixture is stale."""
        with self.assertRaises(Exception):
            pd.read_excel(self.broken, engine="openpyxl")

    def test_read_workbook_recovers(self):
        book = read_workbook(self.broken)
        self.assertIn("Participants", book)

    def test_the_platform_loader_recovers(self):
        frame = load_file(self.broken, CFG.platforms["circlechess"])
        self.assertIn("fide_id", frame.columns)
        self.assertEqual(len(frame), 5)

    def test_rows_normalize_normally_afterwards(self):
        frame = load_file(self.broken, CFG.platforms["circlechess"])
        result = normalize_frame(frame, CFG.platforms["circlechess"], CFG, "Portal.xlsx")
        self.assertEqual(result.rows_in, 5)
        self.assertEqual(result.missing_columns, [])

    def test_a_previous_merged_list_recovers_too(self):
        good = Path(self.tmp.name) / "Merged.xlsx"
        frame = load_file(SAMPLES / "CircleChess.xlsx", CFG.platforms["circlechess"])
        merged = normalize_frame(frame, CFG.platforms["circlechess"], CFG, "x").frame
        write_xlsx(merged[CFG.output_columns], good, CFG)

        broken_baseline = break_styles(good, Path(self.tmp.name) / "Merged Broken.xlsx")
        baseline = load_baseline(broken_baseline, CFG)
        self.assertEqual(baseline.rows, 5)

    def test_a_genuinely_corrupt_file_still_errors(self):
        junk = Path(self.tmp.name) / "not-really.xlsx"
        junk.write_bytes(b"this is not a workbook at all")
        with self.assertRaises(Exception):
            load_file(junk, CFG.platforms["circlechess"])


if __name__ == "__main__":
    unittest.main()
