"""Build the final watchlist from a scan: keep only symbols that pass every
mandatory Minervini criterion.

Writes a .txt file of comma-separated tickers that TradingView can import as a
watchlist.

    uv run minervini-watchlist                       # newest scan in results/
    uv run minervini-watchlist results/scan_X.jsonl
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"

# Rows 1-9 of the minervini_metrics.pine table, matched by the start of each
# row's label. Only the start is matched because the rest of a label can include
# thresholds set in the indicator's inputs ("Weighted RS at least 10%").
#
# Pass/fail comes from the table, not the data-window values: the table is always
# drawn from the last bar, while data-window values follow the chart's crosshair
# and are wrong if the mouse is over the chart during a scan.
MANDATORY_CRITERIA = (
    "MA 150 is above MA 200",
    "MA 50 is above MA 150",
    "Current price is trading above MA 50",
    "MA 200 is trending",
    "Current price is 25% above 52 weeks low",
    "Current price is within 25% of 52 week high",
    "Weighted RS at least",
    "Diluted EPS up at least",
    "Avg volume",
)


def load_scan(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def failed_mandatory(record: dict) -> list[str]:
    """Names of the mandatory criteria this symbol fails (empty = passes all).

    Raises KeyError if the table lacks any mandatory row, which means the scan
    ran against an older version of the indicator.
    """
    rows = record["criteria"]
    results = {}
    for prefix in MANDATORY_CRITERIA:
        matches = [value for label, value in rows.items() if label.startswith(prefix)]
        if len(matches) != 1:
            raise KeyError(f"expected one table row starting {prefix!r}, found {len(matches)}; "
                           "was the chart's indicator up to date?")
        results[prefix] = matches[0].startswith("yes")
    return [prefix for prefix, passed in results.items() if not passed]


def criteria_met(record: dict) -> str:
    """The table's summary, e.g. '11 of 12'."""
    return record["criteria"].get("Meet minervini criteria", "?").strip(" ()")


def build_watchlist(records: list[dict]) -> tuple[list[dict], dict[str, list[str]], dict[str, str]]:
    """Split scan records into (passed, {symbol: failed criteria}, {symbol: error})."""
    passed, failed, errors = [], {}, {}
    for r in records:
        if "error" in r:
            errors[r["symbol"]] = r["error"]
            continue
        try:
            fails = failed_mandatory(r)
        except KeyError as e:
            errors[r["symbol"]] = str(e)
            continue
        if fails:
            failed[r["symbol"]] = fails
        else:
            passed.append(r)
    return passed, failed, errors


def write_watchlist(scan_path: Path) -> Path:
    """Filter a scan file, print a summary and write <scan>_watchlist.txt next to it."""
    passed, failed, errors = build_watchlist(load_scan(scan_path))

    out_path = scan_path.with_name(f"{scan_path.stem}_watchlist.txt")
    out_path.write_text(",".join(r["tickerid"] for r in passed) + "\n")

    total = len(passed) + len(failed) + len(errors)
    print(f"\nWatchlist: {len(passed)} of {total} symbols pass all {len(MANDATORY_CRITERIA)} mandatory criteria")
    for r in passed:
        print(f"  {r['tickerid']:<16} criteria met: {criteria_met(r)}")
    if failed:
        print("\nMandatory criteria failed (symbols can fail several):")
        for name, n in Counter(c for fails in failed.values() for c in fails).most_common():
            print(f"  {n:>4}  {name}")
    if errors:
        print(f"\n{len(errors)} symbols could not be checked:")
        for symbol, err in errors.items():
            print(f"  {symbol}: {err}")
    print(f"\nWrote {out_path}")
    return out_path


def newest_scan(directory: Path) -> Path:
    scans = sorted(directory.glob("scan_*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not scans:
        sys.exit(f"No scan_*.jsonl files found in {directory}")
    return scans[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scan", nargs="?", type=Path,
                        help=f"Scan results JSONL (default: newest in {RESULTS_DIR})")
    args = parser.parse_args()
    write_watchlist(args.scan or newest_scan(RESULTS_DIR))


if __name__ == "__main__":
    main()
