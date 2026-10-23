# R12 软件正式交付 · 测试会签

- **角色**：FBA发货软件测试
- **时间**：2026-10-21（Asia/Hong_Kong）
- **对照草稿**：`SOFTWARE_DELIVERY_R12.md`
- **基线**：`main` @ `1cc3a229c88c7a9cfeeb4258db0942ad3c93594f`
- **约束**：独立核对；**未改代码**；未碰共享 8010

> 本文件点名的 `delivery_review_*`、`cross_score_*`、`figma_review_*`、`main_smoke_*`、`post_r12_open_items_test.md` 等留在 box，不在本仓库。`SOFTWARE_DELIVERY_R12.md` 在同目录。

## 会签结论

**同意交付。**  
以 `1cc3a229` 为正式软件交付基线。草稿第 1–5 节与测试侧证据一致；第 4 节遗留划分可接受，**不阻塞**本基线使用。

无保留意见会阻断交付。下列仅为登记项（非扣分、不要求本轮改码）。

---

## 核对表（相对草稿）

| 草稿主张 | 测试侧核对 | 结果 |
|---|---|---|
| 基线 sha `1cc3a229…` / PR #11 squash | `gh`：`main` tip = `1cc3a229c88c7a9cfeeb4258db0942ad3c93594f`；message 含 #11 | ✅ |
| 交付关独立分三方 100 | 本侧 `delivery_review_test_r5.md` = **100**（634fefa）；代码/运营 r5 文件亦自称 100 | ✅ |
| 交叉互评 100 | 本侧 `cross_score_test_on_code_r5.md`、`cross_score_test_on_ops_r5.md` = **100**；代码方对测试/运营 r5 亦 100（既有文件） | ✅ |
| Figma R12-21 三方 100 | 本侧 `figma_review_test_r2.md` = **100**；稿链 EuCkRxLTMi5dSvh3Y9I88q | ✅ |
| 合入后 main 冒烟通过 | 本侧 `main_smoke_test_1cc3a229.md` = **通过**；证据 `review/work/main_smoke_1cc3a229/`。另见代码方 `main_smoke_1cc3a229.md` | ✅ |
| 冒烟锚点（320.20 / 1.30 / 318.90 / 254.4 / UI-Q 18+8→9+2） | 与本侧 main 冒烟及 r5 实测一致 | ✅ |
| 第 15 批不算总差已落地 | 与 `post_r12_open_items_test.md`、方案 §8 / R12-07「不断言」一致 | ✅ |
| PR #1–#10 已关闭不合并 | `gh`：#1–#10 均为 **CLOSED**；当前 **无打开 PR** | ✅ |
| realdata 未进仓 | 交付与冒烟全程只读 `/workspace/fba_tool/realdata`；仓库内无真实批次业务文件（与既定规则一致） | ✅ |
| 遗留：15 批问九方 / STA 人工 / pending_verification / 已知 tsc | 与测试开放项结论一致；**不作为交付阻断** | ✅ 接受 |

## 测试侧质量门摘要（本方亲测）

| 门 | 分/结果 | 文件 |
|---|---|---|
| 交付关 r5 | 100 | `delivery_review_test_r5.md` |
| 互评代码 r5 / 运营 r5 | 100 / 100 | `cross_score_test_on_code_r5.md`、`cross_score_test_on_ops_r5.md` |
| Figma r2 | 100 | `figma_review_test_r2.md` |
| main@1cc3a229 冒烟+UI-Q | 通过 | `main_smoke_test_1cc3a229.md` |

冒烟关键数：S-01…S-07 全过；carry **1.3** / total **320.2** / box **318.9** / actual **−28.37** / rows **154**；net **254.4**；UI-Q check+live exit 0（**9+2**）；repro **0/12**；vitest **90**；download/穿越 **400**。

## 登记项（不阻断）

1. **前端既有 `tsc`（workflow-context）**：草稿已声明合入前已知、非本轮阻断——测试同意按已知债跟踪，不挡交付。
2. **Figma 确认弹窗黄条**：评审时图层曾有「如需启用，请到箱规库点设为默认」而截图未必可见——属展示一致性备注；定稿分已 100，**不要求本轮改码**。
3. **第 15 批 / STA 人工**：维持「软件不改计费、不做代传」；后续若九方确认或产品要「账单≠Σ」提示，另开条目，不回溯本基线。

## 签字

| 项 | 内容 |
|---|---|
| 结论 | **同意交付** |
| 基线 | `1cc3a229c88c7a9cfeeb4258db0942ad3c93594f` |
| 角色 | FBA发货软件测试 |
| 日期 | 2026-10-21（Asia/Hong_Kong） |

请代码方将主说明会签表「测试」一行更新为：同意交付 · 见 `SOFTWARE_DELIVERY_R12_test.md`。
