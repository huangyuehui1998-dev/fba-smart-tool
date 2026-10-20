#!/usr/bin/env python3
"""S7 端到端启动冒烟：真起一个后端进程（uvicorn），只用临时 app_data，按三大功能各走一遍。

用法（在仓库根目录）：
    backend/.venv/Scripts/python.exe scripts/smoke_e2e.py        # Windows
    python scripts/smoke_e2e.py [--keep]                         # --keep 保留临时目录便于查看
不连领星（领星只测定时同步接口和“没配密钥→不重试”），不碰真实 app_data（启动前后做哈希对比）。
退出码 0 = 全部通过。
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
G = BACKEND / "tests" / "golden"


def _real_app_data() -> Path:
    """真实 app_data：--real-app-data=路径 > 环境变量 FBA_REAL_APP_DATA_DIR > 仓库根 app_data。
    （S7-fix1：在仓库副本里跑时要显式指向真实目录，否则只是在看副本自己的 app_data。）"""
    for a in sys.argv[1:]:
        if a.startswith("--real-app-data="):
            return Path(a.split("=", 1)[1]).expanduser().resolve()
    env = os.environ.get("FBA_REAL_APP_DATA_DIR", "").strip()
    return Path(env).expanduser().resolve() if env else (ROOT / "app_data").resolve()


REAL_APP_DATA = _real_app_data()
TOKEN = "smoke-" + uuid.uuid4().hex[:16]
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("  OK  " if ok else "  FAIL") + f" {name}" + (f" — {detail}" if detail else ""), flush=True)


def tree_hash(p: Path) -> dict:
    if not p.exists():
        return {}
    return {str(f.relative_to(p)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(p.rglob("*")) if f.is_file()}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    b = "----smoke" + uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, (fn, data) in files.items():
        out.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                  f"Content-Type: application/octet-stream\r\n\r\n".encode() + data + b"\r\n")
    out.write(f"--{b}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={b}"


class Api:
    def __init__(self, base: str):
        self.base = base

    def req(self, method: str, path: str, *, json_body=None, fields=None, files=None, token=True):
        headers = {"X-Access-Token": TOKEN} if token else {}
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"
        elif fields is not None or files is not None:
            data, ct = multipart(fields or {}, files or {})
            headers["Content-Type"] = ct
        r = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(r, timeout=120) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)


def seed(app_data: Path) -> dict:
    """往临时 app_data 写入冒烟用的产品和仓库（真实程序也是从这里读）。"""
    os.environ["FBA_APP_DATA_DIR"] = str(app_data)
    sys.path.insert(0, str(BACKEND))
    from fba_tool.app_paths import app_data_dir, ensure_app_data_layout
    assert Path(app_data_dir()).resolve() == app_data.resolve(), app_data_dir()
    ensure_app_data_layout()
    from fba_tool.master_db import init_master_db, upsert_product
    from fba_tool.product_fields import set_product_fields
    init_master_db()
    snap = json.loads((G / "product_master_golden.json").read_text(encoding="utf-8"))
    snap = {p["fnsku"]: p for p in snap["products"]}
    n = 0
    for f in ("X0059EFBRF", "X0059EHE0H"):
        p = snap[f]
        sku = "SMOKE-" + f
        upsert_product({"sku": sku, "fnsku": f, "asin": p["asin"], "english_name": p["english_name"],
                        "chinese_name": p["chinese_name"], "brand": p["brand"], "material": p["material"],
                        "purpose": p["purpose"], "model_name": p["model_name"], "hs_code": p["hs_code"],
                        "extra_data": {"invoice": p["invoice"]}}, overwrite=True)
        set_product_fields(sku, {"listing_price": p["listing_price"]}, "lingxing")
        n += 1
    from fba_tool.customs_package import build_customs_from_tickets
    pet = {"chinese_name": "宠物垫", "hs_code": "6307909000", "unit": "包", "brand": "DemoBrand", "category": "pet"}
    t = {"shipment_id": "FBA19P4NX8HH", "warehouse": "SBD1", "boxes": [7.5] * 13,
         "lines": [dict(pet, sku="A", qty=52, unit_price=39.99)]}
    customs = build_customs_from_tickets([t], {"id": "smoke", "name": "冒烟测试公司", "credit_code": "X",
                                               "signed_at": "武汉", "domestic_source": "武汉"},
                                         order_no="SMOKE1", dates={"invoice_date": "2026-10-16"})
    return {"products": n, "customs": customs.to_dict()}


def main() -> int:
    keep = "--keep" in sys.argv
    before = tree_hash(REAL_APP_DATA)
    print(f"真实 app_data（只做哈希对比，不写入）：{REAL_APP_DATA}，{len(before)} 个文件")
    check("真实 app_data 存在且有文件（否则“未改动”检查没有意义）", REAL_APP_DATA.is_dir() and len(before) > 0,
          str(REAL_APP_DATA) if before else f"{REAL_APP_DATA} 不存在或为空；用 --real-app-data=路径 指向真实目录")
    tmp = Path(tempfile.mkdtemp(prefix="fba_smoke_"))
    app_data = tmp / "app_data"
    app_data.mkdir()
    print(f"临时 app_data：{app_data}")
    seeded = seed(app_data)
    check("临时 app_data 初始化 + 写入冒烟产品", seeded["products"] == 2)

    port = free_port()
    env = dict(os.environ, FBA_APP_DATA_DIR=str(app_data), FBA_ACCESS_TOKEN=TOKEN, PYTHONIOENCODING="utf-8")
    log = open(tmp / "server.log", "wb")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
                            cwd=str(BACKEND), env=env, stdout=log, stderr=subprocess.STDOUT)
    api = Api(f"http://127.0.0.1:{port}")
    try:
        t0 = time.time()
        st = None
        while time.time() - t0 < 60:
            try:
                st, body, _ = api.req("GET", "/api/health")
                if st == 200:
                    break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.5)
        check("后端启动（/api/health）", st == 200, f"{time.time() - t0:.1f}s 端口 {port}")
        st, body, _ = api.req("GET", "/")
        dist = (BACKEND / "dist" / "index.html").is_file()
        check("前端页面（/）", dist and st == 200 and b"<html" in body.lower(),
              "backend/dist 已打包" if dist else "backend/dist/index.html 不存在：先运行 scripts/build_standalone.ps1 或 sync_frontend_static.py")
        st, _, _ = api.req("POST", "/api/invoice-export/preview", fields={"forwarder_id": "send"}, token=False)
        check("写接口不带口令 → 401", st == 401, str(st))

        # ---- 功能一：产品库（仓库地址库导入 + 产品列表 + 领星定时同步接口）
        q = (BACKEND / "tests/fixtures/warehouse/fba_warehouse_qiluo.xlsx").read_bytes()
        st, body, _ = api.req("POST", "/api/master-data/import/warehouses/apply", files={"file": ("q.xlsx", q)})
        check("产品库：导入琪珞仓库地址库", st == 200, body[:120].decode("utf-8", "replace"))
        st, body, _ = api.req("GET", "/api/master-data/warehouses?q=VGT2")
        vg = [w for w in json.loads(body).get("items", json.loads(body) if isinstance(json.loads(body), list) else []) if w.get("code") == "VGT2"] if st == 200 else []
        check("产品库：VGT2 地址已纠正为 Las Vegas", bool(vg) and vg[0].get("city") == "Las Vegas", str(vg[:1])[:120])
        st, body, _ = api.req("GET", "/api/master-data/list")
        check("产品库：产品列表能读到冒烟产品", st == 200 and b"SMOKE-X0059EFBRF" in body)
        st, body, _ = api.req("GET", "/api/lingxing/schedule")
        cfg = json.loads(body).get("config", {}) if st == 200 else {}
        check("产品库：领星定时同步默认关闭", st == 200 and cfg.get("enabled") is False)
        st, body, _ = api.req("PUT", "/api/lingxing/schedule", json_body={"enabled": True, "interval_minutes": 60})
        s2 = json.loads(body) if st == 200 else {}
        check("产品库：开启定时同步并算出下次时间", st == 200 and s2.get("status", {}).get("next_run_at"), str(s2.get("status"))[:120])
        st, body, _ = api.req("POST", "/api/lingxing/schedule/run-now")
        r = json.loads(body) if st == 200 else {}
        check("产品库：没配领星密钥 → 失败且不重试（不连领星）", st == 200 and r.get("status") == "failed" and "Key" in r.get("message", ""))
        api.req("PUT", "/api/lingxing/schedule", json_body={"enabled": False})

        # ---- 功能二：发票（模板识别 + SEND/九方导出）
        tpl = next((G / "samples").rglob("T3_*.xlsx"), None) or next((BACKEND / "tests").rglob("T3_*.xlsx"), None)
        if tpl:
            st, body, _ = api.req("POST", "/api/invoice-templates/detect", files={"file": (tpl.name, tpl.read_bytes())})
            check("发票：识别货代发票模板", st == 200 and b"T3" in body, tpl.name)
        csv = (G / "samples/inputs/第三票FBA19P4N6MM2.csv").read_bytes()
        st, body, _ = api.req("POST", "/api/invoice-export/preview", fields={"forwarder_id": "send", "reference_id": "2VJ79IPP"},
                              files={"csv_file": ("a.csv", csv)})
        j = json.loads(body) if st == 200 else {}
        check("发票：SEND 预览（148 件、箱号 1-23/24-37）", st == 200 and j.get("total_qty") == 148, str(st))
        for fw, extra in (("send", {}), ("jiufang", {"order_no": "SMOKE"})):
            st, body, hd = api.req("POST", "/api/invoice-export/export", fields={"forwarder_id": fw, "reference_id": "2VJ79IPP", **extra},
                                   files={"csv_file": ("a.csv", csv)})
            check(f"发票：导出 {fw} xlsx", st == 200 and body[:2] == b"PK", f"{len(body)} 字节")

        # ---- 功能三：报关资料（xlsx + xls）
        for fmt, magic in (("xlsx", b"PK"), ("xls", bytes.fromhex("D0CF11E0"))):
            st, body, _ = api.req("POST", "/api/customs/export", json_body={"source": "shipment", "order_no": "SMOKE1",
                                                                            "data": seeded["customs"], "export_format": fmt})
            check(f"报关：导出 {fmt}", st == 200 and body[:len(magic)] == magic, f"{st} {len(body)} 字节")
    finally:
        proc.terminate()
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
    logtxt = (tmp / "server.log").read_text(encoding="utf-8", errors="replace")
    check("后端日志无 Traceback", "Traceback" not in logtxt, "" if "Traceback" not in logtxt else logtxt[-800:])
    # S9-step4-fix3：按内容（SHA-256 + SQLite 表特征）确认临时目录里没有真实库 / 会话的副本；只输出临时目录里的相对路径
    from realdata_guard import RealDataIndex, real_sources
    copies = RealDataIndex(real_sources(BACKEND, ROOT, [REAL_APP_DATA])).find_copies(tmp)
    check("临时目录里没有真实库 / 会话副本（按内容比对）", not copies, "；".join(copies[:5]))
    check("真实 app_data 未被改动（哈希前后一致）", tree_hash(REAL_APP_DATA) == before, f"{len(before)} 个文件")
    if not keep:
        shutil.rmtree(tmp, ignore_errors=True)
    bad = [r for r in results if not r[1]]
    print(f"\n冒烟结果：{len(results) - len(bad)}/{len(results)} 通过")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
