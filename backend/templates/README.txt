# 【现状说明（s8-docs，2026-10-16）】下面写的是早期“待填写的发票模板.xlsx”填格流程（/api/invoice/generate，仍可用）。
# 现行 Step 4.5 按货代导出用 backend/templates/forwarders/*.xlsx（send、jiufang、qiluo_t6、qiluo_t5、deshu_t3），
# 登记在 backend/config/invoice_export_forwarders.default.json；报关模板在 backend/templates/customs/。
#
# 将你的真实模板文件放在此目录，系统导出/解析时会自动对齐：

#

# 【Step 4.5 货代发票模板 — 重要】

# 文件名：待填写的发票模板.xlsx

# 完整路径示例：

#   U盘版：  FBAWizard\templates\待填写的发票模板.xlsx

#   开发版： TEST2\templates\待填写的发票模板.xlsx

#

# 也可在 Step 4.5 页面直接上传（仅当次有效）。

# 单元格映射：程序按模板内标签文字自动识别；若识别不准可编辑 config/invoice_mapping.json

# 历史报关参考：config/invoice_history.json

#

# 其他模板：

# - Send to Amazon表格.xlsx  ← Step 3 亚马逊上传

# - 内部留档表.xlsx         ← Step 3 内部留档

# - 工厂表.xlsx / 货代表.xlsx ← Step 4 导出

#

# 上传后无需改代码，重启应用即可生效。

# 业务参数与 Excel 公式可在侧边栏或 config/user_settings.json、config/formulas.json 中修改并持久保存。

