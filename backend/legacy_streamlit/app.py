from __future__ import annotations

import hashlib
import io
import uuid

import pandas as pd
import streamlit as st

from fba_tool.boxing import box_metrics, dataframe_to_sku_rows, generate_box_plan, plans_to_editor_df
from fba_tool.data_processing import (
    INPUT_COLUMNS,
    empty_input_df,
    load_from_excel,
    parse_smart_text,
    validate_step1,
    with_computed_columns,
)
from fba_tool.input_template import generate_input_template_bytes, ensure_template_on_disk
from fba_tool.deepseek_parser import parse_with_deepseek
from fba_tool.settings_ui import render_user_config_panel
from fba_tool.user_config import throw_ratio, weight_limit_kg
from fba_tool.excel_export import build_factory_horizontal
from fba_tool.fba_parser import build_factory_df, build_forwarder_df
from fba_tool.invoice_automation import (
    apply_grid_edits,
    build_invoice_draft,
    export_invoice_xlsx,
    styled_grid,
)
from fba_tool.perf_cache import step3_export_bundle, step4_export_bytes
from fba_tool.product_catalog_ui import render_product_catalog_panel
from fba_tool.session_store import (
    auto_task_name,
    load_autosave,
    new_blank_session,
    save_autosave,
    save_history_task,
)
from fba_tool.session_ui import render_task_history_panel
from fba_tool.shipment_validator import UploadParseResult, parse_uploads, validate_shipments
from fba_tool.template_loader import list_user_templates, template_path, templates_dir


def _step4_upload_fingerprint(csv_payload: list, pdf_payload: list) -> str:
    h = hashlib.sha256()
    for name, data in sorted(csv_payload + pdf_payload, key=lambda x: x[0]):
        h.update(name.encode("utf-8", errors="ignore"))
        h.update(data)
    return h.hexdigest()[:24]


def _get_step4_parsed(csv_payload: list, pdf_payload: list, upload_fp: str) -> UploadParseResult:
    if (
        upload_fp
        and st.session_state.get("step4_upload_parse_fp") == upload_fp
        and st.session_state.get("step4_upload_parse_result") is not None
    ):
        return st.session_state.step4_upload_parse_result
    parsed = parse_uploads(csv_payload, pdf_payload)
    st.session_state.step4_upload_parse_fp = upload_fp
    st.session_state.step4_upload_parse_result = parsed
    st.session_state.step4_preview_lines = parsed.status_lines
    st.session_state.step4_preview_errors = parsed.errors
    st.session_state.step4_preview_fp = upload_fp
    return parsed


def _clear_step4_validation():
    st.session_state.step4_upload_parse_fp = ""
    st.session_state.step4_upload_parse_result = None
    st.session_state.step4_validated = False
    st.session_state.step4_shipment_bundle = None
    st.session_state.step4_status_lines = []
    st.session_state.step4_validation_errors = []
    st.session_state.step4_factory_long = None
    st.session_state.step4_box_specs = None
    st.session_state.step4_box_items = None
    st.session_state.step4_forwarder_df = None
    st.session_state.step4_validated_fp = ""
    st.session_state.step4_throw_ratio = None


st.set_page_config(page_title="FBA智能装箱工具", layout="wide", page_icon="📦")

MAX_BOX_COLS = 5000


def _session_has_data() -> bool:
    df = st.session_state.get("input_df")
    if isinstance(df, pd.DataFrame) and not df.empty:
        return True
    if st.session_state.get("box_locked") or st.session_state.get("step4_validated"):
        return True
    return False


def _restart_workflow():
    if _session_has_data():
        save_history_task(st.session_state, name=None)
    new_blank_session(st.session_state)
    st.rerun()


