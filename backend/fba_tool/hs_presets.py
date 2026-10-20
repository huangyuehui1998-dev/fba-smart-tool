"""S8：钓具 HS 预设参考（不自动写库；用户在 HS 模板里一键套用后才生效，保持 Q13/E4“钓具不预置”的原则）。

核对来源（2026-10-16）：
- 中国：《进出口税则》9507 项下 10 位商品编号，引合肥海关 12360 热线《钓具商品种类及通关税号》
  （jinkoubaodian.com/showinfo-116-3301-0.html）与 htshub 2026 中国税则 9507 节，两者一致。
  申报要素：品名；用途；品牌；型号。
- 美国：USITC 官方 HTS（hts.usitc.gov reststop 接口，2026 版）9507 节逐行核对。
只放两边都能确认的编码。钓鱼线不预设：零售包装与否决定归类（见 FISHING_LINE_NOTE）。
"""
from __future__ import annotations

from typing import Any, Dict, List

_PATTERN = "1|2|{用途}|品牌：{品牌}牌|型号：{型号}"

FISHING_HS_PRESETS: List[Dict[str, Any]] = [
    {"key": "rod", "customs_name": "钓鱼竿", "hs_code": "9507100090",
     "cn_note": "9507.1000.90 其他钓鱼竿（竹、藤等植物材料做的用 9507100010）",
     "us_hts": ["9507.10.00.40"], "us_note": "Fishing rods（MFN 6%）"},
    {"key": "hook", "customs_name": "钓鱼钩", "hs_code": "9507200000",
     "cn_note": "9507.2000.00 钓鱼钩，不论是否带线", "us_hts": ["9507.20.40.00", "9507.20.80.00"],
     "us_note": "带线钩 snelled 9507.20.40（4%）；不带线 9507.20.80（4.8%）"},
    {"key": "reel", "customs_name": "钓线轮", "hs_code": "9507300000",
     "cn_note": "9507.3000.00 钓线轮", "us_hts": ["9507.30.20.00", "9507.30.40.00", "9507.30.60.00"],
     "us_note": "按单价分档：≤$2.70 用 .20；$2.70–$8.45 用 .40；>$8.45 用 .60；零件 .80"},
    {"key": "lure", "customs_name": "拟饵", "hs_code": "9507900000",
     "cn_note": "9507.9000.00 其他钓具（拟饵/假饵、浮漂、铅坠、竿架）。注意：配制的鱼饵是 2309，不是这里",
     "us_hts": ["9507.90.70.00"], "us_note": "Artificial baits and flies（9%）；浮漂铅坠等其他件用 9507.90.80"},
]

FISHING_LINE_NOTE = (
    "钓鱼线不预设一个编码：归类取决于是否零售包装、是否已制成钓鱼线以及材质规格，需逐个确认。"
    "美国：HTS 9507.90.20.00「Fishing line put up and packaged for retail sale」。"
    "CBP HQ 954309（1994）和 HQ 956007（1994，撤销 NY 884900）认定：切成长度、绕在线轴上、装进盒子或吸塑零售包装并明确标为钓鱼线的尼龙单丝，归 9507.90.20；"
    "只绕在线轴上、没有零售包装和鱼线标识的，不算“制成钓鱼线”，按材质归 5404（合成纤维单丝 ≤1mm）、3916（>1mm 塑料单丝）或 5607（编织线/绳）。"
    "较早的 NY 882320（1993）曾把成卷鱼线归 5404/3916/5607，后来 HQ 954309 明确了上面的标准。"
    "中国：已制成零售包装的钓鱼线成品归 9507900000；第 95 章注释排除“切成一定长度但未制成钓鱼线”的单丝/线，按材质归第 39 章或第 54/56 章。"
    "请按实物包装和规格（必要时问报关行）确认后手动录入。"
)


def hs_presets(category: str) -> Dict[str, Any]:
    cat = str(category or "").strip().lower()
    if cat in ("fishing", "渔具", "钓具"):
        items = [dict(p, category="fishing", elements_pattern=_PATTERN, default_purpose="钓鱼用",
                      source="S8 预设（中国税则 + USITC HTS 核对）") for p in FISHING_HS_PRESETS]
        return {"category": "fishing", "items": items, "not_preset": [{"key": "line", "customs_name": "钓鱼线", "note": FISHING_LINE_NOTE}]}
    return {"category": cat, "items": [], "not_preset": []}
