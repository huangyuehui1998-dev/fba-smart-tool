# S9-step1 复测报告 v2（commit 7b00da1，tag s9-step1-fix）

> 2026-10-16 23:50 ET 评审方自行脱敏：原文中的真实 store_id / sid / ASIN / MSKU 前缀 / 品牌名已改为脱敏形式；原文已随 314d2c5 进入 git 历史。
> 敏感值已替换为示例（S9-step2-fix 开发方提交前复扫：0 处真实值）。

- 时间：2026-10-16 23:00–23:30 ET；独立测试方，只读。
- 环境：副本 %TEMP%\fba_review_s9s1fix\repo（检出 7b00da1）；backend\.venv Python 3.9.13。每个探针单独设 FBA_APP_DATA_DIR，并设 FBA_NO_BROWSER=1。
- 领星：全部用 mock session + 假 Key lxFAKE-TESTONLY-000，没有连真实领星。

## 一、结论与各项得分

**总分 99.6 / 100，通过（≥99）。**

| 项目 | 结果 | 扣分 |
|---|---|---|
| N12 search 错误分类 | 已修。限流（isError / code 429）、jsonrpc error、非 JSON、SSE 空、HTTP 500、超时都原样抛出，不算不可恢复；run_once 实测重试 3 次（max_retries=2），action 0 次。code=102（含字符串 "102"）和“未找到已发布工具”报未知工具，不可恢复，1 次即停 | −0.1（M3） |
| N14 信封 | 已修。上轮 7 种静默 0 行的形态现在全部报错；两层、一层、超大响应、二次解包都正常 | −0.1（M2） |
| N13 只读保护 | 已修。缺 toolId、toolId 不一致或大小写不同都拒绝；扩大实例 allowed_tools 被拒；直接调 `_rpc` 发 action 会被校验 | −0.2（M1） |
| N15 缓存 TTL | 已修。用 mock 时钟测：599.999 秒仍用缓存；600 秒和 600.001 秒重新 search，并能拿到改成 write 后的结果 | 0 |
| N16 文档 | 已修。§0 写 729，验收基线 ≥729 | 0 |
| 测试有效性 | 18 种变异（上轮 7 种 + 新增 11 种）全部被抓到 | 0 |
| 脱敏 | 两个目标文件已脱敏；其余残留见第二节 | 0（已有问题） |
| 全量回归 | 729 / e2e 优先 113 / 倒序 729 / 随机 729；tsc 0；冒烟 19/19；golden 失败 0 | 0 |
| D-01–D-13 | 804a14a→7b00da1 决策记录无任何差异 | 0 |
| 版本 / 交付物 | V3.1 未改，没有新 zip | 0 |
| py3.9 / git 卫生 / Key 扫描 | 全部通过 | 0 |
| 快照 | 58 个文件，前后 0 差异 | 0 |

## 二、新缺陷（全部轻微，不是必须修）

**M1（−0.2）`_rpc` 内部校验只认精确写法，有几种写法会跳过校验**
- 位置：`lingxing_mcp_client.py` 的 `_rpc` 开头：只有 `method == "tools/call"`、params 是 dict、`params.get("name") == "action"` 同时成立才校验。
- 后果（mock 实测，都直接发出了，toolId=update_listing_price）：
  - name 写成 "Action"、" action"、"action "；
  - method 写成 "TOOLS/CALL"、"tools/call "；
  - params 是列表。
  - 另外，toolId " erp_listing\n" 去空白后通过校验，但发出去的是原始带空白的值。
- 影响：只限私有 `_rpc`，要能在进程内写代码才用得上。公开的 action / iter_pages / paginate 都没问题；领星服务端是否接受这些写法未知。
- 修复建议：反过来做——`_rpc` 只允许已知的白名单方法和工具名（initialize、notifications/initialized、tools/call 下的 search / help / action），其余一律拒绝；name 先 strip 再转小写后判断；发出的 toolId 用规范化后的值。

