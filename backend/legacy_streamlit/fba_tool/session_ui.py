"""侧边栏：任务历史与保存。"""
from __future__ import annotations

import streamlit as st

from fba_tool.session_store import (
    auto_task_name,
    delete_history_task,
    list_history_tasks,
    load_history_task,
    rename_history_task,
    save_history_task,
)


def render_task_history_panel():
    with st.expander("历史任务", expanded=False):
        st.caption("刷新页面后会自动恢复上次进度；也可在此保存 / 调阅历史任务。")
        current_name = st.session_state.get("task_name") or auto_task_name(dict(st.session_state))
        st.text(f"当前：{current_name}")

        custom = st.text_input("任务名称（保存时可自定义）", value="", placeholder="留空则自动命名", key="task_custom_name")
        c1, c2 = st.columns(2)
        if c1.button("保存当前任务", use_container_width=True, key="save_history_btn"):
            name = custom.strip() or None
            save_history_task(st.session_state, name=name)
            st.success(f"已保存：{st.session_state.task_name}")
            st.rerun()

        tasks = list_history_tasks()
        if not tasks:
            st.info("暂无历史任务。点击「保存当前任务」或「重新开始」时会自动存档。")
            return

        options = {f"{t['name']}  ({t.get('updated_at', '')})": t["id"] for t in tasks}
        pick_label = st.selectbox("选择历史任务", list(options.keys()), key="history_pick")
        task_id = options[pick_label]

        b1, b2, b3 = st.columns(3)
        if b1.button("加载", use_container_width=True, key="load_history_btn"):
            if load_history_task(st.session_state, task_id):
                st.success(f"已加载：{st.session_state.task_name}")
                st.rerun()
            else:
                st.error("加载失败。")
        rename_val = st.text_input("重命名选中任务", value="", key="history_rename_val")
        if b2.button("重命名", use_container_width=True, key="rename_history_btn"):
            if rename_val.strip() and rename_history_task(task_id, rename_val.strip()):
                st.success("已重命名。")
                st.rerun()
        if b3.button("删除", use_container_width=True, key="del_history_btn"):
            delete_history_task(task_id)
            st.success("已删除。")
            st.rerun()
