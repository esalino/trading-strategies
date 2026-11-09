# trading-strategies

Python scripts that help automate running trading strategies with
[TradingView](https://www.tradingview.com/). Each strategy pairs a TradingView
indicator (Pine Script) with Python scripts that drive TradingView Desktop
through [tradingview-mcp](https://github.com/tradesdontlie/tradingview-mcp). The
scripts load symbols on the chart, read the indicator's results, and filter and
rank the stocks.

## Setup

Install [uv](https://docs.astral.sh/uv/), then install the project and its
dependencies:

```sh
uv sync
```

Commands then run with `uv run <command>`, for example `uv run minervini-scan`.

For VS Code debugging, copy `.vscode/launch-example.json` to
`.vscode/launch.json`. `launch.json` is gitignored, so local changes stay local.

## Layout

- `src/trading_strategies/tradingview/`: shared helpers for driving TradingView
  and reading its exports
- `src/trading_strategies/strategies/<name>/`: one folder per strategy, with its
  indicator, scripts, data and README

## Strategies

- [Minervini](src/trading_strategies/strategies/minervini/README.md): Mark
  Minervini's trend template plus earnings and liquidity checks
