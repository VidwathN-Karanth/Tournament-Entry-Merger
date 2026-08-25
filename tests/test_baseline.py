"""Tests for the Status column and comparison against a previous merged list."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.baseline import apply_status, load_baseline
from pipeline.config import load_config
from pipeline.loader import LoadError
from pipeline.merger import merge_sources
from pipeline.writer import write_xlsx

CFG = load_config()
STATUS = CFG.status.column
NEW = CFG.status.new_label
OLD = CFG.status.existing_label
SAMPLES = ROOT / "samples"


def entries(*rows) -> pd.DataFrame:
    """Build a frame shaped like a merged output."""
    frame = pd.DataFrame([{c: "" for c in CFG.output_columns} for _ in rows])
    for index, values in enumerate(rows):
        for column, value in values.items():
            frame.at[index, column] = value
    return frame


class TestStatusWithoutBaseline(unittest.TestCase):
    def test_everyone_is_new_when_no_previous_list_is_given(self):
        frame = entries({"Student Name": "A"}, {"Student Name": "B"})
        new, old = apply_status(frame, None, CFG)
        self.assertEqual((new, old), (2, 0))
        self.assertEqual(list(frame[STATUS]), [NEW, NEW])

    def test_an_empty_merge_is_not_an_error(self):
        frame = pd.DataFrame(columns=CFG.output_columns)
        self.assertEqual(apply_status(frame, None, CFG), (0, 0))


class TestStatusAgainstBaseline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous = Path(self.tmp.name) / "Yesterday.xlsx"
        write_xlsx(
            entries(
                {"Student Name": "Ravi Kumar", "FIDE ID": "111", "Platform": "CW"},
                {"Student Name": "Meera Iyer", "AICF ID": "222", "Platform": "CC"},
                {"Student Name": "No Id Player", "DOB": "01-01-2010", "Platform": "CF"},
            ),
            self.previous,
            CFG,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_known_players_are_marked_already_entered(self):
        base = load_baseline(self.previous, CFG)
        frame = entries(
            {"Student Name": "Ravi Kumar", "FIDE ID": "111"},
            {"Student Name": "Brand New", "FIDE ID": "999"},
        )
        new, old = apply_status(frame, base, CFG)
        self.assertEqual((new, old), (1, 1))
        self.assertEqual(list(frame[STATUS]), [OLD, NEW])

    def test_any_of_the_three_ids_is_enough_to_match(self):
        base = load_baseline(self.previous, CFG)
        frame = entries({"Student Name": "Meera I.", "AICF ID": "222"})
        apply_status(frame, base, CFG)
        self.assertEqual(list(frame[STATUS]), [OLD])

    def test_id_less_player_matches_on_name_and_dob(self):
        base = load_baseline(self.previous, CFG)
        frame = entries(
            {"Student Name": "no id player", "DOB": "01-01-2010"},
            {"Student Name": "No Id Player", "DOB": "02-02-2011"},
        )
        apply_status(frame, base, CFG)
        self.assertEqual(list(frame[STATUS]), [OLD, NEW])

    def test_a_player_with_an_id_never_falls_back_to_name_matching(self):
        base = load_baseline(self.previous, CFG)
        frame = entries(
            {"Student Name": "No Id Player", "DOB": "01-01-2010", "FIDE ID": "555"}
        )
        apply_status(frame, base, CFG)
        self.assertEqual(list(frame[STATUS]), [NEW])

    def test_baseline_row_count_is_reported(self):
        self.assertEqual(load_baseline(self.previous, CFG).rows, 3)


class TestBaselineErrors(unittest.TestCase):
    def test_a_missing_file_is_rejected(self):
        with self.assertRaises(LoadError):
            load_baseline(SAMPLES / "nope.xlsx", CFG)

    def test_a_csv_is_rejected(self):
        with self.assertRaises(LoadError):
            load_baseline(SAMPLES / "ChessFee.csv", CFG)

    def test_a_workbook_that_is_not_a_merged_list_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "random.xlsx"
            pd.DataFrame({"foo": ["a"]}).to_excel(path, index=False)
            with self.assertRaises(LoadError) as ctx:
                load_baseline(path, CFG)
        self.assertIn("merged list", str(ctx.exception))


class TestEndToEnd(unittest.TestCase):
    """Yesterday's export becomes today's baseline."""

    def test_second_run_only_flags_the_players_that_were_added(self):
        for name in ["ChessFee.csv", "ChessWorld.csv", "CircleChess.xlsx"]:
            if not (SAMPLES / name).exists():
                self.skipTest("sample files missing -- run samples/make_samples.py")

        sources = {
            "chessfee": [SAMPLES / "ChessFee.csv"],
            "chessworld": [SAMPLES / "ChessWorld.csv"],
            "circlechess": [SAMPLES / "CircleChess.xlsx"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            day_one = Path(tmp) / "Day1.xlsx"
            first = merge_sources(sources, CFG)
            self.assertEqual(first.stats.new_rows, first.stats.final_rows)
            write_xlsx(first.frame, day_one, CFG)

            # Same inputs the next day: nothing has actually been added.
            second = merge_sources(sources, CFG, previous=day_one)
            self.assertEqual(second.stats.new_rows, 0)
            self.assertEqual(second.stats.existing_rows, second.stats.final_rows)
            self.assertTrue((second.frame[STATUS] == OLD).all())

    def test_a_broken_previous_file_is_reported_not_raised(self):
        sources = {"chessworld": [SAMPLES / "ChessWorld.csv"]}
        if not (SAMPLES / "ChessWorld.csv").exists():
            self.skipTest("sample files missing -- run samples/make_samples.py")
        result = merge_sources(sources, CFG, previous=SAMPLES / "nope.xlsx")
        self.assertIsNotNone(result.baseline_error)
        self.assertTrue((result.frame[STATUS] == NEW).all())


if __name__ == "__main__":
    unittest.main()
