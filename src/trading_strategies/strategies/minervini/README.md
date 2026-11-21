# Minervini

Picks stocks using Mark Minervini's trend template plus some earnings and
liquidity checks. The **Minervini Metrics** TradingView indicator
([minervini_metrics.pine](minervini_metrics.pine)) checks each stock against the
criteria. A Python scan loads each stock from a starting list into TradingView,
reads the indicator's results, and keeps the stocks that pass every mandatory
criterion.

## Prerequisites

- TradingView Desktop running and connected through
  [tradingview-mcp](https://github.com/tradesdontlie/tradingview-mcp), cloned to
  `~/Repos/tradingview-mcp`. Set the `TV_CLI` environment variable if it lives elsewhere.
  - The scan uses a `--no-wait` option on `tv symbol` that is a local change to
    that clone, not in the upstream repo yet. Without it the scan fails with an
    unknown-option error.
- The **Minervini Metrics** indicator added to the active chart and visible.
- [uv](https://docs.astral.sh/uv/) installed.

## Process

### 1. Set up the starting watchlist in TradingView

Build a screener in TradingView that narrows the market down to candidates, then
export the results as CSV into `data/` (create the folder if it doesn't exist;
git ignores it, since each user downloads their own lists).

_Details of the screener filters to come._

### 2. Scan and filter

```sh
uv run minervini-scan                       # uses the newest CSV in data/
uv run minervini-scan path/to/export.csv    # or a specific export
uv run minervini-scan --limit 5             # quick test on the first 5 stocks
```

This loads each stock on the chart (about 1 second each) and reads the
indicator's table. The chart goes back to its original stock when the scan
finishes.

**Keep the mouse off the chart while the scan runs.** Pass/fail comes from the
table, which is unaffected. But the data-window values saved with each stock
follow the crosshair, and a stock is flagged if they don't match the table.

When the scan finishes, it keeps only the stocks that pass all of the mandatory
criteria, which are rows 1-9 of the indicator's table:

1. MA 150 above MA 200
2. MA 50 above MA 150
3. Price above MA 50
4. MA 200 rising every day for at least 22 days in a row (1 month)
5. Price at least 25% above its 52-week low
6. Price within 25% of its 52-week high
7. Weighted RS vs SPY at least 10%
8. Diluted EPS up at least 20% year over year (latest quarter)
9. 30-day average volume at least 200K shares

Rows 10-15 are not mandatory. Instead they rank the stocks that pass: the
more of them a stock meets, the higher it goes. Ties are broken in this order
of priority:

10. EPS growth trending up
11. Revenue growth trending up
12. Net margin growth trending up
13. Latest quarter's EPS beat the analysts' estimate
14. Latest quarter's diluted EPS is positive (a profit, not a loss)
15. Latest quarter's revenue up at least 15% year over year

So a stock meeting 10 and 13 ranks above one meeting 11 and 12. Stocks that
tie on every row keep their order from the CSV.

The criteria lists are `MANDATORY_CRITERIA` and `OPTIONAL_CRITERIA` (in
priority order) in [watchlist.py](watchlist.py).

To rebuild the watchlist from an existing scan without loading the stocks again
(for example after an interrupted run):

```sh
uv run minervini-watchlist                          # newest scan in results/
uv run minervini-watchlist results/scan_<timestamp>.jsonl
```

### 3. Review the results

Both files go to [results/](results/), which git ignores:

- `scan_<timestamp>.jsonl` has one line per stock: the indicator's table rows,
  its data-window values, and the original CSV row.
- `scan_<timestamp>_watchlist.txt` lists the stocks that passed, comma-separated
  and best ranked first. Import it into TradingView as a watchlist.
- `scan_<timestamp>_watchlist.json` has the same stocks in the same order, as
  an array with each stock's rank, which optional criteria it meets, and its
  full scan record (table rows, data-window values and CSV row).

The scan also prints the passing stocks in rank order with the optional
criteria each one meets, and how many stocks failed each mandatory criterion.
