"""Thin wrapper around the `tv` CLI from the tradingview-mcp repo.

Every call to the CLI goes through `tv()`, so if the CLI's command names or
flags change, this module is the only place that needs updating.
"""

import json
import os
import subprocess
from pathlib import Path

DEFAULT_TV_CLI = Path.home() / "Repos" / "tradingview-mcp" / "src" / "cli" / "index.js"
TV_CLI = Path(os.environ.get("TV_CLI", DEFAULT_TV_CLI))


class TvError(RuntimeError):
    """The CLI failed, or reported success: false."""


def tv(*args: str, timeout: float = 60) -> dict:
    """Run a `tv` CLI command and return its parsed JSON output."""
    try:
        proc = subprocess.run(
            ["node", str(TV_CLI), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise TvError(f"tv {' '.join(args)} timed out after {timeout}s") from e

    if proc.returncode != 0:
        # The CLI prints {"success": false, "error": ...} to stderr; exit 2 = connection failure
        detail = proc.stderr.strip() or proc.stdout.strip()
        try:
            detail = json.loads(detail).get("error", detail)
        except (json.JSONDecodeError, AttributeError):
            pass
        raise TvError(f"tv {' '.join(args)} exited {proc.returncode}: {detail}")

    result = json.loads(proc.stdout)
    if not result.get("success", False):
        raise TvError(f"tv {' '.join(args)} failed: {result.get('error', result)}")
    return result


def get_symbol() -> str:
    """The chart's current symbol, e.g. 'BATS:MSFT'."""
    return tv("symbol")["symbol"]


def set_symbol(symbol: str, wait: bool = True) -> dict:
    """Switch the chart to `symbol`.

    With wait=True, tradingview-mcp waits for the chart to report ready, but its
    readiness check is currently broken and always takes its full 10s timeout.
    With wait=False it returns right away (needs the local `--no-wait` patch to
    tradingview-mcp); the caller must verify the switch itself.
    """
    return tv("symbol", symbol, *(["--no-wait"] if not wait else []))


def pine_tables(study_filter: str) -> list[dict]:
    """Tables drawn by Pine studies whose name contains `study_filter`.

    Each item is {"name": study name, "tables": [{"rows": ["cell | cell", ...]}]}.
    """
    return tv("data", "tables", "-f", study_filter)["studies"]


def study_values(study_name: str | None = None) -> dict:
    """Data-window values for every visible study, keyed by study name.

    If `study_name` is given, only that study's values are returned (an empty
    dict if it is not on the chart).
    """
    studies = {s["name"]: s["values"] for s in tv("values")["studies"]}
    if study_name is None:
        return studies
    return studies.get(study_name, {})
