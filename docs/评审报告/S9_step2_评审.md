# S9-step2 评审报告（commit 314d2c5，tag s9-step2）

- 时间：2026-10-16 23:50 – 10-17 00:15 ET；独立测试方，只读。
- 环境：副本 %TEMP%\fba_review_s9s2\repo；backend\.venv Python 3.9.13。每个探针单独设 FBA_APP_DATA_DIR，并设 FBA_NO_BROWSER=1。
- 领星：全部用 mock + 假 Key lxFAKE-TESTONLY-000，没有连真实领星。
- 本报告不含任何真实 store_id / sid / ASIN / MSKU / 店铺名 / 品名；位置一律写成“文件:行号 + 类型”。

## 一、结论与各项得分

**总分 98.3 / 100，不通过（及格线 ≥99）。** 主要扣分是 A1：只有常规价变化时，不会写入常规价，预览显示的申报价和报关包实际申报价不一致。

| 项目 | 结果 | 扣分 |
|---|---|---|
| M1 `_rpc` 规范化 | 已修。大小写、首尾空白（含 NBSP、全角空格）规范化后再校验；全角、零宽、土耳其 İ、开尔文 K 等 unicode 写法一律拒绝；tools/list、resources/read 等未知 method 拒绝；params / arguments / action params 不是 dict 时拒绝；发出的 name 和 toolId 都用整理后的值 | 0 |
| M2 success 严格为 True | 已修。外层和内层 success 为 "false"、"true"、1、0、None 都报错，只有 True 放行 | 0 |
| M3 按异常类型判断不可恢复 | 已修主体：Unknown / ReadOnly / Auth 都是 fatal，429 文字里含“未知工具”或“Key无效”时仍会重试。但 Key 无效的另外两种返回形态现在会被重试 | −0.1（M4） |
| S9-A 价格预览 | 15 个场景中 13 个与报关包一致，预览只读，没用 list_price；S13 不一致，S12 显示自相矛盾，异常输入有崩溃 | −1.0（A1）、−0.2（A2）、−0.1（A3） |
| S9-A 前端 | 代码评审有若干可用性问题；截图未测 | −0.1（U1） |
| 脱敏 | 主要文件已脱敏；交接文档里的脱敏说明本身写了真实 sid，另有 2 处遗漏 | −0.2（D1） |
| 变异测试 | 35 种全部被抓到（含修正后重跑的 1 种） | 0 |
| 全量回归 | 765 / e2e 优先 140 / 倒序 765 / 随机 765；tsc 0；冒烟 19/19；golden 失败 0 | 0 |
| D-01–D-13 | 逐字节未变 | 0 |
| 版本 / zip | 仍是 V3.1；没有新 zip | 0 |
| py3.9 / Key 扫描 / git 卫生 / 文档测试数 | 全部通过 | 0 |
| 快照 | 58 个文件，前后 0 差异 | 0 |

## 二、新缺陷

**A1（−1.0，中等，必须修）只有 regular_price 变化时，常规价不会写入；预览显示的申报价与报关包实际申报价不一致**

- 位置：
  - `lingxing_preview.build_listing_preview`：regular_price 不在 CONFIRM_FIELDS 里，所以售价没变时该 SKU 被分进“unchanged”组，不生成可勾选字段。
  - `apply_lingxing_field_patch`（L425–426）：regular_price 只有在 listing_price 一起写入时才会写。
  - `preview_price_info`：按“remote 的常规价已写入”来模拟。
- 后果：
  - 例：本地 15.99/15.99，领星本次返回售价 15.99、常规价 19.99（按 D-12 是 20% 促销，应按 19.99 申报）。
  - 预览显示“申报将用：19.99（来源：常规价）”。确认写入后，库里常规价仍是 15.99，报关包按 15.99 申报。
  - 定时同步（自动写入）也一样：先 15.99/15.99 再 15.99/19.99，或先只有售价再出现常规价，库里常规价都不会更新，报关包都按 15.99 申报。
  - 也就是说，在这种情形下 D-12 的促销判断不生效，会少报申报价。
