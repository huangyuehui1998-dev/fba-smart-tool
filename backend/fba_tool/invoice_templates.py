"""S4 发票模板映射：8 套货代发票/下单模板（T1–T8）→ 统一的票级数据。

- 映射在 config/invoice_template_map.json；用户配置目录放同名文件可按模板 id 覆盖任意字段（可配置）。
- detect_template：按工作表名 + 关键表头打分，唯一满分时自动选；否则 ambiguous=True，由用户手选（template_id）。
- parse_invoice_file：按映射读出票（FBA、仓库、箱号区间、数量、申报单价、重量），数量/重量口径按配置换算成单箱重。
- reconcile_with_csv：和亚马逊货件 CSV 交叉核对（仓库、箱数、数量、单箱重）；口径对不上时自动换成能对上的口径并留下提示。
  依据：D-2026-10-16-08（用户：数据可能有错，严谨分析后按正确的做）、D-2026-10-16-09（4 个待确认点的核对结论）。
"""
from __future__ import annotations

import io
import json
import re
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fba_tool.app_paths import bundled_config_dir

CONFIG_NAME = "invoice_template_map.json"
QTY_MEANINGS = ("per_box", "row_total")
WEIGHT_MEANINGS = ("per_box", "per_unit", "range_total", "ticket_total")
WAREHOUSE_PREFER = ("filename", "sheet")
BOX_COUNT_SOURCES = ("forecast_if_conflict", "range")
OVERRIDE_KEYS = ("qty_meaning", "weight_meaning", "warehouse_prefer", "box_count_source")
_WH_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{3}[0-9])(?![A-Z0-9])")
_FBA_RE = re.compile(r"^FBA[0-9A-Z]{8,}$")
CSV_DECIDES = "csv_decides"
WEIGHT_MATCH_TOLERANCE = Decimal("0.02")  # 和 CSV Σ单箱重相差 2% 以内算对得上


# ---------------- 配置 ----------------
def _user_config_path() -> Optional[Path]:
    try:
        from fba_tool.app_paths import resolve_config_read

        return resolve_config_read(CONFIG_NAME)
    except Exception:  # noqa: BLE001
        return None


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"配置文件格式错误：{Path(path).name} 第 {exc.lineno} 行第 {exc.colno} 列（{exc.msg}），请修正或删除后重试") from exc
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误：{Path(path).name} 顶层应是 JSON 对象")
    return data


def _load_config() -> Dict[str, Any]:
    cfg = _read_json(bundled_config_dir() / CONFIG_NAME)
    p = _user_config_path()
    if p is not None and Path(p).is_file() and Path(p).resolve() != (bundled_config_dir() / CONFIG_NAME).resolve():
        user = _read_json(Path(p))
        if not isinstance(user.get("templates", {}), dict):
            raise ValueError(f"配置文件格式错误：{Path(p).name} 的 templates 应是对象")
        for tid, patch in (user.get("templates") or {}).items():
            base = cfg["templates"].setdefault(tid, {})
            base.update(patch)
    return cfg


def list_templates() -> List[Dict[str, Any]]:
    cfg = _load_config()
    out = []
    for tid, t in cfg["templates"].items():
        base = cfg["templates"].get(t.get("parse_as") or tid, t)
        item = {"id": tid, **{k: v for k, v in t.items() if k not in ("columns", "fields", "invoice", "packing")}}
        for k in OVERRIDE_KEYS:
            item.setdefault(k, base.get(k))
        out.append(item)
    return out


def _template(cfg: Dict[str, Any], tid: str) -> Dict[str, Any]:
    if tid not in cfg["templates"]:
        raise ValueError(f"没有这个模板：{tid}（可选 {'、'.join(cfg['templates'])}）")
    return cfg["templates"][tid]


# ---------------- 读表 ----------------
def norm(text: Any) -> str:
    s = str(text if text is not None else "")
    s = s.replace("（", "(").replace("）", ")").replace("\xa0", " ")
    return re.sub(r"[\s*]+", "", s)


def _workbook(data: bytes, file_name: str):
    import openpyxl

    try:
        return openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"无法读取 Excel：{file_name or '文件'}（{exc.__class__.__name__}）") from exc


class _Book:
    def __init__(self, data: bytes, file_name: str):
        wb = _workbook(data, file_name)
        self.names = [n.replace("\xa0", " ").strip() for n in wb.sheetnames]
        self.rows: Dict[str, List[Tuple[Any, ...]]] = {}
        for raw, ws in zip(self.names, wb.worksheets):
            rows = []
            for r in ws.iter_rows(values_only=True):
                rows.append(tuple(v.strip() if isinstance(v, str) else v for v in r))
            while rows and not any(v not in (None, "") for v in rows[-1]):
                rows.pop()
            self.rows[raw] = rows
        wb.close()

    def sheet(self, t: Dict[str, Any]) -> List[Tuple[Any, ...]]:
        if "sheet" in t:
            name = t["sheet"]
            for n in self.names:
                if norm(n) == norm(name):
                    return self.rows[n]
            raise ValueError(f"找不到工作表「{name}」")
        return self.rows[self.names[int(t.get("sheet_index", 0))]]

    def has_label(self, label: str, max_rows: int = 40) -> bool:
        key = norm(label)
        return any(norm(v).startswith(key) for rows in self.rows.values() for r in rows[:max_rows] for v in r if isinstance(v, str))