def init_state():
    if not st.session_state.get("_store_loaded"):
        autosave = load_autosave()
        if autosave:
            from fba_tool.session_store import apply_to_session

            apply_to_session(st.session_state, autosave)
            st.session_state._restored_from_autosave = True
        st.session_state._store_loaded = True

    st.session_state.setdefault("task_id", str(uuid.uuid4()))
    st.session_state.setdefault("task_name", auto_task_name(dict(st.session_state)))
    st.session_state.setdefault("step", 1)
    st.session_state.setdefault("input_df", empty_input_df())
    st.session_state.setdefault("fnsku_overrides", {})
    st.session_state.setdefault("box_editor_df", pd.DataFrame(columns=["箱号", "来源", "SKU简称", "数量"]))
    st.session_state.setdefault("box_locked", False)
    st.session_state.setdefault("validation_errors", [])
    st.session_state.setdefault("step4_validated", False)
    st.session_state.setdefault("step4_shipment_bundle", None)
    st.session_state.setdefault("step4_preview_fp", "")
    st.session_state.setdefault("step4_upload_parse_fp", "")
    st.session_state.setdefault("step4_upload_parse_result", None)
    st.session_state.setdefault("step4_preview_lines", [])
    st.session_state.setdefault("step4_preview_errors", [])
    st.session_state.setdefault("step4_status_lines", [])
    st.session_state.setdefault("step4_validation_errors", [])
    st.session_state.setdefault("step4_factory_long", None)
    st.session_state.setdefault("step4_box_specs", None)
    st.session_state.setdefault("step4_box_items", None)
    st.session_state.setdefault("step4_forwarder_df", None)
    st.session_state.setdefault("step4_validated_fp", "")
    st.session_state.setdefault("step4_throw_ratio", None)
    st.session_state.setdefault("invoice_draft", None)
    st.session_state.setdefault("invoice_template_bytes", None)


def step_header():
    steps = [
        (1, "Step 1 录入"),
        (2, "Step 2 排箱"),
        (3, "Step 3 导出"),
        (4, "Step 4 回传校验"),
        (5, "Step 4.5 发票"),
    ]
    head_left, head_right = st.columns([6, 1])
    with head_left:
        st.title("亚马逊 FBA 智能装箱与货件处理工具")
        task_name = st.session_state.get("task_name", "")
        st.caption(
            f"U盘便携版 · 点击步骤名可跳转 · 当前任务：**{task_name}**（刷新后自动恢复）"
        )
        if st.session_state.pop("_restored_from_autosave", False):
            st.success(f"已从本地恢复上次进度（{task_name}）", icon="💾")
    with head_right:
        st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
        if st.button("重新开始", type="secondary", use_container_width=True, key="global_restart"):
            _restart_workflow()
    current = st.session_state.step
    st.progress(current / len(steps))

    nav_cols = st.columns([1, 0.06, 1, 0.06, 1, 0.06, 1, 0.06, 1])
    col_i = 0
    for i, (step_num, label) in enumerate(steps):
        with nav_cols[col_i]:
            if st.button(
                label,
                key=f"goto_step_{step_num}",
                use_container_width=True,
                type="primary" if current == step_num else "secondary",
            ):
                st.session_state.step = step_num
                st.rerun()
        col_i += 1
        if i < len(steps) - 1:
            with nav_cols[col_i]:
                st.markdown("<div style='text-align:center;padding-top:0.4rem'>➜</div>", unsafe_allow_html=True)
            col_i += 1
    st.divider()


def sidebar_panel():
    with st.sidebar:
        st.header("系统设置")
        st.text_input("DeepSeek API Key", type="password", key="deepseek_api_key", help="也可设置环境变量 DEEPSEEK_API_KEY")
        st.caption("智能文本解析需要 API Key；本地逗号分隔解析无需 Key。")
        st.divider()
        render_task_history_panel()
        st.divider()
        st.subheader("模板目录")
        st.code(str(templates_dir()), language=None)
        templates = list_user_templates()
        if templates:
            st.success("已检测到用户模板：")
            for name in templates:
                st.write(f"- {name}")
        else:
            st.info("将样表放入 templates/ 目录后，导出将严格对齐真实排版。")
        st.divider()
        render_product_catalog_panel(compact=True)
        st.divider()
        render_user_config_panel()
        st.divider()
        st.caption("也可使用页面右上角「重新开始」清空当前任务（会自动存入历史）。")


