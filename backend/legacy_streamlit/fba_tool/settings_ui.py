"""侧边栏：用户可编辑参数与公式，保存到 config/ 目录持久化。"""
from __future__ import annotations

import json

import streamlit as st

from fba_tool.user_config import (
    DEFAULT_FORMULAS,
    DEFAULT_SETTINGS,
    load_formulas,
    load_settings,
    reset_all_to_defaults,
    save_formulas,
    save_settings,
)


def render_user_config_panel():
    st.subheader("参数与公式（持久化）")
    st.caption("修改后点击「保存配置」，写入 config/ 目录；U盘拷贝后下次自动生效，无需改代码。")

    settings = load_settings()
    formulas = load_formulas()
    params = settings.get("parameters", {})

    with st.expander("业务参数", expanded=False):
        p = params.copy()
        p["amazon_max_boxes"] = st.number_input("亚马逊单票最大箱数", 1, 500, int(p.get("amazon_max_boxes", 130)))
        p["weight_limit_kg"] = st.number_input("单箱重量上限(kg)", 1.0, 100.0, float(p.get("weight_limit_kg", 22.5)))
        p["max_mixed_items_per_box"] = st.number_input("混装单箱最大件数", 1, 500, int(p.get("max_mixed_items_per_box", 40)))
        p["throw_ratio"] = st.number_input("抛重系数", 1000.0, 10000.0, float(p.get("throw_ratio", 6000)))
        p["volume_divisor"] = st.number_input("体积重除数（内部表）", 1000.0, 10000.0, float(p.get("volume_divisor", 6000)))
        p["kg_to_lb_factor"] = st.number_input("kg→lb 系数", 0.1, 10.0, float(p.get("kg_to_lb_factor", 2.20462)))
        p["inch_to_cm_factor"] = st.number_input("in→cm 系数", 0.1, 10.0, float(p.get("inch_to_cm_factor", 2.54)))
        p["internal_gross_lb_factor"] = st.number_input("内部表 kg→lb（毛重）", 0.1, 10.0, float(p.get("internal_gross_lb_factor", 2.2)))
        p["sta_box_prefix"] = st.text_input("亚马逊箱唛前缀", value=str(p.get("sta_box_prefix", "P1 - B")))
        p["factory_data_start_row"] = st.number_input("工厂表数据起始行", 1, 100, int(p.get("factory_data_start_row", 4)))
        p["forwarder_data_start_row"] = st.number_input("货代表数据起始行", 1, 100, int(p.get("forwarder_data_start_row", 3)))
        p["input_template_blank_rows"] = st.number_input("录入样表空白行数", 1, 100, int(p.get("input_template_blank_rows", 10)))
        settings["parameters"] = p

    with st.expander("Excel 公式模板", expanded=False):
        st.caption("占位符：{row} {col} {box_no} {first_box_col} {last_box_col} {length_row} {width_row} {height_row} {weight_row} {volume_divisor} 等")
        formulas_text = st.text_area(
            "formulas.json 内容",
            value=json.dumps(formulas, ensure_ascii=False, indent=2),
            height=280,
            key="formulas_editor",
        )

    with st.expander("仓库列映射（工厂表，可选）", expanded=False):
        st.caption("留空 `{}` 则自动从 templates/工厂表.xlsx 第2行识别；也可手动指定列号→仓库代码。")
        wh_text = st.text_area(
            "factory_warehouse_columns",
            value=json.dumps(settings.get("factory_warehouse_columns", {}), ensure_ascii=False, indent=2),
            height=120,
            key="factory_wh_editor",
        )

    c1, c2, c3 = st.columns(3)
    if c1.button("保存配置", type="primary", use_container_width=True):
        try:
            settings["factory_warehouse_columns"] = json.loads(wh_text or "{}")
            save_settings(settings)
            save_formulas(json.loads(formulas_text))
            st.success("已保存到 config/user_settings.json 与 config/formulas.json")
        except Exception as exc:
            st.error(f"保存失败：{exc}")

    if c2.button("恢复默认", use_container_width=True):
        reset_all_to_defaults()
        st.success("已恢复默认配置")
        st.rerun()

    if c3.button("打开 config 目录说明", use_container_width=True):
        st.info(
            "config/user_settings.json — 参数\n"
            "config/formulas.json — 公式\n"
            "config/sku_mapping.json — SKU简写\n"
            "config/fnsku_mapping.json — FNSKU\n"
            "templates/*.xlsx — 表格版式（直接替换文件即可）"
        )
