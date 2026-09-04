"""Regressions found against real ChessFee and ChessWorld exports (Sept 2026).

Both bugs were silent: the merge completed and looked fine, but the output
was wrong. Neither would have been caught without live data.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.config import PAYMENT_DATE, load_config
from pipeline.dedupe import merge, same_person
from pipeline.normalize import (
    DATE_KEY,
    SORT_KEY,
    clean_dob_series,
    infer_day_first,
    parse_date_series,
)

CFG = load_config()


def row(platform="CW", name="X", fide="", aicf="", ksca="", dob="", date=None):
    from pipeline.normalize import format_payment, parse_date

    data = {c: "" for c in CFG.output_columns}
    data.update(
        {
            "Platform": platform,
            "Student Name": name,
            "FIDE ID": fide,
            "AICF ID": aicf,
            "KSCA ID": ksca,
            "DOB": dob,
        }
    )
    stamp = parse_date(date) if date else None
    data[DATE_KEY] = stamp
    data[PAYMENT_DATE] = format_payment(stamp)
    data[SORT_KEY] = name.casefold()
    return data


class TestDateFormatInference(unittest.TestCase):
    """ChessWorld writes M/D/YYYY. Day-first turned 9/4/2026 into 9 April."""

    def test_month_first_column_is_detected(self):
        # 8/31 can only be month-first
        column = pd.Series(["9/4/2026", "9/3/2026", "8/31/2026", "9/1/2026"])
        self.assertIs(infer_day_first(column), False)

    def test_day_first_column_is_detected(self):
        # 25/05 can only be day-first -- this is the ChessFee DOB shape
        column = pd.Series(["25/05/2018", "10/04/1974", "01/04/2008"])
        self.assertIs(infer_day_first(column), True)

    def test_ambiguous_column_gives_no_verdict(self):
        self.assertIsNone(infer_day_first(pd.Series(["1/2/2026", "3/4/2026"])))

    def test_iso_values_are_not_evidence(self):
        self.assertIsNone(infer_day_first(pd.Series(["2004-12-08", "2014-08-25"])))

    def test_the_whole_column_parses_month_first_together(self):
        column = pd.Series(["9/4/2026", "8/31/2026", "9/1/2026"])
        parsed = parse_date_series(column)
        self.assertEqual(
            [p.strftime("%d-%m-%Y") for p in parsed],
            ["04-09-2026", "31-08-2026", "01-09-2026"],
        )

    def test_ambiguous_dates_follow_their_unambiguous_neighbours(self):
        """9/4 alone is a coin flip; next to 8/31 it is settled."""
        alone = parse_date_series(pd.Series(["9/4/2026"]))[0]
        in_context = parse_date_series(pd.Series(["9/4/2026", "8/31/2026"]))[0]
        self.assertEqual(alone.strftime("%d-%m-%Y"), "09-04-2026")
        self.assertEqual(in_context.strftime("%d-%m-%Y"), "04-09-2026")

    def test_day_first_dob_column_keeps_its_meaning(self):
        cleaned = clean_dob_series(pd.Series(["25/05/2018", "10/04/1974"]))
        self.assertEqual(list(cleaned), ["25-05-2018", "10-04-1974"])

    def test_payment_dates_sort_chronologically(self):
        rows = pd.DataFrame(
            [
                row(name="Later", date="9/4/2026"),
                row(name="Earlier", date="8/31/2026"),
            ]
        )
        # emulate a real column parse, as normalize_frame does
        rows[DATE_KEY] = parse_date_series(pd.Series(["9/4/2026", "8/31/2026"]))
        result, _ = merge([rows], CFG)
        self.assertEqual(list(result["Student Name"]), ["Earlier", "Later"])


class TestSiblingsSharingAnId(unittest.TestCase):
    """Parents register several children under one ID. Both children paid."""

    def test_same_id_different_dob_are_two_people(self):
        self.assertFalse(same_person("26-07-2017", "22-12-2013"))

    def test_same_id_same_dob_is_one_person(self):
        self.assertTrue(same_person("26-07-2017", "26-07-2017"))

    def test_a_blank_dob_does_not_contradict_the_id(self):
        self.assertTrue(same_person("", "22-12-2013"))
        self.assertTrue(same_person("26-07-2017", ""))

    def test_siblings_on_a_shared_fide_id_are_both_kept(self):
        rows = pd.DataFrame(
            [
                row(name="Monish B", fide="429054974", dob="26-07-2017"),
                row(name="Medansh B", fide="429054974", dob="22-12-2013"),
            ]
        )
        result, stats = merge([rows], CFG)
        self.assertEqual(len(result), 2)
        self.assertEqual(stats.total_dropped, 0)
        self.assertEqual(len(stats.shared_ids), 1)
        self.assertEqual(stats.shared_ids[0].column, "FIDE ID")

    def test_siblings_on_a_shared_aicf_id_are_both_kept(self):
        rows = pd.DataFrame(
            [
                row(name="Shriyan Rai", fide="564060608", aicf="356709KA2025", dob="19-01-2016"),
                row(name="Rishwin Rai", fide="564060446", aicf="356709KA2025", dob="24-02-2020"),
            ]
        )
        result, stats = merge([rows], CFG)
        self.assertEqual(len(result), 2)
        self.assertEqual(len(stats.shared_ids), 1)

    def test_a_genuine_duplicate_is_still_collapsed(self):
        rows = pd.DataFrame(
            [
                row(platform="CW", name="Ravi Kumar", fide="25601234", dob="12-05-2010"),
                row(platform="CF", name="Ravi Kumar", fide="25601234", dob="12-05-2010"),
            ]
        )
        result, stats = merge([rows], CFG)
        self.assertEqual(len(result), 1)
        self.assertEqual(stats.total_dropped, 1)
        self.assertEqual(stats.shared_ids, [])

    def test_a_duplicate_with_one_dob_missing_is_still_collapsed(self):
        rows = pd.DataFrame(
            [
                row(platform="CW", name="Ravi Kumar", fide="25601234", dob="12-05-2010"),
                row(platform="CF", name="Ravi Kumar", fide="25601234", dob=""),
            ]
        )
        result, _ = merge([rows], CFG)
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
