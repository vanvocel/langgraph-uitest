"""MG0557: Excel → NL only. YAML must come from LLM compile.

  python runs/MG0557/_regen_nl_from_excel.py
  python main.py compile --req MG0557 --llm deepseek
"""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("_regen_nl_from_excel.py")), run_name="__main__")