def render_step1():
    st.subheader("Step 1: 发货需求录入")
    left, right = st.columns([1, 1])

    with left:
        st.markdown("**快捷导入 · 智能文本**")
        smart_text = st.text_area("粘贴运营描述或表格文本", height=180, placeholder="例：HUI-2PCS 共120个，单箱24，箱规60x40x35cm，单重0.8kg...")
        c1, c2 = st.columns(2)
        if c1.button("本地规则解析", use_container_width=True):
            parsed = parse_smart_text(smart_text)
            if not parsed.empty:
                st.session_state.input_df = parsed
                st.success(f"已解析 {len(parsed)} 条 SKU。")
            else:
                st.warning("未解析到有效数据。")
        if c2.button("DeepSeek 智能解析", type="primary", use_container_width=True):
            try:
                parsed = parse_with_deepseek(smart_text, api_key=st.session_state.get("deepseek_api_key"))
                st.session_state.input_df = parsed
                st.success(f"DeepSeek 已识别 {len(parsed)} 条 SKU。")
            except Exception as exc:
                st.error(str(exc))

    with right:
        st.markdown("**快捷导入 · Excel（推荐）**")
        st.caption("① 下载标准样表 → ② 填入你的 SKU 数据 → ③ 上传样表自动解析")
        ensure_template_on_disk()
        st.download_button(
            "📥 下载录入样表(.xlsx)",
            data=generate_input_template_bytes(),
            file_name="发货录入样表.xlsx",
            type="primary",
            use_container_width=True,
        )
        upload = st.file_uploader("上传填好的样表", type=["xlsx", "xls"])
        if upload is not None:
            try:
                parsed, fnsku_map = load_from_excel(upload.getvalue())
                if parsed.empty:
                    st.warning("样表中未读到有效 SKU 行，请检查表头与必填列。")
                else:
                    st.session_state.input_df = parsed
                    if fnsku_map:
                        st.session_state.fnsku_overrides = {
                            **st.session_state.get("fnsku_overrides", {}),
                            **fnsku_map,
                        }
                    st.success(f"样表已导入 {len(parsed)} 条 SKU。")
            except Exception as exc:
                st.error(f"样表解析失败：{exc}")

    st.markdown("#### 可编辑数据网格")
    edited = st.data_editor(
        st.session_state.input_df,
        num_rows="dynamic",
        use_container_width=True,
        key="step1_editor",
    )
    st.session_state.input_df = edited[INPUT_COLUMNS] if not edited.empty else empty_input_df()

    computed = with_computed_columns(st.session_state.input_df)
    st.markdown("#### 预计整箱数 / 总净重 / 总毛重（实时计算）")
    st.dataframe(computed, use_container_width=True, hide_index=True)

    errors = validate_step1(st.session_state.input_df)
    if errors:
        err_df = pd.DataFrame(errors, columns=["行号", "缺失字段"])
        err_df["行号"] = err_df["行号"] + 1
        st.warning("以下单元格需补全后才能进入下一步：")
        st.dataframe(err_df, hide_index=True, use_container_width=True)

    if st.button("下一步", type="primary"):
        if errors:
            st.error("存在必填缺失，已拦截。")
        else:
            sku_rows = dataframe_to_sku_rows(st.session_state.input_df)
            plans, _ = generate_box_plan(sku_rows)
            st.session_state.box_editor_df = plans_to_editor_df(plans)
            st.session_state.box_locked = False
            st.session_state.step = 2
            st.rerun()


