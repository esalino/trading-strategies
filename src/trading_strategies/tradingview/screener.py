"""Read stock screener CSV exports downloaded from TradingView."""

import csv
from pathlib import Path


def read_screener_csv(path: Path) -> list[dict[str, str]]:
    """Return one dict per row, keyed by the CSV's column headers.

    Every export has a 'Symbol' column; the other columns depend on how the
    screener was set up.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if rows and "Symbol" not in rows[0]:
        raise ValueError(f"{path} has no 'Symbol' column; is it a TradingView screener export?")
    return rows
