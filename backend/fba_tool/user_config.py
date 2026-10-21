from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict

from fba_tool.app_paths import resolve_config_read, resolve_config_write, user_config_dir
from fba_tool.units import CM_TO_INCH, INCH_TO_CM, KG_TO_LB, LB_TO_KG

SETTINGS_FILE = user_config_dir() / "user_settings.json"
FORMULAS_FILE = user_config_dir() / "formulas.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "parameters": {
        # FBA 标准件单箱毛重红线为 50 lb ≈ 22.68 kg（见 fba_compliance.FBA_MAX_STANDARD_GROSS_KG）。
        # 排箱上限默认 22.5 kg，预留约 0.18 kg 安全余量，防止仓库磅秤误差导致拒收。
        "weight_limit_kg": 22.5,
        "max_mixed_items_per_box": 40,
        # throw_ratio：货代/物流计费的体积重系数（长×宽×高cm ÷ 系数），影响体积重/计费吨判定。
        #   空运常用 6000，海运口径不同，请按货代要求设置。
        #   注意：亚马逊入库配置费用的是固定的尺寸重量除数 139 in³/lb（见 placement_fee.DIM_WEIGHT_DIVISOR），
        #   与此货代系数是两套独立体系，勿混用。
        "throw_ratio": 6000,
        "volume_divisor": 6000,
        "kg_to_lb_factor": KG_TO_LB,
        "lb_to_kg_factor": LB_TO_KG,
        "cm_to_inch_factor": CM_TO_INCH,
        "inch_to_cm_factor": INCH_TO_CM,
        "internal_gross_lb_factor": 2.2,
        "sta_box_prefix": "P1 - B",
        "sta_condition_default": "NewItem",
        "sta_prep_owner_default": "无",
        "sta_label_owner_default": "卖家提供",
        "factory_data_start_row": 4,
        "factory_box_label_prefix": "纸箱",
        "forwarder_data_start_row": 3,
        "forwarder_country_default": "美国",
        "input_template_blank_rows": 10,
        "input_template_include_example": False,
        # S9-step3 #6：价格上限（美元）。领星售价 / 常规价 / 导入价超过它当作无效、不写入；申报价校验也用它。
        # 100000 美元：D-14，用户确认 2026-10-17。
        "price_max": 100000,
        "invoice_unit_fallback_declare_unit": True,
    },
    "factory_warehouse_columns": {},
    "forwarder_column_map": {},
}

DEFAULT_FORMULAS: Dict[str, Any] = {
    "internal": {
        "carton_count": "={total_col}{row}/{carton_col}{row}",
        "check_qty": "=SUM({first_box_col}{row}:{last_box_col}{row})",
        "volume": "={col}{length_row}*{col}{width_row}*{col}{height_row}/{volume_divisor}",
        "gross_lb": "={col}{weight_row}*{internal_gross_lb_factor}",
        "width_in": "={col}{width_row}/{inch_to_cm_factor}",
        "length_in": "={col}{length_row}/{inch_to_cm_factor}",
        "height_in": "={col}{height_row}/{inch_to_cm_factor}",
        "sum_weight_row": "=SUM({first_box_col}{weight_row}:{last_box_col}{weight_row})",
        "sum_volume_row": "=SUM({first_box_col}{volume_row}:{last_box_col}{volume_row})",
    },
    "sta": {
        "packed_qty": "=SUM({first_box_col}{row}:INDEX({first_box_col}{row}:XFD{row},1,{box_count_ref}))",
        "box_header": '=IF({box_count_ref}>={box_no},"单箱 {box_no} 装箱","")',
        "box_type": '=IF({box_count_ref}>={box_no},"{sta_box_prefix}{box_no}","")',
    },
    "labels": {
        "internal_box_header": "第{box_no}箱",
    },
}

_cache: Dict[str, Any] = {"settings": None, "formulas": None}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


CONFIG_ERRORS: Dict[str, str] = {}  # 文件名 → 错误说明；界面/接口据此提示（S7-fix1）


def _read_json(path: Path) -> dict:
    """坏 JSON 不再静默：记日志 + 记到 CONFIG_ERRORS（接口 /api/config/settings 返回 config_errors 提示），本次用出厂值兜底。"""
    import logging

    # S8 P2（S7 待办 B）：按逻辑名记错。用户删掉坏的 formulas.json 后会读 formulas.default.json，
    # 以前按实际文件名记，“formulas.json”的旧错误永远清不掉，要重启才消失。
    name = Path(path).name.replace(".default.json", ".json")
    CONFIG_ERRORS.pop(name, None)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"配置文件格式错误：{name} 第 {exc.lineno} 行第 {exc.colno} 列（{exc.msg}），已暂时改用出厂值；请修正或删除 {path} 后重试"
    except OSError as exc:
        msg = f"配置文件读不了：{name}（{exc}），已暂时改用出厂值"
    else:
        if isinstance(data, dict):
            return data
        msg = f"配置文件格式错误：{name} 顶层应是 JSON 对象，已暂时改用出厂值"
    CONFIG_ERRORS[name] = msg
    logging.getLogger(__name__).warning(msg)
    return {}


def config_errors() -> Dict[str, str]:
    return dict(CONFIG_ERRORS)


def _settings_path() -> Path:
    return resolve_config_read("user_settings.json")


def _formulas_path() -> Path:
    return resolve_config_read("formulas.json")


def load_settings(force: bool = False) -> Dict[str, Any]:
    if _cache["settings"] is not None and not force:
        return _cache["settings"]
    merged = _deep_merge(DEFAULT_SETTINGS, _read_json(_settings_path()))
    _cache["settings"] = merged
    return merged


def load_formulas(force: bool = False) -> Dict[str, Any]:
    if _cache["formulas"] is not None and not force:
        return _cache["formulas"]
    merged = _deep_merge(DEFAULT_FORMULAS, _read_json(_formulas_path()))
    _cache["formulas"] = merged
    return merged


def save_settings(data: Dict[str, Any]) -> None:
    path = resolve_config_write("user_settings.json")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _cache["settings"] = data


def save_formulas(data: Dict[str, Any]) -> None:
    path = resolve_config_write("formulas.json")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _cache["formulas"] = data


def reset_all_to_defaults() -> None:
    save_settings(copy.deepcopy(DEFAULT_SETTINGS))
    save_formulas(copy.deepcopy(DEFAULT_FORMULAS))


def param(key: str, default: Any = None) -> Any:
    settings = load_settings()
    return settings.get("parameters", {}).get(key, default)


def formula(section: str, key: str, default: str = "") -> str:
    formulas = load_formulas()
    return str(formulas.get(section, {}).get(key, default))


def label(key: str, default: str = "") -> str:
    return formula("labels", key, default)


def render_formula(template: str, **ctx) -> str:
    """渲染公式/文本模板，自动注入 user_settings 参数。"""
    settings = load_settings()
    merged = {**settings.get("parameters", {}), **ctx}
    def repl(m):
        k = m.group(1)
        val = merged.get(k, "")
        return str(val)
    return re.sub(r"\{(\w+)\}", repl, template)


def weight_limit_kg() -> float:
    return float(param("weight_limit_kg", 22.5))


def throw_ratio() -> float:
    return float(param("throw_ratio", 6000))


def factory_warehouse_columns() -> Dict[int, str]:
    return {int(k): v for k, v in load_settings().get("factory_warehouse_columns", {}).items()}


def forwarder_column_map() -> Dict[str, int]:
    raw = load_settings().get("forwarder_column_map", {})
    return {str(k): int(v) for k, v in raw.items()}