def _compute_tail_pool(editor_df: pd.DataFrame, sku_rows) -> pd.DataFrame:
    sku_map = {s.sku: s for s in sku_rows}
    shipped = editor_df.groupby("SKU简称")["数量"].sum().to_dict() if not editor_df.empty else {}
    rows = []
    for sku in sku_rows:
        total = int(sku.total_qty)
        packed = int(shipped.get(sku.sku, 0))
        remain = total - packed
        if remain > 0:
            rows.append({"SKU简称": sku.sku, "待排尾数": remain, "单个重量(kg)": sku.unit_weight_kg})
    if not rows:
        _, auto_tail = generate_box_plan(sku_rows)
        return auto_tail
    return pd.DataFrame(rows)


def _render_box_cards(metrics: pd.DataFrame):
    limit = weight_limit_kg()
    if metrics.empty:
        st.info("暂无箱子，请先在 Step 1 录入数据。")
        return
    cols = st.columns(min(3, len(metrics)))
    for i, (_, row) in enumerate(metrics.iterrows()):
        col = cols[i % len(cols)]
        overweight = bool(row["超重"])
        border = "🔴" if overweight else "🟢"
        ratio = min(float(row["毛重(kg)"]) / limit, 1.5)
        col.markdown(f"**{border} 第 {int(row['箱号'])} 箱**")
        col.write(f"SKU种类 {int(row['SKU种类'])} · 件数 {int(row['件数'])}")
        col.write(f"毛重 {row['毛重(kg)']} kg / 限 {limit} kg")
        col.progress(min(ratio, 1.0))
        if overweight:
            col.error("超重！请调整后再锁定。")


def render_step2():
    st.subheader("Step 2: 智能排箱工作台")
    sku_rows = dataframe_to_sku_rows(st.session_state.input_df)
    if st.session_state.box_editor_df.empty and sku_rows:
        plans, _ = generate_box_plan(sku_rows)
        st.session_state.box_editor_df = plans_to_editor_df(plans)

    col_a, col_b = st.columns([1, 2])
    with col_a:
        st.markdown("**待排尾数池**")
        tail_df = _compute_tail_pool(st.session_state.box_editor_df, sku_rows)
        st.dataframe(tail_df, use_container_width=True, hide_index=True)
        st.caption("人工凑箱：在右侧表格修改`箱号`/`数量`，或新增一行分配到目标箱。")

        with st.expander("快速分配尾数"):
            if not tail_df.empty:
                sku_pick = st.selectbox("SKU", tail_df["SKU简称"].tolist())
                qty_pick = st.number_input("数量", min_value=1, value=1, step=1)
                box_pick = st.number_input("目标箱号", min_value=1, value=1, step=1)
                if st.button("添加到目标箱"):
                    new_row = pd.DataFrame([{"箱号": box_pick, "来源": "混装", "SKU简称": sku_pick, "数量": qty_pick}])
                    st.session_state.box_editor_df = pd.concat([st.session_state.box_editor_df, new_row], ignore_index=True)
                    st.rerun()

    with col_b:
        st.markdown("**纸箱明细（可编辑）**")
        edited = st.data_editor(
            st.session_state.box_editor_df,
            num_rows="dynamic",
            use_container_width=True,
            key="step2_editor",
        )
        st.session_state.box_editor_df = edited

    metrics = box_metrics(st.session_state.box_editor_df, sku_rows)
    st.markdown("#### 实体纸箱视图与容量指示")
    _render_box_cards(metrics)
    st.dataframe(metrics, use_container_width=True, hide_index=True)

    overweight = metrics["超重"].any() if not metrics.empty else False
    b1, b2, b3 = st.columns([1, 1, 4])
    if b1.button("上一步"):
        st.session_state.step = 1
        st.rerun()
    if b2.button("确认锁定方案并下一步", type="primary"):
        if overweight:
            st.error(f"存在超重箱（>{weight_limit_kg()}kg），无法进入下一步。")
        elif st.session_state.box_editor_df.empty:
            st.error("装箱方案为空。")
        else:
            st.session_state.box_locked = True
            st.session_state.step = 3
            st.rerun()


