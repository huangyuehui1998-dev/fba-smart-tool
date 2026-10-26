# Accept-currency · 币种短验收规格（U5-M2-P2 / OPS5-O3-B）

> **本页 = 签收壳（壳就绪 · 待测）。**  
> **≠「币种已关」。** 勾选一律 **待测**，过线后再改。  
> **≠ Publish**；ops 不 Publish；扫描 ≠ 已打开。  
> **五包未齐不得称「M2 首包已全部完成」。**（P1 刷箱已过线 ≠ 本包；P3–P5 仍待）

---

## 0. 封面链（强制 · OPS5-O3-B）

| 链 | 路径 / 口径 | 对本包 |
|---|---|---|
| **OPS5-O3-B** | `review/OPT_plan_ops_r5.md` §OPS5-O3-B · `Accept-currency.md`；至少 1 条真实/脱敏对照 | **本包入口** |
| **OPS3-O3** | `review/OPT_plan_ops_r3.md` §OPS3-O3 · 领星币种 + 手工价可执行验收包 | **产品口径源**（夹具≥2；xlsx/MCP 同口径；文档三行 checklist；人民币成本 / USD 零售硬口径） |
| **OPS4-O5** | `review/OPT_plan_ops_r4.md` §OPS4-O5 · 币种/箱规/九方 M2 执行包挂载 | **挂载时机**（M2 启动后；报告文件名约定） |
| 统一项 | **U5-M2-P2** ← OPS5-O3-B ← OPS4-O5 ← OPS3-O3 / U3-P1-01 / U2-P1-01 | `review/OPT_plan_unified_r5.md` |
| kickoff | `review/ops_signoff/M2_kickoff_2026-10-26.md` §3 序号 3 | 队列已宣布；本页 ≠ 完成 |
| P1（背景） | `Signoff-M2b.md` / `Accept-brush-box.md` · **实现+测试过线** | **非**本包证据；刷箱过线 **≠** 币种已关 |

---

## 1. 元信息

| 字段 | 值 |
|---|---|
| Accept ID | Accept-currency |
| 对应统一项 | **U5-M2-P2** |
| ops 口径源 | **OPS5-O3-B**（链 **OPS3-O3** / **OPS4-O5**） |
| 状态 | **壳就绪 · 待测** |
| 落盘时间 | **2026-10-26 14:31:45 EDT**（America/New_York, UTC-4） |
| 实现锚点 | branch `u5-m2-p2-currency-accept` · 实现 `062681b87d393e49b860c951890508b7dd6ff011` · PR https://github.com/huangyuehui1998-dev/fba-smart-tool/pull/31 · 夹具 `backend/tests/fixtures/synthetic/currency/rows.json`（≠币种已关 ≠Publish） |
| 失败回打 | **code**（实现）/ **test**（夹具+断言）/ **ops**（对照与文档三行） |
| ≠ Publish | **确认** |
| 挡宣称 | **「币种已关」** — 本壳未全绿前禁称 |

---

## 2. 继承口径摘要（不重开产品争论）

摘自 OPS3-O3 / 统一稿既有定论（本壳只挂载，不改口径）：

1. **目标站 = 美国站**；非美国站行 → **skipped**（「非目标站点」），有汇率也**不**写入美国站申报价。  
2. **仅美国站行**再处理币种：USD 直用；非 USD → ÷fx；缺汇率 → **409** `FX_RATE_REQUIRED`。  
3. **币种为空** → 该行 skipped（HTTP 200 带明细），**不得**默认 USD；整文件 422 仅限缺必要列/无法解析。  
4. **采购/产品成本默认 CNY**；零售/申报价默认 **USD**；写入申报前须换算。  
5. **手工价保留**规则按 OPS3-O3 / U2-P1-01（与 MCP/xlsx 同口径对照表一行）。  
6. 仓库 pytest 用**合成夹具**；真实领星导出仅 box `requires_realdata`，**不入库**。

---

## 3. Accept 条件表（壳 · 全部待测）

| # | 条件 | 口径 | 状态 |
|---|---|---|---|
| C1 | 合成夹具 ≥2 | 错误币种 skip；手工价保留（路径约定后填） | **待测** |
| C2 | xlsx ↔ MCP/预览 **同口径** | 对照表至少 1 行（见 §4） | **待测**（对照位已占） |
| C3 | 非目标站 skip | CA 等不得写入美国站申报价 | **待测** |
| C4 | 美国站异常币种 | 有 fx → 换算写入；无 fx → 409 | **待测** |
| C5 | 币种为空 | skipped，不默认 USD | **待测** |
| C6 | 文档三行 checklist | `使用说明` / `OPEN_SOURCE`（或当时约定处）已合入 | **待测** |
| C7 | ops 短报告勾选 | 本页条件表全绿 + 挡宣称句仍在 | **待测** |

