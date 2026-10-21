"""R12-03 / N3：realdata 在场时按原始文件复算 S-01..S-07。目录不在才跳过。"""
from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from tests.smoke.reference import LayoutMissing, available, cl2_net, placement_table, realdata_root, sta_sheets, summarize_batch13

pytestmark = pytest.mark.realdata_smoke

CASES = ("S-01", "S-02", "S-03", "S-04", "S-05", "S-06", "S-07")
ANCHOR_BOX = Decimal("318.90")
ANCHOR_CARRY = Decimal("1.30")
ANCHOR_ROWS = 154
ANCHOR_BILLS = 5
ANCHOR_NET = Decimal("254.4")
OFFICIAL = {
    "small_standard": [
        (Decimal("0.5"), (Decimal("0.14"), Decimal("0.32")), None),
        (Decimal("1.0"), (Decimal("0.16"), Decimal("0.32")), None),
    ],
    "large_oversize": [
        (Decimal("5"), (Decimal("1.30"), Decimal("1.80")), (Decimal("0.55"), Decimal("1.25"))),
        (Decimal("12"), (Decimal("2.10"), Decimal("2.90")), (Decimal("0.65"), Decimal("1.80"))),
        (Decimal("28"), (Decimal("3.40"), Decimal("4.10")), (Decimal("0.81"), Decimal("2.30"))),
        (Decimal("42"), (Decimal("4.70"), Decimal("5.60")), (Decimal("1.05"), Decimal("2.95"))),
        (Decimal("50"), (Decimal("5.50"), Decimal("6.50")), (Decimal("1.23"), Decimal("3.50"))),
    ],
}