def render_step3():
    st.subheader("Step 3: 前期报表预览与导出")
    if not st.session_state.box_locked:
        st.warning("请先在 Step 2 锁定装箱方案。")
        return

    sku_rows = dataframe_to_sku_rows(st.session_state.input_df)
    editor_df = st.session_state.box_editor_df
    actual_boxes = int(editor_df["箱号"].astype(int).max()) if not editor_df.empty else 0
    actual_skus = editor_df["SKU简称"].nunique() if not editor_df.empty else 0
    matrix, internal_bytes, amazon_bytes = step3_export_bundle(
        editor_df,
        sku_rows,
        st.session_state.get("fnsku_overrides", {}),
    )

    st.caption(f"当前方案：**{actual_skus}** 个 SKU · **{actual_boxes}** 箱（导出列数随实际箱数动态生成）")

    t1, t2 = st.tabs([f"内部留档预览（{actual_boxes} 箱）", f"Send to Amazon 预览（{actual_boxes} 箱）"])
    with t1:
        st.dataframe(matrix, use_container_width=True, hide_index=True)
    with t2:
        st.dataframe(matrix, use_container_width=True, hide_index=True)
        st.caption("导出时自动转换为 in / lb，并保留 Locale / Metadata 表头。")

    d1, d2 = st.columns(2)
    d1.download_button("下载内部表(.xlsx)", data=internal_bytes, file_name="内部留档表.xlsx", type="primary")
    d2.download_button("下载 Send to Amazon 模板(.xlsx)", data=amazon_bytes, file_name="Send to Amazon表格.xlsx", type="primary")

    b1, b2, _ = st.columns([1, 1, 4])
    if b1.button("上一步"):
        st.session_state.step = 2
        st.rerun()
    if b2.button("下一步"):
        st.session_state.step = 4
        st.rerun()


