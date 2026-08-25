"""Command-line front end for the merge pipeline (plan milestone 1)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.config import load_config
from pipeline.merger import merge_sources
from pipeline.writer import WriteError, write_xlsx


def build_parser(cfg) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="merge",
        description="Merge tournament entry exports into one .xlsx.",
    )
    for platform in cfg.platform_list:
        parser.add_argument(
            f"--{platform.key}",
            metavar="FILE",
            nargs="*",
            default=[],
            help=f"{platform.name} export(s) [{platform.abbrev}]",
        )
    parser.add_argument("-o", "--output", required=True, help="output .xlsx path")
    parser.add_argument(
        "-p",
        "--previous",
        metavar="FILE",
        help="a merged .xlsx exported earlier; only players missing from it "
        "are marked NEW (optional)",
    )
    parser.add_argument(
        "--report", action="store_true", help="list every dropped duplicate"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    args = build_parser(cfg).parse_args(argv)

    sources = {p.key: getattr(args, p.key.replace("-", "_")) for p in cfg.platform_list}
    if not any(sources.values()):
        print("No input files given.", file=sys.stderr)
        return 2

    result = merge_sources(
        sources,
        cfg,
        progress=lambda msg, _f: print(f"  {msg}", file=sys.stderr),
        previous=args.previous,
    )

    if result.baseline_error:
        print(f"ERROR  previous list: {result.baseline_error}", file=sys.stderr)
    for report in result.errors:
        print(f"ERROR  {report.path.name}: {report.error}", file=sys.stderr)
    for report in result.warnings:
        print(
            f"WARN   {report.path.name}: missing columns "
            f"{', '.join(report.missing_columns)} (left blank)",
            file=sys.stderr,
        )

    stats = result.stats
    print()
    for platform in cfg.output_platform_list:
        rows = stats.rows_by_platform.get(platform.abbrev, 0)
        dropped = stats.dropped_by_platform.get(platform.abbrev, 0)
        print(f"{platform.name:<12} {rows:>5} rows in, {dropped:>4} duplicate(s) dropped")
    print(f"{'Ordering':<12} {stats.dated_rows:>5} dated, {stats.undated_rows:>5} undated")
    print(f"{'Output':<12} {stats.final_rows:>5} rows")
    if result.baseline is not None:
        print(
            f"{'Previous':<12} {result.baseline.rows:>5} rows in "
            f"{result.baseline.path.name}"
        )
        print(
            f"{'Status':<12} {stats.new_rows:>5} NEW, "
            f"{stats.existing_rows} already entered"
        )
    else:
        print(f"{'Status':<12} {stats.new_rows:>5} NEW (no previous list given)")

    if args.report:
        for hit in stats.duplicates:
            print(
                f"  dup: {hit.platform} {hit.name} == {hit.kept_platform} "
                f"{hit.kept_name} (on {hit.matched_on} {hit.value})"
            )

    path = write_xlsx(result.frame, Path(args.output), cfg)
    print(f"\nWrote {path}")
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
