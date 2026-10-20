# golden 回归（方案 v7 §5.1）

- `customs_manifest.csv`：38 份报关样例（A 级 14 份 = 单价规则核对“符合”的 13 份 + JUS6HB30；B 级 24 份）。
- `invoice_manifest.csv`：发票样例，只有 SEND 5 份 + 九方 8 份（Q6：琪珞不进 golden；已被 D-2026-10-16-04 取代，S4a 盘点全部发票模板后补入）。
- `product_master_golden.json`：固定的产品库快照。`declared_value` 一律为空，`listing_price` 取样例售价。按新口径（领星 listing_price 第一、手填第二；依据 `docs/用户决策记录.md` D-2026-10-16-01：06:04 对话原话 + 06:27 书面确认，美东），申报价来源是 lingxing，**不再期望“回落售价”警告**；`invoice_manifest.csv` 13 条 expected_warnings 已改为“无”。手填价存在但未采用时才会出 `manual_price_not_used` 提示（快照里没有手填价，所以不出）。D-01 已被 D-12 修订（正常价 = regular_price 或 90 天内非促销价，促销低 5% 以上按正常价申报并提示 `promo_price_not_used`）；快照没有 regular_price / 促销历史，所以 golden 期望不变，D-12 由 `test_s8fix1_dec12_e2e.py` 端到端覆盖。
- `samples/`：样例**副本**（原始文件在用户测试目录，只读不动）。
- `compare_golden.py`：比对工具。S3/S4 的导出完成后，用 `compare_files()` 接入。
- **报关 golden（S3 已接入）**：`customs_inputs.json` 由 `build_customs_inputs.py` 生成（`python -m tests.golden.build_customs_inputs`）。A 级 14 份的输入取发票样例（SEND 5 份、九方 7 份、第 5/6 批旧模板 10 份在 `samples/invoice_legacy/`），B 级 24 份没有发票，输入取报关样例自身的结构字段，只比结构字段。`test_golden_customs.py` 对 38 份分别导出 .xlsx 和 .xls 逐字段比对，“失败”必须为 0；已知差异（净重新口径、口岸、委托书有效期、样例错误）写在 `expected_diff`。
- 发票 golden 的 `input_paths` 里标【S4补】的条目，在 S4 接入发票导出时补齐。
- 琪珞 T6/T5、德速 T3 没有进 golden manifest，由 `test_s8fix1_invoice_adapters.py` 对货代原件逐格比对（德速第 9 批、琪珞 T6 第 6/7 批；T5 按 CSV 汇总核对）。
- 运行：`cd backend && .venv\Scripts\python.exe -m pytest test_golden_infra.py -q`