def _write(items: list[dict]) -> None:
    dest = os.environ.get("SMOKE_REPORT_PATH")
    if not dest:
        return
    Path(dest).write_text(
        json.dumps(
            {
                "items": items,
                "note": "pending_verification 的红绿结果、以及第 15 批账单与逐箱合计的差额，都不作为断言。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _tri(name: str, reference, product, anchor) -> None:
    if reference == product == anchor:
        return
    raise AssertionError(f"{name} reference={reference} product={product} anchor={anchor}")


def _product_compare(monkeypatch, tmp_path, box: dict) -> dict:
    monkeypatch.setenv("FBA_APP_DATA_DIR", str(tmp_path / "app"))
    monkeypatch.setenv("FBA_DISABLE_SCHEDULER", "1")
    from fastapi.testclient import TestClient

    from fba_tool.carton_store import _declared_to_amazon, _stored_dims
    from fba_tool.master_db import init_master_db
    from fba_tool.shipment_parser import parse_csv_shipment
    from main import create_app

    init_master_db()
    client = TestClient(create_app(), raise_server_exceptions=False)
    health = client.get("/api/fx-rates")
    assert health.status_code < 500, health.text
    for raw in box["measure_files"]:
        path = Path(raw)
        response = client.post(
            "/api/measurements/import/apply",
            files={"file": (path.name, path.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert response.status_code < 500, response.text
        assert response.status_code == 200, response.text
    for raw in box["csv_files"]:
        path = Path(raw)
        ship = parse_csv_shipment(path.read_bytes(), file_name=path.name)
        boxes = []
        ids = dict(ship.box_fba_ids or {})
        if ship.box_specs is None or ship.box_specs.empty:
            continue
        for _, spec in ship.box_specs.iterrows():
            box_no = spec.get("箱号")
            try:
                numeric = int(box_no)
            except (TypeError, ValueError):
                numeric = box_no
            box_id = str(spec.get("FBA箱号") or ids.get(box_no) or ids.get(numeric) or "")
            declared = _declared_to_amazon(spec)
            dims = _stored_dims(spec, declared)
            boxes.append({
                "fba_box_id": box_id,
                "box_no": box_no,
                "length_cm": dims["length_cm"],
                "width_cm": dims["width_cm"],
                "height_cm": dims["height_cm"],
                "gross_kg": dims["gross_kg"],
                "declared_to_amazon": declared,
            })
        if not boxes:
            continue
        posted = client.post(
            f"/api/shipments/{ship.shipment_id}/box-snapshot",
            json={"stage": "step4_validated", "batch": "13", "boxes": boxes},
        )
        assert posted.status_code < 500, posted.text
        assert posted.status_code == 200, posted.text
    report = client.get("/api/carton-compare", params={"batch": "13", "source": "forwarder_jiufang"})
    assert report.status_code < 500, report.text
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["mode"] == "box", body.get("message")
    summary = body["summary"]
    return {
        "mode": body["mode"],
        "box_total": _money(summary["box_total"]),
        "carry": _money(summary["carry"]),
        "rows": int(summary["deduped_count"]),
    }


def test_box_realdata_smoke(monkeypatch, tmp_path):
    if not available():
        _write([{"id": case, "status": "skipped", "reason": "realdata 不在本环境"} for case in CASES])
        pytest.skip("需要 box realdata")

    root = realdata_root()
    items: list[dict] = []
    box = None
    sta = None
    cl2 = None
    product = None
    try:
        box = summarize_batch13(root)
    except LayoutMissing as exc:
        box_error = str(exc)
    else:
        box_error = ""
    try:
        sta = sta_sheets(root)
    except LayoutMissing as exc:
        sta_error = str(exc)
    else:
        sta_error = ""
    try:
        cl2 = cl2_net(root)
    except LayoutMissing as exc:
        cl2_error = str(exc)
    else:
        cl2_error = ""
    if box is not None:
        try:
            product = _product_compare(monkeypatch, tmp_path, box)
        except Exception as exc:
            product_error = f"{type(exc).__name__}: {exc}"
        else:
            product_error = ""
    else:
        product_error = box_error

    def run(case: str, fn) -> None:
        try:
            detail = fn()
        except Exception as exc:
            items.append({"id": case, "status": "failed", "reason": f"{type(exc).__name__}: {exc}"})
        else:
            items.append({"id": case, "status": "passed", "detail": detail})

    def s01():
        if box is None or product is None:
            raise AssertionError(box_error or product_error)
        _tri("box_total", box["box_total"], product["box_total"], ANCHOR_BOX)
        _tri("rows", box["matched_rows"], product["rows"], ANCHOR_ROWS)
        return {"box_total": str(box["box_total"]), "rows": box["matched_rows"]}

    def s02():
        if box is None or product is None:
            raise AssertionError(box_error or product_error)
        _tri("carry", box["carry"], product["carry"], ANCHOR_CARRY)
        return {"carry": str(box["carry"])}

    def s03():
        if box is None:
            raise AssertionError(box_error)
        assert box["bill_count"] == ANCHOR_BILLS
        assert box["bills_matched"] == ANCHOR_BILLS
        return {"bills": f"{box['bills_matched']}/{box['bill_count']}"}

    def s04():
        if product is None:
            raise AssertionError(product_error)
        assert product["mode"] == "box"
        return {"mode": product["mode"]}

    def s05():
        if sta is None:
            raise AssertionError(sta_error)
        from fba_tool.sta_precheck import precheck_sta_rows

        for sheet in sta:
            assert sheet["labels_ok"], sheet["path"]
            highlights = precheck_sta_rows(sheet["rows"])
            label_rows = set(sheet["label_rows"])
            false = [
                item for item in highlights
                if item.get("row") in label_rows and "必填项为空" in str(item.get("message") or "")
            ]
            assert false == [], (sheet["path"], false)
        return {"sheets": len(sta)}

    def s06():
        if cl2 is None:
            raise AssertionError(cl2_error)
        from fba_tool.customs_package import compute_net_weight

        product_net = Decimal(str(compute_net_weight(
            cl2["gross"], cl2["boxes"], [cl2["tare"]] * cl2["boxes"],
        )))
        assert cl2["net"] == product_net == ANCHOR_NET, (cl2["net"], product_net, ANCHOR_NET)
        return {"net": str(cl2["net"]), "boxes": cl2["boxes"]}

    def s07():
        table = placement_table()
        assert "GC3Q44" in table["source_url"]
        classes = table["classes"]
        for name, rows in OFFICIAL.items():
            stored = classes[name]
            for index, (high, one, partial) in enumerate(rows):
                assert Decimal(str(stored[index]["high"])) == high
                assert tuple(Decimal(str(item)) for item in stored[index]["1_loc"]) == one
                if partial is None:
                    assert "2_3_loc" not in stored[index]
                else:
                    assert tuple(Decimal(str(item)) for item in stored[index]["2_3_loc"]) == partial
        return {"source_url": table["source_url"]}

    for case, fn in (
        ("S-01", s01), ("S-02", s02), ("S-03", s03), ("S-04", s04),
        ("S-05", s05), ("S-06", s06), ("S-07", s07),
    ):
        run(case, fn)
    _write(items)
    failed = [item for item in items if item["status"] != "passed"]
    assert not failed, failed