- 复现：探针 `t_s9a_probe.py` 场景 S13，以及 `t_a1_sched.py`。
- 根因早于 S9（S8 实现 D-12 时就存在），但 S9-A 的预览把错误的数字直接展示给了用户。
- 修复建议：
  - regular_price 应作为价格字段参与 changed 判断，变化时随价格字段一起默认勾选（定时同步自动写入）；或者 regular_price 变化时总是跟着写。
  - 预览按“实际会勾选的字段”计算 price_info。
  - 补 e2e 测试：只变常规价时，预览价 == 报关包单价。

**A2（−0.2）常规价残留时预览显示自相矛盾**
- 场景 S12：库里有旧常规价 19.99，本次领星没给 regular_price。
- 预览显示“常规价 regular_price：（空）”，后面却是“申报将用：19.99（来源：常规价）”。
- 原因：`price_info.regular_price` 只取 remote 的值，而申报计算用的是本地残留的常规价。
- 另外：领星不再返回常规价时，本地旧常规价永远不会清除（已有行为）。19.99 这个旧值会一直参与 D-12 判断，由用户决定是否给常规价设有效期。
- 建议：显示实际参与计算的常规价，并标出“本地旧值”。

**A3（−0.1）异常输入**
- `preview_price_info` 里，listing_price 为 "1,299.00" 或 "abc" 时抛 ValueError（`resolve_declared_price` 里直接 float），会导致整个预览接口 500。
- listing_price 为 0 时显示“售价（空） · 申报将用 0.00（来源：售价）”。
- listing_price 为 NaN 时，declared_price 也是 NaN（JSON 序列化会失败）。
- 正常同步路径会经过 `_price_or_none` 转成数字，实际很难走到这里。
- 建议：先用 `_num_or_none` 整理后的值组装 sim；declared 不是有限正数时返回 null。

**U1（−0.1）前端可用性（代码评审）**
- 价格没有币种（`listing_price_currency` 没放进 price_info）。多站点 SKU 会看不出单位。
- 文案“申报将用”没有说明这是“确认写入后”的结果。取消勾选售价后，这一行不会随之变化（S15：显示来源“近 90 天非促销价”，实际确认后来源是“售价”）。
- “常规价 regular_price”中英混写，普通用户看不懂 regular_price。
- 能区分“按常规价 / 按售价 / 近 90 天非促销价”，这一点合格。但促销时没有直接说“促销中”，用户要自己比两个数。
- 布局：与现有预览一致（xs 字号、muted 色，放在 SKU 行按钮下方）。每个 SKU 多一行，在 max-h-80 的滚动区里，SKU 多时更挤。“unchanged”组默认折叠，A1 的错误数字就藏在折叠组里，更难发现。
- 空值显示“（空）”，与字段行的写法一致，合格。

**M4（−0.1）Key 无效的另两种返回形态改为可重试**
- 信封 `{code:401, msg:"MCP Key无效或已失效…"}` 和 JSON-RPC error 里写 Key 无效，现在都按普通错误处理，定时同步会重试 3 次才失败。
- 旧版的子串匹配能识别这两种情况。2026-10-16 实测的真实形态是 isError，已正确识别；这两种属于覆盖面变窄，后果只是多试几次。
- 建议：信封业务码 401/403 也归为 Auth。

**D1（−0.2）脱敏遗漏**
- `HANDOFF_交接清单.md:242、244` 和 `交接文档_给新Bot.md:237、239`：脱敏说明本身用“真实值 → 9001/9002”的写法，写出了 2 个真实 sid。
- `docs/评审报告/S2_测试评审_v2.md:45`：1 处真实品名（local_name）。
- `docs/评审报告/S9_step1_评审_v2.md:113、114、119、120`：含真实 store_id、sid、ASIN、品牌。这是**评审方自己写的报告**，开发方原样提交进了 314d2c5。
  - 本轮已按要求先备份（`%TEMP%\fba_review_s9s2\S9_step1_评审_v2.md.bak`），再在原仓库工作树里脱敏。
  - 注意：该文件已被跟踪，所以原仓库现在显示 `M docs/评审报告/S9_step1_评审_v2.md`；原文仍在 314d2c5 的历史里。