# ---------------- 识别 ----------------
def _score(book: _Book, t: Dict[str, Any]) -> float:
    det = t.get("detect") or {}
    checks: List[bool] = []
    have = {norm(n) for n in book.names}
    checks += [norm(s) in have for s in det.get("sheets", [])]
    checks += [book.has_label(l) for l in det.get("labels", [])]
    return round(sum(checks) / len(checks), 3) if checks else 0.0


def _detect(book: _Book, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """唯一满分才自动选。T7（same_as T5）和 T5 结构相同、永远同分：S8 起按“有没有数据”自动定（有数据=T5），其它打平仍由用户手选。"""
    cands = []
    for tid, t in cfg["templates"].items():
        target = (t.get("detect") or {}).get("same_as")
        score = _score(book, cfg["templates"][target]) if target else _score(book, t)
        cands.append({"template_id": tid, "name": t.get("name", ""), "score": score})
    cands.sort(key=lambda c: -c["score"])
    full = [c for c in cands if c["score"] >= 1.0]
    tid = full[0]["template_id"] if len(full) == 1 else None
    msg = ""
    # S8 D3：T5 和它的空白版 T7 结构相同、永远同分。有数据 → T5；没数据 → T7（空白模板）。其它打平仍让用户手选。
    if tid is None and len(full) == 2:
        ids = {c["template_id"] for c in full}
        alias = {k: (v.get("detect") or {}).get("same_as") for k, v in cfg["templates"].items()}
        pair = [k for k in ids if alias.get(k) in ids]
        if len(pair) == 1:
            blank_id, base_id = pair[0], alias[pair[0]]
            has = _has_data(book, cfg["templates"][base_id])
            tid = base_id if has else blank_id
            msg = (f"{base_id} 和 {blank_id}（{base_id} 的空白版）结构相同；文件里" + ("有数据，按 " + base_id if has else "没有数据，按空白模板 " + blank_id)
                   + " 识别，如不对可手动选择模板")
            return {"template_id": tid, "ambiguous": False, "candidates": cands[:4], "tied": sorted(ids), "message": msg,
                    "auto_resolved": True}
    if not tid:
        if len(full) > 1:
            names = "、".join(f"{c['template_id']}（{c['name']}）" for c in full)
            blank = any(not _has_data(book, cfg["templates"][(cfg["templates"][c["template_id"]].get("detect") or {}).get("same_as") or c["template_id"]])
                        for c in full)
            msg = f"有 {len(full)} 套模板同时满分：{names}，不自动选，请手动选择模板" + ("（文件里没有数据，像是空白模板）" if blank else "")
        else:
            msg = "认不出唯一的模板，请手动选择模板"
    return {"template_id": tid, "ambiguous": tid is None, "candidates": cands[:4], "tied": [c["template_id"] for c in full] if len(full) > 1 else [],
            "message": msg}


def detect_template(data: bytes, file_name: str = "") -> Dict[str, Any]:
    return _detect(_Book(data, file_name), _load_config())


# ---------------- 解析 ----------------
def _find_header(rows, label: str) -> int:
    key = norm(label)
    for i, r in enumerate(rows[:60]):
        if any(norm(v).startswith(key) for v in r if isinstance(v, str)):
            return i
    raise ValueError(f"找不到表头「{label}」")


def _columns(header: Tuple[Any, ...], mapping: Dict[str, str]) -> Dict[str, int]:
    heads = [norm(h) for h in header]
    out: Dict[str, int] = {}
    for field, label in mapping.items():
        key = norm(label)
        idx = next((i for i, h in enumerate(heads) if h == key), None)
        if idx is None:
            idx = next((i for i, h in enumerate(heads) if h and h.startswith(key)), None)
        if idx is not None:
            out[field] = idx
    return out


def _field(rows, spec: Dict[str, Any], stop: int) -> Any:
    key = norm(spec["label"])
    for exact in (True, False):
        for i, r in enumerate(rows[:stop]):
            for j, v in enumerate(r):
                if not isinstance(v, str):
                    continue
                n = norm(v)
                if (n == key or n.rstrip(":：") == key) if exact else n.startswith(key):
                    if spec.get("at") == "below":
                        nxt = rows[i + 1] if i + 1 < len(rows) else ()
                        return nxt[j] if j < len(nxt) else None
                    return next((x for x in r[j + 1:] if x not in (None, "")), None)
    return None


def _has_data(book: _Book, t: Dict[str, Any]) -> bool:
    try:
        rows = book.sheet(t)
        h = _find_header(rows, t["header_label"])
    except ValueError:
        return False
    return any(any(v not in (None, "") for v in r) for r in rows[h + 1:])


def parse_box_range(v: Any) -> List[int]:
    """箱号区间：1-2 / 1~3 / 1,2,3 / 3 / 21~21。"""
    if v in (None, ""):
        return []
    if isinstance(v, (int, float)):
        return [int(v)]
    s = str(v).replace("～", "~").replace("，", ",").replace("－", "-").replace(" ", "")
    out: List[int] = []
    for part in s.split(","):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)[-~](\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out += list(range(min(a, b), max(a, b) + 1))
        elif part.isdigit():
            out.append(int(part))
        else:
            raise ValueError(f"箱号写法认不出：{v}")
    return out


def _dec(v: Any) -> Optional[Decimal]:
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v).replace(",", "").strip())
    except Exception:  # noqa: BLE001
        return None