def render_step4():
    st.subheader("Step 4: 回传校验与下游分发")
    st.caption("支持批量拖拽多个 CSV 与 PDF，系统将按 **货件编号 (Shipment ID)** 自动配对，并按 **真实箱号 (U-index)** 重排后比对。")

    csv_files = st.file_uploader(
        "上传亚马逊装箱单 CSV（可多选）",
        type=["csv"],
        accept_multiple_files=True,
        key="step4_csv",
    )
    pdf_files = st.file_uploader(
        "上传箱唛 PDF（可多选）",
        type=["pdf"],
        accept_multiple_files=True,
        key="step4_pdf",
    )

    throw_ratio_val = st.number_input(
        "抛重系数",
        min_value=1000.0,
        max_value=10000.0,
        value=float(throw_ratio()),
        step=100.0,
        help="系统已开启智能换算：不论导入文件是英寸还是厘米，均会先统一转为 cm，再按此系数计算体积重。",
    )
    st.caption("智能换算已开启：in/cm、lb/kg 自动识别并统一为 cm 后计算体积重。")

    csv_payload = [(f.name, f.getvalue()) for f in csv_files] if csv_files else []
    pdf_payload = [(f.name, f.getvalue()) for f in pdf_files] if pdf_files else []
    upload_fp = _step4_upload_fingerprint(csv_payload, pdf_payload) if (csv_payload or pdf_payload) else ""

    if upload_fp and upload_fp != st.session_state.get("step4_validated_fp") and st.session_state.get("step4_validated"):
        st.info("检测到上传文件已变更，上次校验结果已失效，请重新点击「开始校验」。")
        _clear_step4_validation()

    if csv_payload or pdf_payload:
        if upload_fp != st.session_state.get("step4_upload_parse_fp"):
            with st.status("正在解析上传文件…", expanded=True) as parse_status:
                st.write(f"• 已选 **{len(csv_payload)}** 个 CSV、**{len(pdf_payload)}** 个 PDF")
                st.write("• 读取 CSV 货件编号与目的仓…")
                if pdf_payload:
                    st.write("• 解析 PDF 箱唛页（文件较多时可能需要数秒，请稍候）…")
                _get_step4_parsed(csv_payload, pdf_payload, upload_fp)
                parse_status.update(label="文件解析完成", state="complete")
        elif not st.session_state.get("step4_upload_parse_result"):
            _get_step4_parsed(csv_payload, pdf_payload, upload_fp)

        if st.session_state.step4_preview_lines or st.session_state.step4_preview_errors:
            st.markdown("#### 自动解析状态板")
            for line in st.session_state.step4_preview_lines:
                st.markdown(line)
            for err in st.session_state.step4_preview_errors:
                st.warning(err)

    btn_col1, btn_col2, _ = st.columns([1, 1, 3])
    run_validate = btn_col1.button("开始校验", type="primary", disabled=not (csv_payload and pdf_payload))
    if btn_col2.button("重新校验", disabled=not (csv_payload and pdf_payload)):
        _clear_step4_validation()
        st.session_state.step4_preview_fp = ""
        st.rerun()

    if run_validate:
        if not csv_payload:
            st.error("请至少上传一个 CSV。")
        elif not pdf_payload:
            st.error("请至少上传一个箱唛 PDF。")
        else:
            progress = st.progress(0, text="准备校验…")
            with st.status("正在校验货件数据…", expanded=True) as val_status:
                st.write("① 解析 CSV / PDF 并匹配货件编号…")
                progress.progress(20, text="解析文件中…")
                parsed = _get_step4_parsed(csv_payload, pdf_payload, upload_fp)
                result = validate_shipments(csv_payload, pdf_payload, parsed=parsed)
                st.write("② 按真实箱号 (U-index) 逐箱比对 SKU 数量…")
                progress.progress(55, text="逐箱比对中…")
                st.session_state.step4_status_lines = result.status_lines

                compare_errors = [e for e in result.errors if "错误：" in e]
                match_errors = [e for e in result.errors if e.startswith("⚠️") or e.startswith("❌")]
                st.write("③ 汇总校验结果…")
                progress.progress(80, text="生成下游表…")

                if compare_errors:
                    st.session_state.step4_validation_errors = compare_errors
                    _clear_step4_validation()
                    val_status.update(label="校验未通过：装箱数量不一致", state="error")
                    progress.progress(100, text="校验完成（存在差异）")
                elif match_errors:
                    st.session_state.step4_validation_errors = match_errors
                    _clear_step4_validation()
                    val_status.update(label="校验未通过：文件匹配不完整", state="error")
                    progress.progress(100, text="校验完成（匹配失败）")
                elif not result.ok:
                    st.session_state.step4_validation_errors = result.errors or ["校验未通过，请检查上传文件。"]
                    _clear_step4_validation()
                    val_status.update(label="校验未通过", state="error")
                    progress.progress(100, text="校验完成")
                else:
                    bundle = []
                    for pair in result.pairs:
                        csv_bytes = result.csv_bytes.get(pair.shipment_id)
                        pdf_bytes = result.pdf_bytes.get(pair.shipment_id)
                        if csv_bytes and pdf_bytes:
                            bundle.append(
                                {
                                    "shipment_id": pair.shipment_id,
                                    "warehouse": pair.warehouse_code,
                                    "csv_bytes": csv_bytes,
                                    "pdf_bytes": pdf_bytes,
                                }
                            )
                    factory_long = build_factory_df(result.all_box_items)
                    forwarder_df = build_forwarder_df(
                        result.all_box_specs,
                        result.all_box_items,
                        throw_ratio=throw_ratio_val,
                    )
                    st.session_state.step4_validated = True
                    st.session_state.step4_shipment_bundle = bundle
                    st.session_state.step4_factory_long = factory_long
                    st.session_state.step4_box_specs = result.all_box_specs
                    st.session_state.step4_box_items = result.all_box_items
                    st.session_state.step4_forwarder_df = forwarder_df
                    st.session_state.step4_validated_fp = upload_fp
                    st.session_state.step4_throw_ratio = throw_ratio_val
                    st.session_state.step4_validation_errors = []
                    val_status.update(label="全部货件校验通过", state="complete")
                    progress.progress(100, text="校验通过")
            st.rerun()

    if st.session_state.step4_validation_errors:
        st.markdown("#### 校验进度")
        for line in st.session_state.step4_status_lines:
            st.markdown(line)
        if any("错误：" in e for e in st.session_state.step4_validation_errors):
            st.error("发现装箱差异，请核对以下真实箱号：")
        else:
            st.error("文件匹配或校验未通过：")
        for err in st.session_state.step4_validation_errors[:50]:
            st.markdown(err) if "错误：" in err else st.warning(err)

    if st.session_state.get("step4_validated") and st.session_state.get("step4_factory_long") is not None:
        st.markdown("#### 校验进度")
        for line in st.session_state.step4_status_lines:
            st.markdown(line)
        st.success("全部货件校验通过！可下载工厂表 / 货代表，或进入 Step 4.5 发票。")

        factory_long = st.session_state.step4_factory_long
        box_specs = st.session_state.step4_box_specs
        forwarder_df = st.session_state.step4_forwarder_df
        if box_specs is not None and throw_ratio_val != st.session_state.get("step4_throw_ratio"):
            st.caption("抛重系数已变更，货代表已按新系数重新计算。")
            forwarder_df = build_forwarder_df(
                box_specs,
                st.session_state.get("step4_box_items"),
                throw_ratio=throw_ratio_val,
            )

        factory_df = build_factory_horizontal(factory_long)

        st.markdown("#### 工厂表预览（横向跨列）")
        st.dataframe(factory_df, use_container_width=True, hide_index=True)
        st.markdown("#### 货代表预览")
        st.dataframe(forwarder_df, use_container_width=True, hide_index=True)

        factory_bytes, forwarder_bytes = step4_export_bytes(factory_long, forwarder_df)
        d1, d2 = st.columns(2)
        d1.download_button(
            "下载工厂表(.xlsx)",
            data=factory_bytes,
            file_name="工厂表.xlsx",
            type="primary",
            key="step4_dl_factory",
        )
        d2.download_button(
            "下载货代表(.xlsx)",
            data=forwarder_bytes,
            file_name="货代表.xlsx",
            type="primary",
            key="step4_dl_forwarder",
        )

        if st.button("进入 Step 4.5 货代发票", type="primary", key="step4_goto_invoice"):
            st.session_state.step = 5
            st.rerun()

    if st.button("回到 Step 3", key="step4_back_step3"):
        st.session_state.step = 3
        st.rerun()