**信息性（不扣分）**
- action 的 arguments 里另带 `ToolId` / `toolid` 等键，或在 params 里嵌套 toolId / name，会原样发出；校验的是规范化后的 `toolId`。服务端是否认这些键未知。
- 在进程内重新绑定模块级 READ_ONLY_TOOLS，仍能放行写工具，与上轮相同。
- 带业务码 0 的“未找到已发布工具”现在可重试（按“有业务码只认 102”的设计）。

## 三、规则决策复核
- `git diff 7b00da1 314d2c5 -- docs/用户决策记录.md` 为空；`cf9bed1..314d2c5` 没有删除行。D-01–D-13 逐字节未变。
- S9-A 复用了 `resolve_declared_price` / `_informative_regular`，没有用 list_price / history_price。S11 场景带 list_price=38.97 也没被用到，符合 D-13。
- D-12 场景逐项核对（预览价 / 报关包单价 / 期望值，三者一致的都标 ✓）：

| 场景 | 预览价 | 报关包单价 | 期望 | 结果 |
|---|---|---|---|---|
| 新品 15.99/19.99 | 19.99 常规价 | 19.99 | 19.99 | ✓ |
| 18.98/20 | 20 | 20 | 20 | ✓ |
| 恰好 5%：19/20 | 19 售价 | 19 | 19 | ✓ |
| 常规价=售价 15.99 | 15.99 | 15.99 | 15.99 | ✓ |
| 历史 16 → 12/12 | 16 近 90 天 | 16 | 16 | ✓ |
| 历史 16 → 12/12.5 | 12 | 12 | 12 | ✓ |
| 历史 25 → 20/20.5 | 20 | 20 | 20 | ✓ |
| 历史 25 → 18/20 | 20 常规价 | 20 | 20 | ✓ |
| 历史 16 → 15.5 | 15.5 | 15.5 | 15.5 | ✓ |
| 历史过期 → 12 | 12 | 12 | 12 | ✓ |
| 带 list_price | 15.99 | 15.99 | 15.99 | ✓ |
| 售价手填锁定 30 → 领星 20 | 30 | 30 | — | 一致 |
| 取消勾选售价 | 16（近 90 天） | 16（售价） | — | 数值一致，来源不同 |
| 常规价残留（A2） | 19.99 | 19.99 | — | 数值一致，显示矛盾 |
| **只变常规价（A1）** | **19.99** | **15.99** | — | **✗** |

- 预览只读：每个场景都调用 `serialize_preview` 两次、`latest_preview_payload` 一次。前后 DB 文件 SHA256 不变，product_master 的价格和历史价列不变，不更新历史非促销价。

## 四、S9-B 方案意见（不打分）

1. **字段含义与生命周期**
   - 建议字段：`last_nonpromo_origin` = `self_first` / `confirmed` / `unknown`。“是否首次自记”的布尔值不够表达“迁移前的旧数据”。
   - 置位：`_track_nonpromo` 在 `ref is None` 分支（没有有效常规价、也没有 90 天内历史价）写入时，置为 `self_first`。
   - 清除（改为 `confirmed`）：
     - 之后某次在 `ref` 不为 None 的情况下再次记下非促销价；
     - 出现有效常规价；
     - 用户手动确认正常价。
   - 90 天过期后再次自记，重新置为 `self_first`。
2. **旧数据迁移**：现有记录无法区分来源，建议统一标为 `unknown`，不要标成 `self_first`，否则所有老 SKU 一次性全部提示。
   - 可以选做：用 `lingxing_sync_run` / 价格历史估算。如果只有 1 条样本且时间等于首次同步时间，就标 `self_first`。
3. **与 D-12 / D-13 的一致性**
   - 提示只能是提示，不能改变申报价（D-12 的取值顺序不变）。
   - 提示文案和兜底都不能建议用 list_price / history_price（D-13）。
