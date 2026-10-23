# FBA Smart Tool · R12 软件正式交付说明

- **交付时间**：2026-10-21（Asia/Hong_Kong）
- **产品版本**：V3.3
- **仓库**：https://github.com/huangyuehui1998-dev/fba-smart-tool（private）
- **交付基线**：`main` @ `1cc3a229c88c7a9cfeeb4258db0942ad3c93594f`
- **合入 PR**：[#11](https://github.com/huangyuehui1998-dev/fba-smart-tool/pull/11)（squash merge；原 head `634fefa`）
- **授权**：Marco 批准合并；随后批准关闭 r11 PR #1–#10 并跑 main 冒烟；本日确认「软件交付」

> 文中 `delivery_review_*`、`cross_score_*`、`figma_review_*`、`main_smoke_*` 等评审与冒烟文件，以及 `/workspace/...` 下的复核材料，留在 box，不在本仓库。同目录交付文件：`SOFTWARE_DELIVERY_R12_test.md`、`SOFTWARE_DELIVERY_R12_ops.md`、`OPTIMIZATION_PLAN_r12.7.md`。

## 1. 交付范围

R12-01…R12-21（含 N1–N7 修复），覆盖箱规与实测对比、申报价值/汇率、安全与历史路径、产品主数据与领星零售价同步、STA 预检、Playwright 点击基线、以及箱规库 Figma 定稿等。细节见 PR #11 描述与 `OPTIMIZATION_PLAN_r12.7.md`。

## 2. 质量门（均已达标）

| 门 | 结果 | 证据 |
|---|---|---|
| 交付关 · 独立分 | 代码 / 测试 / 运营 均为 **100** | `delivery_review_*_r5.md` |
| 交付关 · 交叉互评 | 六向互评均为 **100** | `cross_score_*_r5.md` 等 |
| R12-21 Figma | 三方定稿均为 **100** | `figma_review_*`；设计稿 https://www.figma.com/design/EuCkRxLTMi5dSvh3Y9I88q |
| 合入后 main 冒烟 | 代码方 + 测试方均 **通过** | `main_smoke_1cc3a229.md`、`main_smoke_test_1cc3a229.md` |

### 合入后冒烟锚点（与交付 r5 一致，无回退）

- 第 13 批口径 B：总差 **+320.20** = 进位 **+1.30** + 箱级 **+318.90**（154 行）；实重差 −28.37 仅参考
- CL2 净重 **254.4**；账单匹配 5/5
- UI-Q：`playwright_live=true`；基线 18+8 → 当前 9+2；事件 26 → 11
- 第 15 批账单≠Σ：**不算总差**（已落地）

## 3. 仓库状态

- `main` tip = 交付基线 `1cc3a229`
- r11 PR #1–#10：**已关闭不合并**（注明 superseded by #11）
- 当前无打开的 PR
- 真实业务数据仅在 box `/workspace/fba_tool/realdata`，**未进仓**

## 4. 明确不在本次软件交付内 / 遗留

1. **第 15 批 101 vs Σ100**：运营按账单付、标待确认；请 Marco 问九方后再定是否改规则。软件**不改计费**，最多后续加「账单≠Σ」提示。
2. **第 13 批 STA**：继续 **人工上传**；软件导出 + 预检已够，**不做代传 / SP-API 写入**。
3. 政策类 `pending_verification`（待核实）项：界面已标，非本轮计费改动。
4. 前端既有 `tsc` 报错（`workflow-context.tsx`）为合入前已知项，未纳入本轮阻断。

## 5. 使用说明（最短）

- 检出或部署：`main` @ `1cc3a229`
- 本地冒烟：`scripts/box_smoke.sh` / `pytest -m realdata_smoke`（需 realdata）
- UI-Q：`python3 scripts/e2e/click_count.py --live` 再 `--check`
- 箱规库 / 对比页设计：见上述 Figma 链接（实现以合入代码为准；Figma 为定稿参照）

## 6. 三方会签

| 角色 | 结论 | 签字栏 |
|---|---|---|
| 代码（FBA发货软件代码） | **同意交付** · 基线 `1cc3a229` | 已签 · 2026-10-21 |
| 测试（FBA发货软件测试） | **同意交付** · 基线 `1cc3a229` | 已签 · 见 `SOFTWARE_DELIVERY_R12_test.md` |
| 运营（FBA发货软件 亚马逊运营专员） | **同意交付** · 基线 `1cc3a229`（保留意见见 ops 会签，不挡交付） | 已签 · 见 `SOFTWARE_DELIVERY_R12_ops.md` |

---

**结论**：代码 / 测试 / 运营三方均已会签 **同意交付**。软件交付完成。业务遗留仅第 15 批问九方与 STA 人工上传流程，不阻塞本基线使用。