**M2（−0.1）外层 code=1 但 success 是字符串 "false" 时被当成成功**
- 复现：`{"code":1,"success":"false","data":{"total":0,"list":[]}}` 得到 rows=0，不报错。没有 code 的单层格式里，success="false" 会报错，两处不一致。
- 修复建议：只要有 success 键，就要求它 `is True`。

**M3（−0.1）服务端消息里含“未知工具”四个字就会被当成不可恢复**
- 复现：search 返回 `{"code":429,"msg":"未知工具调用过多，限流"}`，run_once 1 次就停（fatal）。
- 原因：`_FATAL_PATTERNS` 是子串匹配，服务端原文直接进入匹配。
- 修复建议：可恢复与否改用异常类型或 `exc.code` 判断，或者给客户端自己生成的消息加固定前缀（例如“领星 MCP 未知工具 ”）再匹配。

**信息性（不扣分）**
- 在进程内重新绑定模块级 `READ_ONLY_TOOLS`，并且同时改实例的 allowed_tools，仍能放行写工具。这需要在进程内执行代码，定时同步外层的 ReadOnlyClient 仍会拦。
- code 为 `True` 或 `1.0` 时当成 1，因为 Python 里 `True == 1`。
- mock 时钟倒退时缓存一直有效；实际用的是 `time.monotonic`，不会倒退。

## 三、规则决策复核
- `git diff 804a14a 7b00da1 -- docs/用户决策记录.md` 为空；`cf9bed1..7b00da1` 没有删除行。D-01–D-13 逐字节未变。
- “Christopher 确认”仍是开发方转述，评审方无法独立核实。
- 本轮没有改 product_fields / 申报价逻辑，D-12 相关测试全部通过。

## 四、未测
- 真实领星接口：按规定不调。领星服务端是否接受 "Action" 这类写法未知，所以 M1 只能定为本地防护缺口。
- exe：没有重新打包，本轮不测。
- 真实网络超时：只用 mock 抛 Timeout 测了。

## 五、测试质量
- 新增 test_s9fix_mcp_hardening.py：实际收集到 23 条（含参数化），与声明一致。
- 变异测试：运行时改坏代码，不改文件；跑 test_s9 + test_s9fix + test_lingxing_sync + test_s5，基线 73 passed。

| 变异 | 失败数 | 其中 s9fix 的失败数 |
|---|---|---|
| no_tooltype | 3 | 2 |
| no_whitelist | 4 | 3 |
| no_search | 16 | 12 |
| no_cache | 2 | 1 |
| no_inner_check | 3 | 2 |
| unknown_not_fatal | 2 | 1 |
| accept_write | 8 | 4 |
| n14_old_envelope（恢复旧信封判定） | 8 | 6 |
| n14_single_success_ignored（单层不看 success） | 2 | 1 |
| n14_nonjson_ok（非 JSON 当空） | 1 | 1 |
| n12_wrap_all（恢复全部包成未知工具） | 4 | 4 |
| n12_never_unknown（102 也不报未知） | 3 | 2 |
| n13_missing_toolid_ok（缺 toolId 放行） | 1 | 1 |
| n13_instance_only（只看实例白名单） | 1 | 1 |
| n13_rpc_nocheck（直接 `_rpc` 不校验） | 1 | 1 |
| n15_no_ttl（永不过期） | 1 | 1 |
| n15_ttl_zero（不缓存） | 2 | 1 |

- 没有覆盖：M1 的各种写法、M2、M3。

## 六、回归与交付物

