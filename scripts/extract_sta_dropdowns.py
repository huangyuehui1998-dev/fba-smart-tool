"""从 STA 模板的数据验证里抽取下拉取值。

仓库内模板目前只有数值验证。脚本会把 formula1 记下来；
如果验证类型是 list，再把取值写进 columns。
空白模板不进仓库，只更新 config/sta_dropdowns.default.json 里的清单。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "backend" / "templates" / "Send to Amazon表格.xlsx"
OUT = ROOT / "backend" / "config" / "sta_dropdowns.default.json"


def extract(path: Path) -> dict:
    wb = load_workbook(path, data_only=False)
    found = []
    columns: dict[str, list[str]] = {}
    for ws in wb.worksheets:
        validations = getattr(ws, "data_validations", None)
        if not validations:
            continue
        for dv in validations.dataValidation:
            formula = str(dv.formula1 or "")
            found.append({"type": dv.type, "formula1": formula, "sqref": str(dv.sqref)})
            if dv.type == "list" and formula:
                raw = formula[1:] if formula.startswith("=") else formula
                values = [part.strip().strip('"') for part in raw.split(",") if part.strip()]
                columns[str(dv.sqref)] = values
    return {"template_filename": path.name, "data_validations_found": found, "list_columns": columns}


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TEMPLATE
    print(json.dumps(extract(path), ensure_ascii=False, indent=2))
    if OUT.is_file():
        current = json.loads(OUT.read_text(encoding="utf-8"))
        for key in ("贴标", "空", "由卖家提供"):
            blob = json.dumps(current, ensure_ascii=False)
            if key not in blob:
                raise SystemExit(f"清单里缺少已知取值：{key}")


if __name__ == "__main__":
    main()
