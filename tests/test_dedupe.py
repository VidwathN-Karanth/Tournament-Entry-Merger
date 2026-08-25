"""Unit tests for normalization, ordering and de-duplication (plan sections 2, 6, 7)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import load_config
from pipeline.dedupe import merge
from pipeline.config import PAYMENT_DATE
from pipeline.normalize import (
    DATE_KEY,
    SORT_KEY,
    clean_dob,
    clean_id,
    format_payment,
    parse_date,
)

CFG = load_config()


def row(platform="CW", name="X", fide="", aicf="", ksca="", date=None):
    data = {column: "" for column in CFG.output_columns}
    data["Platform"] = platform
    data["Student Name"] = name
    data["FIDE ID"] = fide
    data["AICF ID"] = aicf
    data["KSCA ID"] = ksca
    stamp = parse_date(date) if date else None
    data[DATE_KEY] = stamp
    data[PAYMENT_DATE] = format_payment(stamp)
    data[SORT_KEY] = name.casefold()
    return data


def frame(*rows):
    return pd.DataFrame(list(rows))


class TestPlaceholders(unittest.TestCase):
    def test_placeholders_become_blank(self):
        for value in ["", "-", "0", "00", " N/A ", "unrated", "AICF ID not available"]:
            self.assertEqual(clean_id(value, CFG.placeholder_ids), "", value)

    def test_real_ids_survive(self):
        self.assertEqual(clean_id(" 25601234 ", CFG.placeholder_ids), "25601234")

    def test_float_ids_lose_their_decimal(self):
        self.assertEqual(clean_id("25601234.0", CFG.placeholder_ids), "25601234")

    def test_dob_normalizes_excel_timestamps(self):
        self.assertEqual(clean_dob("2010-05-12 00:00:00"), "12-05-2010")

    def test_dob_keeps_unparseable_text(self):
        self.assertEqual(clean_dob("not a date"), "not a date")


class TestDedupe(unittest.TestCase):
    def test_blank_never_matches_blank(self):
        result, stats = merge([frame(row(name="A"), row(name="B"))], CFG)
        self.assertEqual(len(result), 2)
        self.assertEqual(stats.total_dropped, 0)

    def test_match_on_each_id_type(self):
        for field, value in [("fide", "111"), ("aicf", "222"), ("ksca", "333")]:
            with self.subTest(field=field):
                rows = frame(
                    row(name="First", **{field: value}),
                    row(name="Second", **{field: value}),
                )
                result, stats = merge([rows], CFG)
                self.assertEqual(len(result), 1)
                self.assertEqual(result.iloc[0]["Student Name"], "First")
                self.assertEqual(stats.total_dropped, 1)

    def test_cross_field_match_is_independent(self):
        rows = frame(row(name="A", fide="111"), row(name="B", aicf="111"))
        result, _ = merge([rows], CFG)
        self.assertEqual(len(result), 2)

    def test_earliest_payment_wins(self):
        rows = frame(
            row(name="Late", fide="111", date="07-08-2026 18:40"),
            row(name="Early", fide="111", date="01-08-2026 09:00"),
        )
        result, _ = merge([rows], CFG)
        self.assertEqual(list(result["Student Name"]), ["Early"])

    def test_dated_row_beats_undated_row(self):
        rows = frame(
            row(platform="CF", name="Undated", fide="111"),
            row(platform="CW", name="Dated", fide="111", date="09-09-2026"),
        )
        result, _ = merge([rows], CFG)
        self.assertEqual(list(result["Platform"]), ["CW"])


class TestOrdering(unittest.TestCase):
    def test_platform_groups_follow_the_configured_order(self):
        self.assertEqual(CFG.output_abbrev_order, ["CW", "CC", "CF"])

    def test_groups_are_chessworld_then_circlechess_then_chessfee(self):
        rows = frame(
            row(platform="CF", name="Fee One"),
            row(platform="CC", name="Circle One"),
            row(platform="CW", name="World One", date="09-08-2026"),
            row(platform="CF", name="Fee Two"),
            row(platform="CC", name="Circle Two"),
            row(platform="CW", name="World Two", date="02-08-2026"),
        )
        result, _ = merge([rows], CFG)
        self.assertEqual(list(result["Platform"]), ["CW", "CW", "CC", "CC", "CF", "CF"])

    def test_dated_first_then_input_order_within_a_group(self):
        rows = frame(
            row(platform="CF", name="Zara"),
            row(platform="CF", name="Aarav"),
            row(platform="CW", name="Later", date="09-08-2026"),
            row(platform="CW", name="Sooner", date="02-08-2026"),
        )
        result, stats = merge([rows], CFG)
        self.assertEqual(
            list(result["Student Name"]), ["Sooner", "Later", "Zara", "Aarav"]
        )
        self.assertEqual((stats.dated_rows, stats.undated_rows), (2, 2))

    def test_undated_rows_are_never_re_sorted(self):
        rows = frame(
            row(platform="CC", name="Zoya"),
            row(platform="CC", name="Bhavya"),
            row(platform="CC", name="Aarav"),
        )
        result, _ = merge([rows], CFG)
        self.assertEqual(list(result["Student Name"]), ["Zoya", "Bhavya", "Aarav"])

    def test_input_order_is_kept_across_several_files_in_one_box(self):
        first = frame(row(platform="CF", name="File1 Row1"), row(platform="CF", name="File1 Row2"))
        second = frame(row(platform="CF", name="File2 Row1"))
        result, _ = merge([first, second], CFG)
        self.assertEqual(
            list(result["Student Name"]), ["File1 Row1", "File1 Row2", "File2 Row1"]
        )

    def test_a_missing_platform_group_is_skipped(self):
        rows = frame(row(platform="CF", name="Only"), row(platform="CC", name="Other"))
        result, _ = merge([rows], CFG)
        self.assertEqual(list(result["Platform"]), ["CC", "CF"])

    def test_unparseable_date_falls_into_the_undated_group(self):
        rows = frame(
            row(platform="CW", name="Bad Date", date="not a date"),
            row(platform="CW", name="Good Date", date="02-08-2026"),
        )
        result, stats = merge([rows], CFG)
        self.assertEqual(list(result["Student Name"]), ["Good Date", "Bad Date"])
        self.assertEqual((stats.dated_rows, stats.undated_rows), (1, 1))


class TestPaymentColumn(unittest.TestCase):
    def test_time_is_kept_when_the_source_has_one(self):
        self.assertEqual(format_payment(parse_date("05-08-2026 10:15")), "05-08-2026 10:15")

    def test_seconds_are_kept_when_present(self):
        self.assertEqual(
            format_payment(parse_date("05-08-2026 10:15:42")), "05-08-2026 10:15:42"
        )

    def test_date_only_source_stays_date_only(self):
        self.assertEqual(format_payment(parse_date("05-08-2026")), "05-08-2026")

    def test_undated_rows_get_a_blank_payment_cell(self):
        result, _ = merge([frame(row(platform="CF", name="A"))], CFG)
        self.assertEqual(result.iloc[0][PAYMENT_DATE], "")

    def test_column_survives_the_merge(self):
        rows = frame(
            row(platform="CW", name="Paid", date="03-08-2026 09:00"),
            row(platform="CF", name="Unpaid"),
        )
        result, _ = merge([rows], CFG)
        self.assertEqual(
            list(result[PAYMENT_DATE]), ["03-08-2026 09:00", ""]
        )


class TestOutputShape(unittest.TestCase):
    def test_fifteen_columns_platform_first_status_last(self):
        result, _ = merge([frame(row())], CFG)
        self.assertEqual(list(result.columns), CFG.output_columns)
        self.assertEqual(len(CFG.output_columns), 15)
        self.assertEqual(CFG.output_columns[0], "Platform")
        self.assertEqual(CFG.output_columns[-1], CFG.status.column)
        self.assertEqual(CFG.output_columns[-2], PAYMENT_DATE)

    def test_no_inputs_still_yields_the_header(self):
        result, stats = merge([], CFG)
        self.assertEqual(list(result.columns), CFG.output_columns)
        self.assertEqual(stats.final_rows, 0)


if __name__ == "__main__":
    unittest.main()
