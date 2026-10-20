"""Streamlit 侧纯计算缓存（导出 / 矩阵），不改变业务结果。"""
from __future__ import annotations

import json
from io import StringIO

import pandas as pd
import streamlit as st

from fba_tool.config_cache import template_mtime
from fba_tool.excel_export import (
    build_box_matrix,
    export_amazon_template,
    export_factory_sheet,
    export_forwarder_quote,
    export_internal_archive,
)
from fba_tool.models import SkuRow


def sku_rows_to_tuple(sku_rows: list[SkuRow]) -> tuple:
    return tuple(
        (
            s.sku,
            s.total_qty,
            s.carton_qty,
            s.length_cm,
            s.width_cm,
            s.height_cm,
            s.unit_weight_kg,
            s.carton_tare_kg,
            s.carton_gross_kg,
        )
        for s in sku_rows
    )


def sku_rows_from_tuple(tup: tuple) -> list[SkuRow]:
    return [
        SkuRow(
            sku=r[0],
            total_qty=int(r[1]),
            carton_qty=int(r[2]),
            length_cm=float(r[3]),
            width_cm=float(r[4]),
            height_cm=float(r[5]),
            unit_weight_kg=float(r[6]),
            carton_tare_kg=float(r[7]),
            carton_gross_kg=r[8] if r[8] is None else float(r[8]),
        )
        for r in tup
    ]


@st.cache_data(show_spinner=False, max_entries=24)
def cached_build_box_matrix(editor_json: str) -> pd.DataFrame:
    df = pd.read_json(StringIO(editor_json))
    if df.empty:
        return build_box_matrix(df)
    return build_box_matrix(df)


@st.cache_data(show_spinner=False, max_entries=12)
def cached_export_internal(
    editor_json: str,
    sku_tuple: tuple,
    fnsku_json: str,
    internal_tpl_mtime: float,
) -> bytes:
    editor_df = pd.read_json(StringIO(editor_json))
    sku_rows = sku_rows_from_tuple(sku_tuple)
    fnsku = json.loads(fnsku_json) if fnsku_json else {}
    return export_internal_archive(editor_df, sku_rows, fnsku_overrides=fnsku)


@st.cache_data(show_spinner=False, max_entries=12)
def cached_export_amazon(
    editor_json: str,
    sku_tuple: tuple,
    fnsku_json: str,
    amazon_tpl_mtime: float,
) -> bytes:
    editor_df = pd.read_json(StringIO(editor_json))
    sku_rows = sku_rows_from_tuple(sku_tuple)
    fnsku = json.loads(fnsku_json) if fnsku_json else {}
    return export_amazon_template(editor_df, sku_rows, fnsku_overrides=fnsku)


@st.cache_data(show_spinner=False, max_entries=24)
def cached_export_factory(factory_json: str, factory_tpl_mtime: float) -> bytes:
    df = pd.read_json(StringIO(factory_json))
    return export_factory_sheet(df)


@st.cache_data(show_spinner=False, max_entries=24)
def cached_export_forwarder(forwarder_json: str, forwarder_tpl_mtime: float) -> bytes:
    df = pd.read_json(StringIO(forwarder_json))
    return export_forwarder_quote(df)


def step3_export_bundle(editor_df: pd.DataFrame, sku_rows: list[SkuRow], fnsku_overrides: dict) -> tuple[pd.DataFrame, bytes, bytes]:
    editor_json = editor_df.to_json(force_ascii=False)
    sku_tuple = sku_rows_to_tuple(sku_rows)
    fnsku_json = json.dumps(fnsku_overrides or {}, sort_keys=True, ensure_ascii=False)
    matrix = cached_build_box_matrix(editor_json)
    internal = cached_export_internal(
        editor_json,
        sku_tuple,
        fnsku_json,
        template_mtime("内部留档表.xlsx"),
    )
    amazon = cached_export_amazon(
        editor_json,
        sku_tuple,
        fnsku_json,
        template_mtime("Send to Amazon表格.xlsx"),
    )
    return matrix, internal, amazon


def step4_export_bytes(factory_long: pd.DataFrame, forwarder_df: pd.DataFrame) -> tuple[bytes, bytes]:
    factory_json = factory_long.to_json(force_ascii=False)
    forwarder_json = forwarder_df.to_json(force_ascii=False)
    return (
        cached_export_factory(factory_json, template_mtime("工厂表.xlsx")),
        cached_export_forwarder(forwarder_json, template_mtime("货代表.xlsx")),
    )
