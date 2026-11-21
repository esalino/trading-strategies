"""Build the final watchlist from a scan: keep only symbols that pass every
mandatory Minervini criterion, ranked by the optional criteria they meet.

Writes a .txt file of comma-separated tickers, best first, that TradingView can
import as a watchlist, and a .json file with the same symbols in the same order
plus their scan details.

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
#
# Each maps to a short name for the scan log.
MANDATORY_CRITERIA = {
    "MA 150 is above MA 200": "MA150>MA200",
    "MA 50 is above MA 150": "MA50>MA150",
    "Current price is trading above MA 50": "price>MA50",
    "MA 200 is trending": "MA200 rising",
    "Current price is 25% above 52 weeks low": "25% above 52W low",
    "Current price is within 25% of 52 week high": "near 52W high",
    "Weighted RS at least": "RS",
    "Diluted EPS up at least": "EPS growth",
    "Avg volume": "volume",
}

# Rows 10-15, matched the same way, with a short name for the printed summary.
# Symbols passing every mandatory criterion are ranked by how many of these they
# meet; ties go to the symbol meeting the criteria listed first.
OPTIONAL_CRITERIA = {
    "Diluted EPS YoY growth trending up": "EPS trend",
    "Revenue YoY growth trending up": "revenue trend",
    "Net margin YoY growth trending up": "net margin trend",
    "Latest qtr EPS beat estimate": "EPS beat",
    "Latest qtr diluted EPS positive": "EPS positive",
    "Latest qtr revenue up at least": "revenue growth",
}


def load_scan(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def passes(record: dict, prefix: str) -> bool:
    """Whether the table row whose label starts with `prefix` says 'yes'.

    Raises KeyError if the table lacks that row, which means the scan ran
    against an older version of the indicator.
    """
    matches = [value for label, value in record["criteria"].items() if label.startswith(prefix)]
    if len(matches) != 1:
        raise KeyError(f"expected one table row starting {prefix!r}, found {len(matches)}; "
                       "was the chart's indicator up to date?")
    return matches[0].startswith("yes")


def failed_mandatory(record: dict) -> list[str]:
    """Names of the mandatory criteria this symbol fails (empty = passes all)."""
    return [prefix for prefix in MANDATORY_CRITERIA if not passes(record, prefix)]


def optional_met(record: dict) -> list[bool]:
    """Pass/fail of each optional criterion, in priority order."""
    return [passes(record, prefix) for prefix in OPTIONAL_CRITERIA]


def rank_key(record: dict) -> tuple:
    """Sort key putting the most optional criteria met first, ties broken by
    priority order (a symbol meeting the EPS trend beats one that doesn't)."""
    met = optional_met(record)
    return (-sum(met), *(not m for m in met))


def build_watchlist(records: list[dict]) -> tuple[list[dict], dict[str, list[str]], dict[str, str]]:
    """Split scan records into (passed, {symbol: failed criteria}, {symbol: error}).

    `passed` is ranked best first (see rank_key).
    """
    passed, failed, errors = [], {}, {}
    for r in records:
        if "error" in r:
            errors[r["symbol"]] = r["error"]
            continue
        try:
            fails = failed_mandatory(r)
            optional_met(r)  # check the optional rows exist before ranking
        except KeyError as e:
            errors[r["symbol"]] = str(e)
            continue
        if fails:
            failed[r["symbol"]] = fails
        else:
            passed.append(r)
    passed.sort(key=rank_key)  # stable: equal ranks keep scan order
    return passed, failed, errors


def optional_summary(record: dict) -> str:
    """e.g. 'optional 3/6 (EPS trend, revenue trend, EPS beat)'."""
    met = [name for name, m in zip(OPTIONAL_CRITERIA.values(), optional_met(record)) if m]
    return f"optional {len(met)}/{len(OPTIONAL_CRITERIA)}" + (f" ({', '.join(met)})" if met else "")


def scan_status(record: dict) -> str:
    """One-line verdict for the scan log, using the same checks as the watchlist, e.g.
    'PASS  mandatory 9/9, optional 2/6 (EPS trend, EPS beat)' or
    'DROP  mandatory 8/9 (failed: volume), optional 1/6 (EPS beat)'."""
    try:
        fails = failed_mandatory(record)
        optional = optional_summary(record)
    except KeyError as e:
        return f"ERROR {e}"
    mandatory = f"mandatory {len(MANDATORY_CRITERIA) - len(fails)}/{len(MANDATORY_CRITERIA)}"
    if fails:
        mandatory += " (failed: " + ", ".join(MANDATORY_CRITERIA[f] for f in fails) + ")"
    return f"{'DROP' if fails else 'PASS'}  {mandatory}, {optional}"


def watchlist_entry(rank: int, record: dict) -> dict:
    """A passing symbol for the JSON watchlist: its rank and optional criteria up
    front, then everything the scan recorded (table rows, data-window values, CSV row)."""
    optional = dict(zip(OPTIONAL_CRITERIA.values(), optional_met(record)))
    return {
        "rank": rank,
        "tickerid": record["tickerid"],
        "symbol": record["symbol"],
        "optional_met_count": sum(optional.values()),
        "optional_met": optional,
        **{k: v for k, v in record.items() if k not in ("tickerid", "symbol")},
    }


def write_watchlist(scan_path: Path) -> Path:
    """Filter a scan file, print a summary and write the watchlist next to it, best
    first: <scan>_watchlist.txt for TradingView and <scan>_watchlist.json with details."""
    passed, failed, errors = build_watchlist(load_scan(scan_path))

    out_path = scan_path.with_name(f"{scan_path.stem}_watchlist.txt")
    out_path.write_text(",".join(r["tickerid"] for r in passed) + "\n")
    json_path = out_path.with_suffix(".json")
    entries = [watchlist_entry(rank, r) for rank, r in enumerate(passed, 1)]
    json_path.write_text(json.dumps(entries, indent=2) + "\n")

    total = len(passed) + len(failed) + len(errors)
    print(f"\nWatchlist: {len(passed)} of {total} symbols pass all {len(MANDATORY_CRITERIA)} mandatory criteria"
          + (", best first" if passed else ""))
    for rank, r in enumerate(passed, 1):
        print(f"  {rank:>3}. {r['tickerid']:<16} {optional_summary(r)}")
    if failed:
        print("\nMandatory criteria failed (symbols can fail several):")
        for name, n in Counter(c for fails in failed.values() for c in fails).most_common():
            print(f"  {n:>4}  {name}")
    if errors:
        print(f"\n{len(errors)} symbols could not be checked:")
        for symbol, err in errors.items():
            print(f"  {symbol}: {err}")
    print(f"\nWrote {out_path}\n  and {json_path}")
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
