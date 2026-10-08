import json
import re
from pathlib import Path

out_lines = []
for f in Path(__file__).parent.joinpath("allure-results").glob("*-result.json"):
    d = json.loads(f.read_text(encoding="utf-8"))
    params = {p["name"]: p.get("value") for p in d.get("parameters") or []}
    cid = str(params.get("case_id", "")).strip("'\"")
    first = ((d.get("statusDetails") or {}).get("message") or "").splitlines()
    first = first[0] if first else ""
    m = re.search(r"element not in POM: '([^']+)'", first)
    if m:
        reason = "POM缺失: " + m.group(1)
    elif "text not containing" in first:
        reason = "断言文本不匹配"
    else:
        reason = first[:120]
    out_lines.append(f"{cid}: {reason}")

text = "\n".join(sorted(out_lines)) + "\n"
Path(__file__).parent.joinpath("_fail_summary.txt").write_text(text, encoding="utf-8")
print(text)
