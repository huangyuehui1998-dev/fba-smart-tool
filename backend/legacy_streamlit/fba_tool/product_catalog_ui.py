"""首页/侧边栏：产品信息表维护（可选）。"""
from __future__ import annotations

import streamlit as st

from fba_tool.product_catalog import (
    CANONICAL_NAME,
    catalog_status_text,
    find_catalog_path,
    load_product_catalog,
    save_catalog_upload,
)
from fba_tool.template_loader import templates_dir


def render_product_catalog_panel(compact: bool = False):
    title = "产品信息表（可选）" if compact else "产品信息表维护（非流程必选项）"
    with st.expander(title, expanded=not compact):
        st.caption("发票报关字段：本地产品表 → 找不到再用 DeepSeek。不影响主流程 Step 1–4。")
        st.info(f"**{catalog_status_text()}**")
        st.code(str(templates_dir() / CANONICAL_NAME), language=None)

        upload = st.file_uploader(
            "上传新版产品信息表 (.csv / .xlsx)",
            type=["csv", "xlsx", "xls"],
            key="product_catalog_upload",
        )
        if upload is not None and st.button("保存并更新产品信息表", key="save_catalog_btn"):
            dest = save_catalog_upload(upload.getvalue(), upload.name)
            cat = load_product_catalog(dest)
            st.success(f"已更新 {dest.name}（{cat.row_count if cat else 0} 条 SKU）")
            st.rerun()

        path = find_catalog_path()
        if path and path.exists():
            st.download_button(
                "下载当前产品信息表",
                data=path.read_bytes(),
                file_name=path.name,
                key="dl_product_catalog",
            )
            cat = load_product_catalog(path)
            if cat and cat.records:
                preview = [
                    {
                        "SKU": r.sku,
                        "中文品名": r.chinese_name,
                        "海关编码": r.hs_code,
                        "材质": (r.material[:40] + "…") if len(r.material) > 40 else r.material,
                        "成本": r.unit_cost,
                    }
                    for r in list(cat.records.values())[:5]
                ]
                st.caption("预览（前 5 条）")
                st.dataframe(preview, hide_index=True, use_container_width=True)