def render_step45():
    st.subheader("Step 4.5: 货代发票智能生成")
    if not st.session_state.get("step4_validated") or not st.session_state.get("step4_shipment_bundle"):
        st.warning("请先在 Step 4 完成 CSV/PDF 校验。")
        if st.button("返回 Step 4"):
            st.session_state.step = 4
            st.rerun()
        return

    bundle = st.session_state.step4_shipment_bundle
    st.caption("🟢 精准提取 · 🔵 产品信息表 · 🟡 AI 推理需复核 · 🔴 必填待补（ID号须手工填写）")

    default_tpl = template_path("待填写的发票模板.xlsx") or template_path("发票模板.xlsx")
    tpl_hint = str(default_tpl) if default_tpl else str(templates_dir() / "待填写的发票模板.xlsx")

    st.markdown("#### 发票模板")
    st.info(
        f"**永久路径（推荐）**：`{tpl_hint}`\n\n"
        "将您的《待填写的发票模板.xlsx》放入上述 `templates/` 目录；"
        "也可在下方临时上传（仅本次会话）。"
    )

    col_u, col_s = st.columns([2, 1])
    uploaded_tpl = col_u.file_uploader("或上传发票模板 (.xlsx)", type=["xlsx"], key="invoice_tpl_upload")
    shipment_ids = [b["shipment_id"] for b in bundle]
    pick = col_s.selectbox("选择货件", shipment_ids, index=0)
    ship_ctx = next(b for b in bundle if b["shipment_id"] == pick)

    if uploaded_tpl is not None:
        st.session_state.invoice_template_bytes = uploaded_tpl.getvalue()
    elif not st.session_state.get("invoice_template_bytes") and default_tpl and default_tpl.exists():
        st.session_state.invoice_template_bytes = default_tpl.read_bytes()
    elif not st.session_state.get("invoice_template_bytes"):
        st.error("未找到发票模板。请将文件放到 templates/ 或上传。")
        return

    api_key = st.session_state.get("deepseek_api_key", "")

    if st.button("智能生成发票", type="primary"):
        with st.spinner("解析中：CSV/PDF 精准映射 → 产品信息表 → DeepSeek 补全空缺..."):
            try:
                draft, _usage = build_invoice_draft(
                    ship_ctx["csv_bytes"],
                    ship_ctx["pdf_bytes"],
                    st.session_state.invoice_template_bytes,
                    api_key=api_key or None,
                )
                st.session_state.invoice_draft = draft
                st.session_state.invoice_grid_df = draft.to_grid_df()
            except Exception as exc:
                st.error(f"生成失败：{exc}")

    draft = st.session_state.get("invoice_draft")
    if draft is None or draft.shipment_id != pick:
        st.caption("选择货件后点击「智能生成发票」。")
    else:
        grid_df = st.session_state.get("invoice_grid_df", draft.to_grid_df())
        st.markdown("#### 发票数据审核（可编辑）")
        st.caption("🟢 绿色=CSV/PDF · 🔵 蓝色=产品信息表 · 🟡 黄色=AI 需复核 · 🔴 红色=必填（ID号）")
        try:
            st.dataframe(styled_grid(grid_df), use_container_width=True, hide_index=True)
        except Exception:
            st.dataframe(grid_df, use_container_width=True, hide_index=True)

        edited = st.data_editor(
            grid_df,
            use_container_width=True,
            hide_index=True,
            key=f"invoice_editor_{pick}",
            column_config={"值": st.column_config.TextColumn("值", width="large")},
        )
        st.session_state.invoice_grid_df = edited
        draft = apply_grid_edits(draft, edited)
        st.session_state.invoice_draft = draft

        missing = draft.missing_required()
        if missing:
            st.warning(
                f"部分必填项未补全：{', '.join(missing)}（如 ID 号须从亚马逊后台手工复制）。"
                "仍可导出，请在 Excel 中补全后再提交货代。"
            )

        if st.button("导出最终发票", type="primary"):
            try:
                out = export_invoice_xlsx(st.session_state.invoice_template_bytes, draft)
                st.download_button(
                    "下载发票.xlsx",
                    data=out,
                    file_name=f"货代发票_{draft.shipment_id}.xlsx",
                    type="primary",
                )
                st.success("已生成，模板样式与 Sheet2 已保留，仅写入对应单元格。")
            except Exception as exc:
                st.error(str(exc))

    b1, _ = st.columns([1, 4])
    if b1.button("返回 Step 4"):
        st.session_state.step = 4
        st.rerun()


def main():
    init_state()
    sidebar_panel()
    step_header()
    if st.session_state.step == 1:
        render_step1()
    elif st.session_state.step == 2:
        render_step2()
    elif st.session_state.step == 3:
        render_step3()
    elif st.session_state.step == 4:
        render_step4()
    elif st.session_state.step == 5:
        render_step45()
    save_autosave(st.session_state)


if __name__ == "__main__":
    main()