4. **触发条件与误报、漏报**
   - 触发条件建议：申报来源是“售价”或“近 90 天非促销价”，且该记录是 `self_first`，且没有有效常规价。
   - 误报：大多数新 SKU 首次同步时本来就是正常价，所以每个新 SKU 都会提示，直到第二次确认，噪声大。可以加“只在首次记录后 N 天内提示”，或只在报关导出时提示一次。
   - 漏报：如果促销一直持续超过 90 天，或首次同步后价格没再变动，就一直识别不了。
   - 另外 A1 未修之前，常规价也进不来，`confirmed` 的路径会少一条。
5. **更简单的替代做法**
   - 用样本数和跨度判断：例如“近 90 天非促销价样本 < 2 次，或跨度 < 7 天”就提示。需要记次数，或从同步记录里数。
   - 比较 `last_nonpromo_at` 与该 SKU 首次领星同步时间：两者相同即为“首次自记”。如果已有首次同步时间列，就不用新增字段。
   - 最简做法：只在 S9-A 预览里对新 SKU 显示“首次同步，没有历史正常价可对照”，不改表结构。
6. **需要用户决定**
   - 是否要这个提示，在哪里显示（预览 / 报关导出 / 两处）；
   - 多少样本或多少天算“有历史”；
   - 旧数据标为 unknown 时是否也提示；
   - 用户能否手动确认正常价来消除提示；
   - 常规价残留是否设有效期（见 A2）。

## 五、未测
- **UI 截图未测。** PC 上有 ms-playwright 的 chromium 浏览器文件，但 frontend 的 node_modules 和 venv 里都没有 playwright 包。副本里的 backend\dist 是 10-16 12:18 的旧构建，不含本次前端改动；要截图必须先 `vite build`。而 node_modules 是联接到原仓库的，构建或 dev server 可能往原仓库 node_modules 写缓存（.vite / .nitro 等），违反“不改原仓库”，所以没有构建。前端只做了代码评审，并跑了 tsc。
- 真实领星接口：按规定不调。
- exe：没有重新打包，不测。

## 六、测试质量
- test_s9step2_protocol_m123.py：实际 27 条（100−73），与声明一致。test_s9step2_preview_price.py：9 条。765 = 729 + 27 + 9。
- 协议变异：运行时改坏代码，不改文件；跑 5 个文件，基线 100 passed。下表中失败数都 ≥1，即全部被抓到。

| 变异 | 失败数 |
|---|---|
| 上轮 17 种（不含已失效的 unknown_not_fatal） | 全部 ≥1 |
| m1_no_lower | 7 |
| m1_raw_toolid | 1 |
| m1_any_method | 3 |
| m1_params_any | 5 |
| m2_false_only | 6 |
| m3_auth_not_fatal | 4 |
| m3_unknown_not_fatal | 4 |
| m3_readonly_not_fatal | 2 |
| m3_iserror_not_auth | 2 |
| m3_auth_substring（Key 文字子串匹配误杀限流） | 1 |
| m3_text_fatal（恢复旧子串判定） | 3 |
| n13_rpc_nocheck | 第一版插件按旧调用栈写，没生效（100 passed，不算漏抓）；按新调用栈修正后 6 failed |

- S9-A 变异（只跑 preview 测试，基线 9 passed）：

| 变异 | 失败数 |
|---|---|
| ignore_history | 2 |
| no_regular | 3 |
| declare_listing | 3 |
| use_list_price | 1 |
| no_price_info | 8 |

- 缺口：没有“只变常规价”（A1）、常规价残留（A2）、字符串价格（A3）的测试；预览价与报关包单价没有 e2e 对照。

## 七、脱敏检查（只写位置与类型）
- 方法：从 804a14a 的旧样本和旧测试取真实值清单（只在内存里），用 `git grep` 扫 314d2c5 工作树。清单规模：MSKU 6、品名 6、FNSKU 3、ASIN 5、sid/store_id 3、店铺名 2、品牌 1。
- 属于声明保留的三类：
  - golden 样本（`backend/tests/golden/**`）：ASIN 8 处、FNSKU 10、MSKU 24、品牌 131。
  - 业务配置（`backend/config/*.default.json`）：品牌 8 处。
  - 产品目录 / 模板（`backend/templates/产品信息表.csv`、`亚马逊FBA表*.csv`、`product_catalog.py`）：ASIN 3、FNSKU 3、MSKU 6、品名 3、品牌 37。
