"""Load each symbol from a TradingView screener export on the chart and record
the Minervini Metrics indicator's output.

Every symbol gets one JSONL record with the raw table rows and data-window
values. When the scan completes, the symbols passing all mandatory criteria are
written to a watchlist (see watchlist.py).

Requires TradingView Desktop running with the "Minervini Metrics" indicator
visible on the active chart.

    uv run minervini-scan                      # newest CSV in data/
    uv run minervini-scan path/to/export.csv --limit 5
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from trading_strategies.strategies.minervini.watchlist import write_watchlist
from trading_strategies.tradingview import cli
from trading_strategies.tradingview.screener import read_screener_csv

STUDY_NAME = "Minervini Metrics"
HERE = Path(__file__).parent
DATA_DIR = HERE / "data"
RESULTS_DIR = HERE / "results"


def read_minervini_table() -> tuple[str, dict[str, str]] | None:
    """Return (ticker in the table header, {criterion: value}), or None if the
    table is not drawn yet."""
    studies = cli.pine_tables(STUDY_NAME)
    if not studies or not studies[0]["tables"]:
        return None
    rows = [r.split(" | ", 1) for r in studies[0]["tables"][0]["rows"]]
    if not rows or len(rows[0]) != 2:
        return None
    (_, header_ticker), *body = rows
    return header_ticker, {r[0].strip(): r[1].strip() for r in body if len(r) == 2}


def ticker_matches(table_ticker: str, symbol: str) -> bool:
    """The table header holds the full ticker ('BATS:MSFT'); the CSV may hold
    just 'MSFT' or 'NASDAQ:MSFT'."""
    def bare(t: str) -> str:
        return t.split(":")[-1].upper()
    return bare(table_ticker) == bare(symbol)


def scan_symbol(symbol: str, timeout: float, poll: float) -> dict:
    """Switch the chart to `symbol` and wait until the indicator has recalculated
    for it, then read the table and data-window values."""
    cli.set_symbol(symbol, wait=False)  # readiness is confirmed below via the table header
    deadline = time.monotonic() + timeout
    last_seen = None
    while True:
        table = read_minervini_table()
        if table is not None:
            last_seen = table[0]
            if ticker_matches(table[0], symbol):
                break
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"table did not update to {symbol} within {timeout}s (still showing {last_seen})"
            )
        time.sleep(poll)

    tickerid, criteria = table
    # The table is drawn from the last bar, but data-window values are for the bar
    # under the chart's crosshair, so they are wrong if the mouse is over the chart.
    # Flag them when their count disagrees with the table's; the table is used for
    # pass/fail either way.
    values = cli.study_values(STUDY_NAME)
    record = {"tickerid": tickerid, "criteria": criteria, "values": values}
    if table_count(criteria) != values_count(values):
        record["values_stale"] = True
    return record


def table_count(criteria: dict[str, str]) -> int | None:
    """Criteria met per the table summary row, e.g. ' (11 of 12)' -> 11."""
    summary = criteria.get("Meet minervini criteria", "")
    try:
        return int(summary.strip(" ()").split(" of ")[0])
    except ValueError:
        return None


def values_count(values: dict[str, str]) -> int | None:
    try:
        return int(float(values["Criteria met"]))
    except (KeyError, ValueError):
        return None


def newest_csv(directory: Path) -> Path:
    csvs = sorted(directory.glob("*.csv"), key=lambda p: p.stat().st_mtime)
    if not csvs:
        sys.exit(f"No CSV files found in {directory}")
    return csvs[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("csv", nargs="?", type=Path,
                        help=f"TradingView screener export (default: newest CSV in {DATA_DIR})")
    parser.add_argument("--out", type=Path, help="JSONL output path (default: results/scan_<timestamp>.jsonl)")
    parser.add_argument("--limit", type=int, help="Only scan the first N symbols")
    parser.add_argument("--timeout", type=float, default=30,
                        help="Seconds to wait for the indicator after each symbol switch (default: 30)")
    parser.add_argument("--poll", type=float, default=0.5, help="Seconds between table reads (default: 0.5)")
    args = parser.parse_args()

    csv_path = args.csv or newest_csv(DATA_DIR)
    rows = read_screener_csv(csv_path)[: args.limit]
    out_path = args.out or RESULTS_DIR / f"scan_{datetime.now():%Y-%m-%d_%H%M%S}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Fail fast if TradingView isn't reachable or the indicator isn't on the chart
    original_symbol = cli.get_symbol()
    if read_minervini_table() is None:
        sys.exit(f'"{STUDY_NAME}" table not found. Add the indicator to the chart and make sure it is visible.')

    print(f"Scanning {len(rows)} symbols from {csv_path.name} -> {out_path}")
    ok = failed = 0
    completed = False
    try:
        with open(out_path, "w") as out:
            for i, row in enumerate(rows, 1):
                symbol = row["Symbol"]
                record = {"symbol": symbol, "scanned_at": datetime.now().isoformat(timespec="seconds")}
                start = time.monotonic()
                try:
                    record.update(scan_symbol(symbol, args.timeout, args.poll))
                    status = f"criteria met: {table_count(record['criteria'])}"
                    if record.get("values_stale"):
                        status += "  (data-window values don't match the table; is the mouse over the chart?)"
                    ok += 1
                except (cli.TvError, TimeoutError) as e:
                    record["error"] = str(e)
                    status = f"ERROR: {e}"
                    failed += 1
                record["screener"] = row
                out.write(json.dumps(record) + "\n")
                out.flush()  # keep partial results if the run is interrupted
                print(f"[{i}/{len(rows)}] {symbol:<8} {status}  ({time.monotonic() - start:.1f}s)")
        completed = True
    except KeyboardInterrupt:
        print(f"\nInterrupted. Build a watchlist from the partial scan with: uv run minervini-watchlist {out_path}")
    finally:
        print(f"Done: {ok} ok, {failed} failed. Restoring chart to {original_symbol}.")
        try:
            cli.set_symbol(original_symbol, wait=False)
        except cli.TvError as e:
            print(f"Could not restore chart symbol: {e}")

    if completed:
        write_watchlist(out_path)


if __name__ == "__main__":
    main()
