"""Tests for file loading, column mapping and wrong-box detection."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.config import load_config
from pipeline.loader import LoadError, load_file
from pipeline.normalize import ShapeError, normalize_frame

CFG = load_config()
SAMPLES = ROOT / "samples"


def sample(name: str) -> Path:
    path = SAMPLES / name
    if not path.exists():
        raise unittest.SkipTest(f"{name} missing -- run samples/make_samples.py")
    return path


class TestLoader(unittest.TestCase):
    def test_circlechess_uses_only_the_participants_sheet(self):
        frame = load_file(sample("CircleChess.xlsx"), CFG.platforms["circlechess"])
        self.assertIn("fide_id", frame.columns)
        self.assertNotIn("rating", frame.columns)  # NationalRatingList is skipped

    def test_missing_participants_sheet_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "book.xlsx"
            pd.DataFrame({"name": ["a"]}).to_excel(path, sheet_name="Sheet1", index=False)
            with self.assertRaises(LoadError) as ctx:
                load_file(path, CFG.platforms["circlechess"])
        self.assertIn("Participants", str(ctx.exception))

    def test_unknown_suffix_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.docx"
            path.write_text("not a spreadsheet", encoding="utf-8")
            with self.assertRaises(LoadError):
                load_file(path, CFG.platforms["chessfee"])

    def test_missing_file_is_rejected(self):
        with self.assertRaises(LoadError):
            load_file(SAMPLES / "does-not-exist.csv", CFG.platforms["chessfee"])


class TestWrongBox(unittest.TestCase):
    def test_circlechess_file_in_the_chessfee_box(self):
        frame = load_file(sample("CircleChess.xlsx"), CFG.platforms["circlechess"])
        with self.assertRaises(ShapeError) as ctx:
            normalize_frame(frame, CFG.platforms["chessfee"], CFG, "CircleChess.xlsx")
        self.assertIn("CircleChess box", str(ctx.exception))

    def test_chessfee_file_in_the_circlechess_box(self):
        frame = load_file(sample("ChessFee.csv"), CFG.platforms["chessfee"])
        with self.assertRaises(ShapeError):
            normalize_frame(frame, CFG.platforms["circlechess"], CFG, "ChessFee.csv")

    def test_unrelated_table_is_rejected(self):
        frame = pd.DataFrame({"foo": ["a"], "bar": ["b"]})
        with self.assertRaises(ShapeError):
            normalize_frame(frame, CFG.platforms["chessworld"], CFG, "junk.csv")


class TestMapping(unittest.TestCase):
    def test_each_sample_maps_to_the_output_columns(self):
        for key, name in [
            ("chessfee", "ChessFee.csv"),
            ("chessworld", "ChessWorld.csv"),
            ("circlechess", "CircleChess.xlsx"),
        ]:
            with self.subTest(platform=key):
                platform = CFG.platforms[key]
                raw = load_file(sample(name), platform)
                result = normalize_frame(raw, platform, CFG, name)
                self.assertEqual(result.missing_columns, [])
                self.assertEqual(result.rows_in, 5)
                for column in CFG.output_columns:
                    self.assertIn(column, result.frame.columns)
                self.assertTrue((result.frame["Platform"] == platform.abbrev).all())

    def test_only_chessworld_carries_payment_dates(self):
        self.assertTrue(CFG.platforms["chessworld"].has_payment_date)
        self.assertFalse(CFG.platforms["chessfee"].has_payment_date)
        self.assertFalse(CFG.platforms["circlechess"].has_payment_date)


if __name__ == "__main__":
    unittest.main()