> 全表未绿前：**不得**称「币种已关 / 多站点规模化导入已放心」。

---

## 4. 真实 / 脱敏对照位（≥1 · OPS5-O3-B 强制）

> 下列为 **脱敏对照锚点**（来自既有交付/计划评审公开摘录与 Marco 确认的零售价口径；**不是**本轮过线证据）。  
> 过线时须用合成夹具或 box `requires_realdata` 复跑，并把命令/日志路径回填到 §5。  
> **禁止**把真实完整导出 xlsx 推进 public git。

### 对照位 C-REF-01（主 · 美国站 USD 零售）

| 项 | 值 |
|---|---|
| 来源类型 | **真实/脱敏**（领星在售导出 / MCP `erp_listing` 摘录；MSKU 已在公开 review 出现） |
| MSKU | `J-PETMAT-CAR-ZHENTOU-1PC-FBA` |
| 站点 / marketplace | 美国 · JoyBlooms-US |
| 币种 | **USD** |
| 价格 / listing | **39.99** |
| 期望写入 | 美国站申报零售路径可落 **39.99 USD**（非目标站行不得混入） |
| 旁证摘录 | `review/plan_review_code_r6.md`；`review/delivery_review_ops_r1.4.md`；Marco N-04 确认零售 USD |
| 本轮实测 | **待测**（壳占位） |

### 对照位 C-REF-02（辅 · 同站第二 SKU）

| 项 | 值 |
|---|---|
| MSKU | `J-PETMAT-CAR-ZHENTOU-TANZI-1PC-FBA` |
| 站点 | 美国 |
| 币种 / 价格 | **USD / 49.99** |
| 期望 | 与 C-REF-01 同口径写入 **49.99 USD** |
| 本轮实测 | **待测** |

### 对照位 C-REF-03（辅 · 非目标站 skip）

| 项 | 值 |
|---|---|
| MSKU | 同上 ZHENTOU 族（加拿大 JoyBlooms-CA 摘录） |
| 站点 / 币种 / 价 | 加拿大 · **CAD** · **65.11** |
| 期望 | **skipped**（「非目标站点」）；**不得**换算写入美国站申报价 |
| 本轮实测 | **待测** |

---

## 5. 证据位（占位 · 待回填）

| 证据 | 占位 | 责任方 |
|---|---|---|
| 合成夹具路径 | `backend/tests/fixtures/synthetic/currency/rows.json`（TEST_*；39.99 USD / 65.11 CAD） | **code** / **test** |
| xlsx↔MCP 同口径一行 | 以 §4 C-REF-01 为锚；实测命令/日志 `_待填_` | **test** |
| 非目标站 skip 日志 | `_待填_` | **test** |
| 美国站缺汇率 409 | `_待填_` | **test** |
| 币种为空 skipped | `_待填_` | **test** |
| 文档三行 checklist 路径 | `docs/使用说明.md`「零售价币种（美国站申报）」；`docs/OPEN_SOURCE.md`「申报币种（美国站）」 | **code** / **ops** |
| 实现 tip / PR | `062681b87d393e49b860c951890508b7dd6ff011` · https://github.com/huangyuehui1998-dev/fba-smart-tool/pull/31 | **code** |
| 挡宣称句出现位置 | 本页标题 / §6 签字区 / 未来短报告 | ops |

---

## 6. 挡宣称句（强制）

**明示不得**声称（未全绿前）：

- 「币种已关」
- 「多站点规模化导入已放心 / 本项完成」
- 以本 Accept 为 **Publish** 许可
- 「M2 首包已全部完成」（五包未齐）

本句与 `M2_kickoff_2026-10-26.md` §3/§4 及 OPS5-O3 一致。壳落盘 **本身** 不解除上述禁语。

---

## 7. 签字位（待填 · 当前禁止签「通过 / 币种已关」）

| 项 | 值 |
|---|---|
| 角色 | ops |
| **当前结论** | **壳就绪 · 待测** |
| 过线后结论 | _（待填：实现+测试过线 / 失败+回打对象）_ |
| 时间（壳） | **2026-10-26 14:31:45 EDT** |
| 时间（过线） | _待填_ |
| 封面链 OPS3-O3 / OPS4-O5 | **已链** |
| 脱敏对照 ≥1 | **已占**（C-REF-01～03） |
| **≠「币种已关」** | **确认** |
| **≠ Publish** | **确认** |
| 五包未齐 ≠ 首包全部完成 | **确认** |