- 交接文档已列明、但不属于上面三类的：
  - `test1/*.csv`：5 个文件，含 ASIN / FNSKU / MSKU / 品牌；
  - `backend/_sta_compare.json`、`packaging/Step5报关资料_架构与工作流.txt:336`、`docs/方案/*.md`、`代码评审日志.md`：品牌；
  - `HANDOFF_交接清单.md:270` / `交接文档_给新Bot.md:986`：FNSKU（金样快照说明）；
  - `test_product_master_parser.py:116`：MSKU（读模板的测试）。
- 未列明：D1 里的 4 个位置。
- 店铺名：工作树 0 处。
- DemoBrand 的影响：DemoBrand 只出现在测试、脚本和文档里；产品代码、golden、业务配置、模板都没改。golden 发票 2557 格、报关 756 格失败 0，冒烟 19/19，不影响产品输出。
- git 历史没有改写，仍含真实值；只有仓库对外共享时才需要处理，由用户决定。

## 八、回归与交付物

| 项目 | 结果 |
|---|---|
| pytest 全量 | 765 passed（321 s） |
| e2e 在前（7 个文件） | 140 passed |
| 倒序 | 765 passed |
| 随机 seed9101 | 765 passed |
| tsc | 0 错误 |
| 冒烟 `--real-app-data=<原仓库 app_data 绝对路径>` | 19/19，53 个文件哈希不变 |
| golden 发票 | 2557 格，已知差异 24，失败 0 |
| golden 报关 | 756 格，失败 0 |
| py3.9 | 本次改动的 22 个 py 文件 AST 解析通过 |
| Key 扫描 | 工作树（排除 lock 文件）0 命中；`git log -p 7b00da1..314d2c5` 0 命中，只出现假 Key lxFAKE 3 处 |
| git 卫生 | commit 里没有 pyc / db / env / sessions / app_data / zip |
| 文档测试数 | 交接文档 §0、验收基线都是 765 / ≥765；HANDOFF 写明 27 条 |
| 版本 | 界面仍为 V3.1 |
| zip | 13:00 之后只有 V3.1 zip（13:31:35 ET，206,743,397 字节） |
| 快照 | 58 个文件，前后 0 差异 |
| 原仓库 | HEAD 314d2c5；工作树多出 `M docs/评审报告/S9_step1_评审_v2.md`（本轮脱敏）和本报告（未跟踪） |

## 九、探针位置（PC：%TEMP%\fba_review_s9s2\）
- p_mcp.py、p3.py：协议探针（M1 / M2 / M3 / N12–N15）
- t_sched_probe.py + p2helpers.py：真实客户端进入 run_once，测重试 / 不可恢复
- t_s9a_probe.py：S9-A 15 个场景 + 12 种异常输入
- t_a1_sched.py：A1 定时同步复现
- mut3_plugin.py、mut_rpc_plugin.py、muta_plugin.py、mut.ps1：变异
- desens_scan.py：脱敏扫描，只输出位置和类型
- regress.ps1：回归脚本
- out\：各项输出
- snap_before.csv、snap_after.csv：快照
- S9_step1_评审_v2.md.bak：脱敏前备份

## 十、修复清单
- **必须修**：
  1. A1：regular_price 单独变化时要能写入（手动预览可勾选、定时同步自动写入）；price_info 按实际会写入的字段计算；补 e2e 测试“预览价 == 报关包单价”，包含只变常规价的场景。
- 建议修：
  1. A2：显示实际参与计算的常规价；决定残留常规价的有效期。
  2. A3：异常价格容错。
  3. U1：加币种、写明“确认后”、随勾选状态更新、文案不用英文字段名。
  4. M4：信封业务码 401/403 也归为 Auth。
  5. D1：交接文档 4 处去掉真实 sid；S2_测试评审_v2.md:45 去掉真实品名；把本轮脱敏后的 S9_step1_评审_v2.md 一并提交。
