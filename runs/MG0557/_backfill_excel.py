"""Deprecated helper — use framework backfill via CLI.

  python main.py excel-backfill --req MG0557
  # or automatic after: python main.py run --req MG0557
"""

from __future__ import annotations

from framework.runner.excel_backfill import backfill_requirement_excel


def main() -> None:
    summary = backfill_requirement_excel("MG0557")
    print(summary)


if __name__ == "__main__":
    main()
