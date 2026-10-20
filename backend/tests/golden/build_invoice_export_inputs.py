"""一次性：整理发票导出 golden 的“输入”（不是期望值）。

1. 产品库快照 product_master_golden.json 补发票字段（英文/中文品名、品牌、型号、材质、用途、目的港 HS、单位、每套个数、
   采购价、ASIN）。这些是产品资料，现存唯一记录在货代发票里，所以从样例里抄出来作为产品库输入，并逐条记来源；
   金额、数量、箱号区间、重量、合计、CBM、派送地址等“计算/汇总结果”一律不从样例取。
2. 票级输入 invoice_export_inputs.json：Reference ID（运费表“FBA运费-记录”G 列 / “FBA-发货信息”I 列；
   运费表没有的 4 票从样例抄，标出来）、九方 LCL 单号（文件名）、渠道、发票日期、实测单箱数据来源。
3. 九方有 3 票（GZ0PA / 9BD6A / TNKDA）找不到“单箱数据”文件，实测单箱重/尺寸只能从样例 Packing list 抄作输入
   （方案 §3.5：九方 Packing list 单箱毛重是实测值，作为输入），这 3 票的 L/W/H/G.W 列因此不算独立核验，报告里单列。
"""
import json
from pathlib import Path

import openpyxl

G = Path(__file__).resolve().parent
S = G / "samples" / "invoice"

FREIGHT_REF = {  # 运费表 e1-01-J-宠物庭院-FBA运费-入库配置费测算.xlsx「FBA运费-记录」G63、G72–G77
    "FBA19JQTB2XL": "4RTG99ZH", "FBA19P4P4CL2": "7D1HAMFN", "FBA19P4P4MBQ": "584ZZ66H", "FBA19P4N6MM2": "2VJ79IPP",
    "FBA19P4NX8HH": "529Y225L", "FBA19P4P3PZC": "557HILNJ", "FBA19RJCXY6X": "2DNWEOXU",
}
SEND = {"FBA19P4N6MM2": "第三票FBA19P4N6MM2.csv", "FBA19P4NX8HH": "第四票FBA19P4NX8HH.csv", "FBA19P4P3PZC": "第五票FBA19P4P3PZC.csv",
        "FBA19P4P4CL2": "第一票FBA19P4P4CL2.csv", "FBA19P4P4MBQ": "第二票FBA19P4P4MBQ.csv"}
JF = {"LCL2607GZ0PA": "第11批FBA19JQTB2XL.csv", "LCL26099BD6A": "第14批第一票FBA19RJCXY6X.csv", "LCL2609PU1DA": "第四票FBA19P4NX8HH.csv",
      "LCL2609TNKDA": "第14批第二票FBA19RJH13MS.csv", "LCL2610DHTZA": "第二票FBA19SC2G1WQ.csv", "LCL2610QGXTA": "第四票FBA19SC5CCXC.csv",
      "LCL2610S97BA": "第五票FBA19SC5YXQQ.csv", "LCL2610UKEKA": "第三票FBA19SC937CV.csv"}
BOXDATA = {k: f"jiufang_box_data/{k}-单箱数据-运营(企微用-SEND).xlsx" for k in ("LCL2609PU1DA", "LCL2610DHTZA", "LCL2610QGXTA", "LCL2610S97BA", "LCL2610UKEKA")}


def main():
    snap = json.loads((G / "product_master_golden.json").read_text(encoding="utf-8"))
    prods = {p["fnsku"]: p for p in snap["products"]}
    cases = []
    for sid, csv in SEND.items():
        ws = openpyxl.load_workbook(S / f"{sid}发票.xlsx").worksheets[0]
        ref = None
        for r in ws.iter_rows(min_row=15, values_only=True):
            if not r[4]:
                continue
            ref = r[3]
            p = prods[r[4]]
            inv = p.setdefault("invoice", {})
            p.update({"english_name": r[6], "chinese_name": r[7], "brand": r[8], "material": r[9], "purpose": r[10],
                      "model_name": r[11], "hs_code": str(r[12]), "asin": r[13]})
            inv.update({"unit": r[14], "purchase_price": float(r[16]), "purchase_currency": "CNY"})
            p.setdefault("_来源", {})["SEND字段"] = f"{sid}发票.xlsx（品名/品牌/中文材质/中文用途/型号/HS/ASIN/单位/采购价）"
        cases.append({"case_id": sid, "forwarder": "send", "csv": csv, "reference_id": FREIGHT_REF.get(sid, ref),
                      "reference_id_source": "运费表" if sid in FREIGHT_REF else "样例（运费表无记录）",
                      "expected": f"samples/invoice/{sid}发票.xlsx"})
    for lcl, csv in JF.items():
        wb = openpyxl.load_workbook(S / f"{lcl}-箱单发票.xlsx")
        inv_ws, pk = wb["Invoice"], wb["Packing list"]
        sid = inv_ws["P3"].value
        ref = None
        for r in inv_ws.iter_rows(min_row=25, values_only=True):
            if not (r[2] and str(r[2]).startswith("X0")):
                continue
            ref = r[1]
            p = prods[r[2]]
            inv = p.setdefault("invoice", {})
            p.setdefault("english_name", r[3]); p.setdefault("chinese_name", r[4]); p.setdefault("brand", r[5])
            p.setdefault("model_name", r[6]); p.setdefault("asin", r[20])
            inv.update({"material_en": r[7], "purpose_en": r[12], "dest_hs_code": str(r[13]), "unit": r[15], "pcs_per_set": r[16]})
            p.setdefault("_来源", {})["九方字段"] = f"{lcl}-箱单发票.xlsx（英文材质/英文用途/HS/单位/每套个数）"
        case = {"case_id": lcl, "forwarder": "jiufang", "csv": csv, "shipment_id": sid, "order_no": lcl,
                "reference_id": FREIGHT_REF.get(sid, ref), "reference_id_source": "运费表" if sid in FREIGHT_REF else "样例（运费表无记录）",
                "channel": inv_ws["B2"].value, "invoice_date": "2026-10-16",
                "expected": f"samples/invoice/{lcl}-箱单发票.xlsx"}
        if lcl in BOXDATA:
            case["measured_file"] = BOXDATA[lcl]
            if lcl == "LCL2610QGXTA":
                case["measured_box_id_fix"] = {"12": 6}
                case["measured_box_id_fix_原因"] = ("九方单箱数据原件第 7 行外箱号写成 12，该票 CSV 只有 6 箱、其余 5 行是 1–5，"
                                                 "九方箱单 Packing list 里也是 U000006；按证据确认的更正（相当于用户在预览里确认），作为输入；程序不会自己改")
        else:
            m = {}
            for r in pk.iter_rows(min_row=6, values_only=True):
                if r[5] and str(r[5]).startswith("FBA"):
                    m[r[5]] = {"weight": r[12], "length": r[8], "width": r[9], "height": r[10]}
            case["measured"] = m
            case["measured_source"] = "样例 Packing list（找不到九方单箱数据文件；L/W/H/G.W 不算独立核验）"
        cases.append(case)
    snap["_说明"] = ("golden 固定产品库快照：listing_price 为申报价来源（D-01）；发票字段（品名、材质、用途、HS、单位、每套个数、采购价、ASIN）"
                    "是产品资料，现存唯一记录在货代发票样例里，逐条在 _来源 注明。金额/数量/箱号/重量/合计等计算结果不在快照里。")
    (G / "product_master_golden.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    (G / "invoice_export_inputs.json").write_text(json.dumps({"_说明": __doc__, "cases": cases}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