def _num(d: Optional[Decimal]) -> Optional[float]:
    return None if d is None else float(d)


def _txt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _issue(code: str, message: str, **extra) -> Dict[str, Any]:
    return {"code": code, "message": message, **extra}


def _file_warehouse(file_name: str) -> str:
    found = list(dict.fromkeys(_WH_RE.findall(Path(file_name or "").stem.upper())))
    return found[0] if len(found) == 1 else ""


def _split(v: Any, seps: str) -> List[str]:
    s = _txt(v)
    if not s:
        return []
    return [x.strip() for x in re.split("[" + re.escape(seps) + "]", s) if x.strip()]


def _effective(t: Dict[str, Any], overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    eff = {k: t.get(k) for k in OVERRIDE_KEYS}
    for k, v in (overrides or {}).items():
        if k not in OVERRIDE_KEYS:
            raise ValueError(f"不能覆盖的配置项：{k}")
        eff[k] = v
    for k, allowed in (("qty_meaning", QTY_MEANINGS), ("weight_meaning", WEIGHT_MEANINGS),
                       ("warehouse_prefer", WAREHOUSE_PREFER), ("box_count_source", BOX_COUNT_SOURCES)):
        if k == "weight_meaning" and eff.get(k) in (None, "", CSV_DECIDES):
            eff[k] = None  # 不默认任何含义，由货件 CSV 校验决定（D-09 第 2 点重写）
            continue
        if eff.get(k) not in allowed:
            raise ValueError(f"{k} 只能是 {' / '.join(allowed)}：{eff.get(k)}")
    return eff


def _table_rows(rows, t) -> List[Dict[str, Any]]:
    h = _find_header(rows, t["header_label"])
    cols = _columns(rows[h], t["columns"])
    out = []
    for i, r in enumerate(rows[h + 1:], start=h + 2):
        rec = {f: (r[c] if c < len(r) else None) for f, c in cols.items()}
        if not any(rec.get(k) not in (None, "") for k in ("qty", "sku", "chinese_name", "box_range", "shipment_id")):
            continue
        if isinstance(rec.get("box_range"), str) and norm(rec["box_range"]).startswith("Total"):
            break
        rec["_row"] = i
        out.append(rec)
    return out, h


def _line_from(rec: Dict[str, Any]) -> Dict[str, Any]:
    line = {k: _txt(rec.get(k)) for k in ("sku", "english_name", "chinese_name", "hs_code", "brand", "model", "material", "purpose", "unit", "reference_id")}
    line["unit_price"] = _num(_dec(rec.get("unit_price")))
    line["_row"] = rec.get("_row")
    return line


def _box_weights(lines: List[Dict[str, Any]], meaning: str) -> Optional[Dict[int, Decimal]]:
    if meaning == "ticket_total":
        return None
    out: Dict[int, Decimal] = {}
    for l in lines:
        w, boxes = l.get("_weight"), l.get("_boxes") or []
        if w is None or not boxes:
            continue
        n = Decimal(len(boxes))
        if meaning == "per_box":
            bw = w
        elif meaning == "range_total":
            bw = w / n
        else:  # per_unit
            bw = w * (l["_qty_dec"] / n)
        for b in boxes:
            out[b] = out.get(b, Decimal("0")) + bw if b in out and meaning != "per_box" else bw
    return out


def _finish(t: Dict[str, Any]) -> Dict[str, Any]:
    """按当前口径重算 qty / boxes。"""
    for l in t["lines"]:
        raw, n = l["_qty_raw"], Decimal(len(l.get("_boxes") or []) or 1)
        q = raw * n if (t["qty_meaning"] == "per_box" and not l.get("_force_row_total")) else raw
        l["_qty_dec"] = q
        l["qty"] = float(q)
    if t.get("_box_list") is not None:  # T8：Packing list 每箱一行，单箱重是实测值，不按口径换算
        t["boxes"] = [float(x.normalize()) for x in t["_box_list"]]
        t["gross_kg"] = float(sum(t["_box_list"], Decimal("0")))
    elif t["weight_meaning"] == "ticket_total":
        t["boxes"] = None
    elif t["weight_meaning"] is None:
        t["boxes"], t["gross_kg"] = None, None
    else:
        bw = _box_weights(t["lines"], t["weight_meaning"]) or {}
        t["boxes"] = [float(bw[b].normalize()) if b in bw else 0.0 for b in range(1, t["box_count"] + 1)] if bw else None
        if t["boxes"] is not None:
            t["gross_kg"] = float(sum(Decimal(str(x)) for x in t["boxes"]))
    return t


def _parse_table(book: _Book, t: Dict[str, Any], eff: Dict[str, Any], file_name: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rows = book.sheet(t)
    recs, h = _table_rows(rows, t)
    head = {k: _field(rows, spec, h) for k, spec in (t.get("fields") or {}).items()}
    seps = t.get("multi_value_sep")
    issues: List[Dict[str, Any]] = []
    tickets: Dict[str, Dict[str, Any]] = {}
    for rec in recs:
        sid = _txt(rec.get("shipment_id") or head.get("shipment_id")).upper()
        tk = tickets.setdefault(sid, {"shipment_id": sid, "lines": [], "issues": []})
        if seps:  # T5：一行写多个品名，用逗号分隔
            parts = {k: _split(rec.get(k), seps) for k in ("hs_code", "chinese_name", "english_name", "material", "purpose", "brand", "qty", "unit_price")}
            n = max(len(parts["chinese_name"]), len(parts["qty"]), 1)
            if any(len(v) not in (0, 1, n) for v in parts.values()):
                tk["issues"].append(_issue("multi_value_count_mismatch", f"第{rec['_row']}行逗号分隔的个数对不上：" + "，".join(f"{k}={len(v)}" for k, v in parts.items())))
            for i in range(n):
                sub = {k: (v[i] if i < len(v) else (v[0] if len(v) == 1 else None)) for k, v in parts.items()}
                sub["_row"] = rec["_row"]
                line = _line_from(sub)
                line["_qty_raw"] = _dec(sub.get("qty")) or Decimal("0")
                line["_boxes"], line["_weight"] = [], None
                tk["lines"].append(line)
            tk["_box_count"] = int(_dec(rec.get("box_count")) or 0)
            tk["_total_weight"] = _dec(rec.get("weight"))
            continue
        line = _line_from(rec)
        line["_qty_raw"] = _dec(rec.get("qty")) or Decimal("0")
        line["_boxes"] = parse_box_range(rec.get("box_range"))
        if not line["_boxes"] and rec.get("box_count") not in (None, ""):
            line["_boxes"] = list(range(1, int(_dec(rec["box_count"]) or 0) + 1))
        line["_weight"] = _dec(rec.get("weight"))
        if len([s for s in re.split(r"[\n\r]+", line["sku"]) if s.strip()]) > 1:
            line["_force_row_total"] = True
            tk["issues"].append(_issue("qty_meaning_row_total_multi_sku",
                                       f"第{rec['_row']}行一个格子写了多个 SKU，数量只能是该行合计，不按“每箱数量 × 箱数”换算"))
        if rec.get("box_count") not in (None, "") and line["_boxes"] and int(_dec(rec["box_count"]) or 0) != len(line["_boxes"]):
            tk["issues"].append(_issue("box_count_column_mismatch", f"第{rec['_row']}行总箱数 {rec['box_count']} 和箱号区间 {rec.get('box_range')} 对不上"))
        tk["lines"].append(line)

    out = []
    file_wh = _file_warehouse(file_name)
    for sid, tk in tickets.items():
        sheet_wh = re.sub(r"-\d+$", "", _txt(head.get("warehouse")).upper())  # 琪珞表里可能写 VGT2-1 这类后缀
        wh = sheet_wh or file_wh
        if sheet_wh and file_wh and sheet_wh != file_wh:
            wh = file_wh if eff["warehouse_prefer"] == "filename" else sheet_wh
            tk["issues"].append(_issue("warehouse_conflict", f"表内仓库 {sheet_wh} 和文件名仓库 {file_wh} 不一致，按配置（{eff['warehouse_prefer']}）取 {wh}；有货件 CSV 时以 CSV 为准",
                                       sheet=sheet_wh, filename=file_wh))
        forecast = int(_dec(head.get("forecast_boxes")) or 0)
        if "_box_count" in tk:
            count = tk["_box_count"]
        else:
            allb = sorted({b for l in tk["lines"] for b in l["_boxes"]})
            count = max(allb) if allb else 0
            if forecast and count > forecast:
                tk["issues"].append(_issue("box_range_exceeds_forecast",
                                           f"箱号区间写到第 {count} 箱，但预报件数是 {forecast}；按配置（{eff['box_count_source']}）" +
                                           (f"以预报件数 {forecast} 为准" if eff["box_count_source"] == "forecast_if_conflict" else "以箱号区间为准")))
                if eff["box_count_source"] == "forecast_if_conflict":
                    count = forecast
                    if len(tk["lines"]) == 1:
                        tk["lines"][0]["_boxes"] = list(range(1, forecast + 1))
                    else:
                        tk["issues"].append(_issue("box_range_needs_manual", "多行时无法自动把箱号区间改成预报件数，请人工核对箱号"))
            elif forecast and count != forecast:
                tk["issues"].append(_issue("box_count_forecast_mismatch", f"箱号区间共 {count} 箱，表头件数栏填的是 {forecast}（可能填成了商品总数），以箱号区间为准"))
        ticket = {"template_id": t["_id"], "forwarder": t.get("forwarder", ""), "shipment_id": sid, "warehouse": wh,
                  "order_no": _txt(head.get("order_no")), "box_count": count, "gross_kg": None,
                  "qty_meaning": eff["qty_meaning"], "weight_meaning": eff["weight_meaning"],
                  "lines": tk["lines"], "issues": tk["issues"]}
        if eff["weight_meaning"] == "ticket_total":
            ticket["gross_kg"] = _num(tk.get("_total_weight"))
        if eff["weight_meaning"] is None:
            ticket["issues"].append(_issue("weight_meaning_undecided",
                                           "这套模板的重量列含义不固定（D-09 第 2 点：第 7 批是单箱重、第 6 批是单件重），不默认；"
                                           "上传货件 CSV 由 Σ单箱重判定，或手动指定 weight_meaning"))
        if not _FBA_RE.match(sid):
            ticket["issues"].append(_issue("shipment_id_invalid", f"FBA 号认不出：{sid or '空'}"))
        out.append(_finish(ticket))
    return out, issues


def _parse_jiufang_export(book: _Book, t: Dict[str, Any], eff: Dict[str, Any], file_name: str):
    inv_t, pk_t = dict(t["invoice"]), dict(t["packing"])
    rows = book.sheet(inv_t)
    recs, h = _table_rows(rows, inv_t)
    wh = _txt(_field(rows, inv_t["fields"]["warehouse"], h)).upper()
    prows = book.sheet(pk_t)
    precs, _ = _table_rows(prows, pk_t)
    tickets: Dict[str, Dict[str, Any]] = {}
    for rec in recs:
        sid = _txt(rec.get("shipment_id")).upper()
        if not _FBA_RE.match(sid):
            continue
        tk = tickets.setdefault(sid, {"template_id": t["_id"], "forwarder": t.get("forwarder", ""), "shipment_id": sid, "warehouse": wh,
                                      "order_no": "", "qty_meaning": "row_total", "weight_meaning": "per_box", "lines": [], "issues": [], "_w": []})
        line = _line_from(rec)
        line["_qty_raw"] = _dec(rec.get("qty")) or Decimal("0")
        line["_boxes"], line["_weight"] = [], None
        tk["lines"].append(line)
    for rec in precs:
        sid = _txt(rec.get("shipment_id")).upper()
        if sid in tickets:
            n = int(_dec(rec.get("cartons")) or 0)
            tickets[sid]["_w"] += [_dec(rec.get("weight")) or Decimal("0")] * n
    out = []
    for tk in tickets.values():
        w = tk.pop("_w")
        tk["box_count"] = len(w)
        for l in tk["lines"]:
            l["_qty_dec"] = l["_qty_raw"]
            l["qty"] = float(l["_qty_raw"])
        tk["_box_list"] = w
        out.append(_finish(tk))
    return out, []


def parse_invoice_file(data: bytes, file_name: str = "", template_id: Optional[str] = None,
                       overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = _load_config()
    book = _Book(data, file_name)
    if template_id:
        t = _template(cfg, template_id)
        target = t.get("parse_as") or template_id
        score = _score(book, _template(cfg, target))
        if score < 1.0:
            raise ValueError(f"这个文件和所选模板 {template_id}（{t.get('name', '')}）对不上（匹配度 {score:.0%}），请换一个模板或用自动识别")
        detected_by, tid = "manual", template_id
    else:
        d = _detect(book, cfg)
        if d["ambiguous"]:
            raise ValueError(d["message"] + "：" + "、".join(f"{c['template_id']}({c['score']:.0%})" for c in d["candidates"]))
        detected_by, tid = "auto", d["template_id"]
    t = deepcopy(_template(cfg, tid))
    real = t.get("parse_as") or tid
    if t.get("parse_as"):
        t = {**deepcopy(_template(cfg, real)), **{k: v for k, v in t.items() if k not in ("detect", "parse_as")}}
    t["_id"] = tid
    eff = _effective(t, overrides)
    if t.get("parser") == "jiufang_export":
        tickets, issues = _parse_jiufang_export(book, t, eff, file_name)
    else:
        tickets, issues = _parse_table(book, t, eff, file_name)
    tickets = [tk for tk in tickets if tk["lines"] and any(l.get("qty") for l in tk["lines"]) or tk["shipment_id"]]
    if not tickets:
        issues.append(_issue("blank_template", "模板里没有填数据（空白模板）"))
    for tk in tickets:
        tk.setdefault("verify_status", "未核对")  # 没附货件 CSV 时一律“未核对”
        tk.setdefault("proposals", [])
    return {"template_id": tid, "template_name": t.get("name", ""), "forwarder": t.get("forwarder", ""), "detected_by": detected_by,
            "settings": eff, "tickets": [_public(tk) for tk in tickets], "_raw": tickets, "issues": issues}


def _public(tk: Dict[str, Any]) -> Dict[str, Any]:
    out = {k: v for k, v in tk.items() if not k.startswith("_") and k != "lines"}
    out["lines"] = [{k: v for k, v in l.items() if not k.startswith("_")} | {"box_range": _fmt_range(l.get("_boxes") or [])} for l in tk["lines"]]
    return out


def _fmt_range(boxes: List[int]) -> str:
    if not boxes:
        return ""
    runs, start, prev = [], boxes[0], boxes[0]
    for b in boxes[1:] + [None]:
        if b is not None and b == prev + 1:
            prev = b
            continue
        runs.append(f"{start}-{prev}" if start != prev else str(start))
        if b is not None:
            start = prev = b
    return ",".join(runs)


# ---------------- 和货件 CSV 交叉核对 ----------------
# S4-fix1：核对只“提出”修正，不自己改。每条修正写进 proposals，用户在预览里确认（apply_corrections）后才生效；
# 多个口径都能对上（且结果不同）时不提任何一个为默认，列出全部选项；没有 CSV 的票标“未核对”。
VERIFY_NONE = "未核对"
VERIFY_PENDING = "待确认"
VERIFY_OK = "已核对"


def _ship_to_codes(ship_to: str, warehouses: Optional[List[Dict[str, Any]]] = None) -> List[str]:
    """CSV 的“配送地址”（如 'BLOOMINGTON, CA'）→ fba_warehouse 里城市+州都对上的仓库代码。"""
    parts = [p.strip().upper() for p in str(ship_to or "").split(",") if p.strip()]
    if len(parts) < 2:
        return []
    city, state = parts[-2], parts[-1]
    if warehouses is None:
        try:
            from fba_tool.warehouse_db import list_warehouses

            warehouses = list_warehouses(limit=100000)
        except Exception:  # noqa: BLE001
            warehouses = []
    return sorted({str(w.get("code") or "").upper() for w in warehouses
                   if str(w.get("city") or "").strip().upper() == city and str(w.get("state") or "").strip().upper() == state and w.get("code")})


def _propose(tk, kind: str, value: Any, message: str, current: Any) -> None:
    sid = tk["shipment_id"]
    tk.setdefault("proposals", []).append({"id": f"{sid}:{kind}:{value}", "group": f"{sid}:{kind}", "field": kind,
                                           "current": current, "proposed": value, "message": message})


def _weights_for(tk, meaning) -> Optional[List[float]]:
    saved = tk["weight_meaning"]
    tk["weight_meaning"] = meaning
    boxes = _finish(tk).get("boxes")
    tk["weight_meaning"] = saved
    _finish(tk)
    return boxes


def _qty_for(tk, meaning) -> Decimal:
    saved = tk["qty_meaning"]
    tk["qty_meaning"] = meaning
    got = Decimal(str(sum(l["qty"] for l in _finish(tk)["lines"])))
    tk["qty_meaning"] = saved
    _finish(tk)
    return got


def reconcile_with_csv(result: Dict[str, Any], csv_files: Iterable[bytes],
                       warehouses: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    from fba_tool.shipment_parser import parse_csv_shipment

    shipments = {}
    for data in csv_files:
        s = parse_csv_shipment(data)
        shipments[s.shipment_id] = s
    raw = deepcopy(result["_raw"])
    for tk in raw:
        tk["proposals"], tk["decisions"] = [], []
        s = shipments.get(tk["shipment_id"])
        if s is None:
            tk["verify_status"] = VERIFY_NONE
            tk["issues"].append(_issue("csv_missing", "没有这票的货件 CSV，未核对（仓库、箱数、数量、重量都按发票原样，未经校验）"))
            continue
        _reconcile_one(tk, s, warehouses)
        _finish(tk)
        tk["verify_status"] = VERIFY_PENDING if (tk["proposals"] or any(i["code"].endswith("_ambiguous") or i["code"].endswith("_mismatch") or
                                                                         i["code"] in ("warehouse_unverified", "weight_meaning_undecided")
                                                                         for i in tk["issues"])) else VERIFY_OK
    out = dict(result)
    out["_raw"] = raw
    out["tickets"] = [_public(tk) for tk in raw]
    out["proposals"] = [p for tk in raw for p in tk.get("proposals", [])]
    out["reconciled"] = True
    return out


def _reconcile_one(tk, s, warehouses) -> None:
    tk.setdefault("proposals", [])
    tk.setdefault("decisions", [])
    # 仓库：取 CSV 的仓库字段（“配送地址”城市+州 → FBA 仓库地址库），不取货件名称
    ship_to = getattr(s, "ship_to", "") or ""
    codes = _ship_to_codes(ship_to, warehouses)
    cur = tk["warehouse"]
    tk["csv_ship_to"] = ship_to
    if not codes:
        tk["issues"].append(_issue("warehouse_unverified", f"货件 CSV 配送地址「{ship_to or '空'}」在 FBA 仓库地址库里对不上仓库代码，"
                                                           f"仓库 {cur or '空'} 未经核对；请导入仓库地址库或人工确认"))
    elif cur in codes:
        tk["decisions"].append({"field": "warehouse", "value": cur, "message": f"仓库 {cur} 与 CSV 配送地址 {ship_to} 一致"})
    elif len(codes) == 1:
        if not cur:
            tk["warehouse"] = codes[0]  # 发票本来没有仓库（如 SEND）：直接用 CSV 的，不算修正
            tk["decisions"].append({"field": "warehouse", "value": codes[0], "message": f"发票没写仓库，取 CSV 配送地址 {ship_to} 对应的 {codes[0]}"})
        else:
            _propose(tk, "warehouse", codes[0], f"发票仓库 {cur}，货件 CSV 配送地址 {ship_to} 对应 {codes[0]}；确认后改为 {codes[0]}", cur)
    else:
        tk["issues"].append(_issue("warehouse_ambiguous", f"CSV 配送地址 {ship_to} 对应多个仓库：{'、'.join(codes)}，发票写的是 {cur or '空'}，请选择", options=codes))
        for c in codes:
            _propose(tk, "warehouse", c, f"CSV 配送地址 {ship_to} 对应多个仓库，可选 {c}", cur)

    # 箱数
    if s.box_count and s.box_count != tk["box_count"]:
        msg = f"发票 {tk['box_count']} 箱，货件 CSV {s.box_count} 箱"
        if len(tk["lines"]) == 1 and tk["lines"][0].get("_boxes"):
            _propose(tk, "box_count", s.box_count, msg + f"；确认后按 CSV 改成 1–{s.box_count} 箱", tk["box_count"])
        else:
            tk["issues"].append(_issue("box_count_mismatch", msg + "；多行时无法自动改箱号，请人工核对"))

    # 数量口径
    csv_qty = Decimal(str(int(s.box_items["数量"].sum()))) if not s.box_items.empty else None
    if csv_qty is not None:
        cur_q = tk["qty_meaning"]
        fits = [m for m in QTY_MEANINGS if _qty_for(tk, m) == csv_qty]
        _decide(tk, "qty_meaning", cur_q, fits, {m: _qty_for(tk, m) for m in QTY_MEANINGS}, f"货件 CSV 商品数量 {csv_qty}", "qty")

    # 重量口径
    if not s.box_specs.empty and "实重(kg)" in s.box_specs and tk["weight_meaning"] != "ticket_total" and tk.get("_box_list") is None:
        csv_w = Decimal(str(round(float(s.box_specs["实重(kg)"].sum()), 2)))
        if csv_w > 0:
            results = {m: _weights_for(tk, m) for m in ("per_box", "per_unit", "range_total")}
            totals = {m: (Decimal(str(round(sum(b), 4))) if b else None) for m, b in results.items()}
            fits = [m for m, v in totals.items() if v is not None and abs(v - csv_w) <= csv_w * WEIGHT_MATCH_TOLERANCE]
            _decide(tk, "weight_meaning", tk["weight_meaning"], fits, totals, f"货件 CSV Σ单箱重 {csv_w} kg", "weight", results)


def _decide(tk, key, cur, fits, values, what, kind, results=None) -> None:
    """cur 能对上且没有别的不同结果 → 通过；cur 未设（CSV 决定）且唯一 → 采用并记录；其余一律只提建议。"""
    def same(ms):
        if results is None:
            return len({str(values[m]) for m in ms}) <= 1
        return len({tuple(results[m] or []) for m in ms}) <= 1

    if cur is not None and cur in fits:
        others = [m for m in fits if m != cur]
        if others and not same(fits):
            tk["issues"].append(_issue(f"{kind}_meaning_ambiguous", f"按配置口径 {cur} 能和{what}对上，但 {'、'.join(others)} 也能对上且结果不同；"
                                                                    f"保持 {cur}，请确认", options=fits))
            for m in others:
                _propose(tk, key, m, f"改用 {m}（同样能和{what}对上，算出 {values[m]}）", cur)
        return
    if not fits:
        tk["issues"].append(_issue(f"{kind}_mismatch", f"按 {cur or '未设口径'} 算出 {values.get(cur) if cur else '—'}，和{what}对不上，"
                                                       f"换别的口径也对不上（{'；'.join(f'{m}={v}' for m, v in values.items())}），请人工核对"))
        return
    if len(fits) > 1 and not same(fits):
        tk["issues"].append(_issue(f"{kind}_meaning_ambiguous", f"{'、'.join(fits)} 都能和{what}对上且结果不同，不自动采用任何一个，请选择", options=fits))
        for m in fits:
            _propose(tk, key, m, f"改用 {m}（算出 {values[m]}）", cur)
        return
    pick = fits[0]
    if cur is None:
        tk[key] = pick  # 模板没有默认口径：由 CSV 判定（唯一能对上的口径）
        tk["issues"] = [i for i in tk["issues"] if i["code"] != "weight_meaning_undecided"]
        tk["decisions"].append({"field": key, "value": pick, "message": f"模板不设默认口径，按{what}判定为 {pick}（只有它对得上）"})
        return
    _propose(tk, key, pick, f"按模板口径 {cur} 算出 {values.get(cur)}，和{what}对不上；按 {pick} 算出 {values[pick]} 能对上，确认后改用 {pick}", cur)
    tk["issues"].append(_issue(f"{kind}_meaning_proposed", f"建议把 {key} 从 {cur} 改为 {pick}（待确认，未生效）", configured=cur, proposed=pick))


def apply_corrections(result: Dict[str, Any], accepted: Iterable[str]) -> Dict[str, Any]:
    """用户在预览里勾选的修正（proposal id）才生效；同一组只能选一个。"""
    accepted = list(dict.fromkeys(accepted or []))
    raw = deepcopy(result["_raw"])
    by_id = {p["id"]: (tk, p) for tk in raw for p in tk.get("proposals", [])}
    unknown = [a for a in accepted if a not in by_id]
    if unknown:
        raise ValueError("没有这条修正建议：" + "、".join(unknown))
    groups: Dict[str, str] = {}
    for a in accepted:
        g = by_id[a][1]["group"]
        if g in groups:
            raise ValueError(f"同一项只能选一个修正：{groups[g]} 和 {a}")
        groups[g] = a
    for a in accepted:
        tk, p = by_id[a]
        f, v = p["field"], p["proposed"]
        if f == "warehouse":
            tk["warehouse"] = v
        elif f == "box_count":
            tk["lines"][0]["_boxes"] = list(range(1, int(v) + 1))
            tk["box_count"] = int(v)
        else:
            tk[f] = v
        tk.setdefault("applied", []).append(p)
        tk["issues"] = [i for i in tk["issues"] if not (i["code"].endswith("_ambiguous") and i.get("options") and v in i["options"])
                        and i["code"] not in (f"{f.split('_')[0]}_meaning_proposed",)]
        _finish(tk)
    for tk in raw:
        done = {p["group"] for p in tk.get("applied", [])}
        tk["proposals"] = [p for p in tk.get("proposals", []) if p["group"] not in done]
        if tk.get("verify_status") != VERIFY_NONE:
            tk["verify_status"] = VERIFY_PENDING if tk["proposals"] or any(i["code"].endswith("_ambiguous") or i["code"].endswith("_mismatch")
                                                                           or i["code"] == "warehouse_unverified" for i in tk["issues"]) else VERIFY_OK
    out = dict(result)
    out["_raw"] = raw
    out["tickets"] = [_public(tk) for tk in raw]
    out["proposals"] = [p for tk in raw for p in tk.get("proposals", [])]
    return out


# ---------------- 给报关用 ----------------
def to_customs_ticket(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """转成 customs_package.build_customs_from_tickets 的票输入；HS/单位等报关字段仍以产品库为准（发票里是货代/目的港 HS）。"""
    out: Dict[str, Any] = {"shipment_id": ticket["shipment_id"], "warehouse": ticket["warehouse"]}
    if ticket.get("boxes"):
        out["boxes"] = list(ticket["boxes"])
    else:
        out["box_count"], out["gross_kg"] = ticket.get("box_count") or 0, ticket.get("gross_kg") or 0
    out["lines"] = [{"sku": l.get("sku") or l.get("chinese_name"), "chinese_name": l.get("chinese_name"), "qty": float(l.get("qty") or 0),
                     "unit_price": l.get("unit_price"), "brand": l.get("brand")} for l in ticket["lines"]]
    return out