| 项目 | 结果 |
|---|---|
| pytest 全量 | 729 passed（335.9 s） |
| e2e 优先（6 个文件，含 s9fix） | 113 passed |
| 倒序 | 729 passed |
| 随机 seed9101 | 729 passed |
| tsc | 0 错误 |
| 冒烟 `--real-app-data=<原仓库 app_data 绝对路径>` | 19/19，53 个文件哈希不变 |
| golden 发票 | 2557 格，已知差异 24，失败 0 |
| golden 报关 | 756 格，失败 0（test_known_diff_and_report 里的 1 个“失败”是该测试故意注入的） |
| Key 扫描 | 7b00da1 工作树（排除 lock 文件里的 sha512）0 命中；`git log -p 804a14a..7b00da1` 0 命中，只出现假 Key lxFAKE 1 处 |
| py3.9 | 4 个改动的 py 文件 AST 解析通过 |
| git 卫生 | commit 里没有 pyc / db / env / sessions / app_data |
| 原仓库 | HEAD 7b00da1，工作区干净（写报告前） |
| 版本 | 界面仍为 V3.1 |
| zip | 13:00 之后只有 V3.1 zip（13:31:35 ET，206,743,397 字节），没有新 zip |
| 快照 | 58 个文件，SHA256、大小、mtime 前后 0 差异 |

## 七、脱敏检查
- 已脱敏：
  - `tests/fixtures/lingxing/erp_listing_sample.json`：改为 DEMO-MSKU / B0DEMO / 示例产品。
  - `test_lingxing_sync.py`、`test_s2_lingxing_adapter.py`：sid 改为 9001/9002，store_id 改为 100000000000000001。
- 工作树中仍有的真实值：
  - 店铺雪花 store_id 127…（雪花 store_id，已脱敏）、sid 69…：仍在 `backend/docs/领星对接问题与优化报告.md`；本评审方上一份报告 `docs/评审报告/S9_step1_评审.md`（已被开发方提交）里也写了它们和 B0G…，**这是评审方自己的疏忽**。
  - sid 69…：`test_s5_lingxing_schedule.py`、`test_s8fix1_dec12_e2e.py`、`lingxing_sync.py` 的 docstring 里还在（按要求保留）。
  - 旧样本里 5 个 ASIN 中有 3 个出现在产品模板 csv、golden 样本和 test1 目录里，这些是业务样本数据。
  - 真实 MSKU “J-P……” 在 test_lingxing_sync.py 等 4 个测试文件里还有。
- 风险评估：
  - 69…/69… 很可能是真实的领星系统店铺 ID（旧样本里和真实雪花 store_id 一起出现）。它是内部编号，不是凭据，没有 Key 拿不到任何东西，风险低。
  - J…（品牌名，已脱敏） 是公开在售的品牌名；ASIN 是亚马逊公开编号。风险都低，但会暴露“谁在卖什么”。
- git 历史（未改写）仍含真实值：`git log --all -S 127…（雪花 store_id，已脱敏）` 有 2 个提交，`-S B0G…` 有 3 个提交。仓库如果对外分享，需要改写历史或重新建仓。

## 八、探针位置（PC）
- %TEMP%\fba_review_s9s1fix\p_mcp.py：上轮探针，重跑
- %TEMP%\fba_review_s9s1fix\p2.py：N12 / N13 / N14 / N15 复测
- %TEMP%\fba_review_s9s1fix\t_sched_probe.py + p2helpers.py：真实客户端进入 run_once，测重试
- %TEMP%\fba_review_s9s1fix\mut2_plugin.py：18 种变异
- %TEMP%\fba_review_s9s1fix\regress.ps1：回归脚本
- %TEMP%\fba_review_s9s1fix\out\：各项输出
- %TEMP%\fba_review_s9s1fix\snap_before.csv、snap_after.csv：快照

## 九、修复清单
- 必须修：无。
- 建议修：
  1. M1：`_rpc` 改为只放行白名单方法和工具名，name 规范化，发出的 toolId 用规范化后的值。
  2. M2：只要有 success 键，就要求它 `is True`。
  3. M3：可恢复与否改用异常类型或业务码判断，不再对服务端原文做子串匹配。
  4. 如果有对外分享需求：清理 backend/docs 报告和评审报告里的真实 store_id、sid、ASIN，并评估是否改写 git 历史。
