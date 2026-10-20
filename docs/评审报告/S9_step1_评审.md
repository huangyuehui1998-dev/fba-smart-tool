# S9-step1 评审报告（commit 804a14a，tag s9-step1）

> 注：本报告中的敏感值（store_id、sid、真实 ASIN）已替换为示例（S9-step2 脱敏，2026-10-16）；其余内容为测试 BOT 原文。

- 评审时间：2026-10-16 约 22:30–22:50 ET；独立测试方，只读。
- 环境：仓库副本 %TEMP%\fba_review_s9s1\repo（检出 804a14a）；backend\.venv Python 3.9.13；每个探针单独设 FBA_APP_DATA_DIR，并设 FBA_NO_BROWSER=1。
- 领星：全部用 mock session，假 Key lxFAKE-TESTONLY-000。没有连真实领星，也没有用聊天里出现过的任何 Key。

## 一、结论与各项得分

**总分 99.0 / 100，通过（及格线 ≥99，刚好压线）。**

| 项目 | 结果 | 扣分 |
|---|---|---|
| 决策记录 D-01–D-12 未改，D-13 内容 | s8-docs 与 cf9bed1 之间该文件无差异；cf9bed1→804a14a 只在文件末尾新增 9 行（D-13），D-01–D-12 逐字节不变。`s8-final^{commit}` = cf9bed1099d5…，与声明一致 | 0 |
| 只读保护（toolType / 白名单 / search 先行） | 主路径全部 fail-closed，未发现能经公开 API 发出 write 的绕过 | −0.1（N13） |
| search 失败分类 | 限流、非 JSON、SSE 空、jsonrpc error 都被标成“未知工具”，进入定时同步的不可恢复错误，不会重试 | −0.3（N12） |
| 解包 / 信封 | 两层、一层、6.9 MB 都正确；但若干失败形态静默返回 0 行，被当成成功 | −0.4（N14） |
| 缓存 | 同一客户端内 search 结果一直沿用，不会刷新 | −0.1（N15） |
| fixture 脱敏 / Key 扫描 | 新增的 3 个 mcp_* fixture 干净；仓库和 log -p 无 Key 形态命中 | 0 |
| 测试有效性 | 7 种变异全部被抓到 | 0 |
| 全量回归 | 706/706；e2e 优先、倒序、随机种子都全过；tsc 0；冒烟 19/19；golden 失败 0 | 0 |
| 文档 | 交接文档 §0 写 706，一致；第 74、280 行的验收基线仍写 ≥695 | −0.1（N16） |
| 版本 / 交付物 | 版本号仍 V3.1；没有新 zip；V3.1 zip 仍是 13:31:35 ET 那份 | 0 |
| py3.9 / git 卫生 | 4 个改动的 py 文件按 3.9 语法 AST 解析通过；原仓库工作区干净 | 0 |
| 真实数据快照 | 58 个文件，前后 0 差异 | 0 |

## 二、新缺陷

**N12（−0.3）search 的暂时性错误被误标为“未知工具”，并被当作不可恢复错误**
- 位置：`lingxing_mcp_client.py` 的 `search()` except 分支：只有消息含“Key无效 / HTTP / 网络错误”时才原样抛出，其余一律包成“领星 MCP 未知工具 {id}：…”。`lingxing_scheduler._FATAL_PATTERNS` 新增了“未知工具”。
- 后果：领星限流（isError“限流，请稍后”）、jsonrpc error“rate limited”、响应不是 JSON、SSE 为空，都会被报成“未知工具”。定时同步因此直接按不可恢复错误停止，不重试，用户看到的原因也是错的。
- 复现：mock search 返回 isError=True、文本“限流，请稍后”，结果为 `领星 MCP 未知工具 erp_listing：限流，请稍后`，action 发出 0 次。
- 修复建议：只有 search 明确返回 code=102 / success=false 且信息是“未找到已发布工具”时，才报“未知工具”；其余错误原样抛出，或另设可重试的类别。

**N14（−0.4）部分失败信封静默返回 0 行，被当成成功**
- 位置：`unwrap_lingxing_payload`。外层只有存在 success 键时才检查；内层只在 success=False，或 code 为 0 且 data 为空时才判失败。
- 后果：以下形态都返回 rows=0 total=0，不报错：外层 code=0 或 code=102 且没有 success 键；内层 code=500 且没有 data；内层 code=0 但带 data；content 文本不是 JSON；data 是字符串。同步结果显示“成功 0 条”（实测不会删除数据），状态有误导性。这与交接文档说的“内层失败也报错”不完全一致。
- 修复建议：外层或内层 code 不等于 1（或不在明确的成功码集合里）就报错；content 文本不是 JSON 时报错，不要返回空列表。

**N13（−0.1，信息性）只读保护的边角**
- search 结果里缺 toolId 时直接放行（只校验了 toolType）。
- 进程内把实例的 `allowed_tools` 重新赋值，或在建客户端前重新绑定模块的 `READ_ONLY_TOOLS`，都能放行写工具。这需要能在进程内执行代码，定时同步外层的 ReadOnlyClient 仍会拦截。
- 私有方法 `_rpc` 可以直接发 action，不经校验；`help` 不校验（它是只读元工具）。
- 建议：缺 toolId 时拒绝；`_authorize` 直接对照模块级常量，不用可改写的实例属性。

**N15（−0.1）search 缓存不过期**
- 同一个客户端里，服务端已把工具改成 write，后续 action 仍按缓存的 read 放行（实测发出 2 次）。由于每次同步新建一个客户端，影响有限。建议给缓存加 TTL，或按每次同步清空。

**N16（−0.1）文档验收基线过时**
- `交接文档_给新Bot.md` 第 74、280 行仍写“≥695 passed”，§0 已是 706。

**已有问题（S2 起就存在，不扣分）**
- `tests/fixtures/lingxing/erp_listing_sample.json` 含真实 ASIN（如 B0DEMO0002）、MSKU、品名。
- `test_lingxing_sync.py` 含 store_id 100000000000000001、sid 9001/9002。
- 建议后续脱敏。

## 三、规则决策复核
- D-01–D-12：`git diff s8-docs cf9bed1` 和 `git diff cf9bed1 804a14a` 都显示该段没有任何改动；804a14a 只追加了 D-13。
- D-13 内容：① 不用 list_price / history_price 作为正常价；② D-12 两条参数（regular_price 高于售价才算有信息；售价 ≥ max×0.95 才更新历史值）由“Bot 选定”改为“已确认”；③ S7、S8 完成，s8-final=cf9bed1（tag 已核实）。D-13 与 D-12 原文没有矛盾，D-12 的取值顺序明确保留。
- **无法独立核实**：“Christopher 已确认（经主对话转达）”是开发方的转述。评审方看不到用户原话，只能核实记录与代码、tag 一致。
- 代码复核：s9 没有改 product_fields；回归中 D-12 的各条测试全部通过。

## 四、未测
- 真实领星接口：按规定不调用，所以“6 个工具 toolType=read、名字不变”只能信开发方的实测，fixture 结构与其描述一致。
- 交接文档说开发方在盒子上用真实 Key 调过 help/search 和 1 次 read action。评审方无法核实 Key 没有落盘，只在仓库和 git 历史里查了，无命中。
- exe 重新启动：本轮没有重新打包，未测（zip 未变）。
- 真实网络超时下的计时行为：只用 mock 抛 Timeout 测了。

## 五、测试质量
- test_s9_mcp_protocol.py 共 11 条，都有真实断言。
- 变异测试：运行时改坏代码，不改文件；跑 test_s9 + test_lingxing_sync + test_s5，基线 50 passed。

| 变异 | 结果 |
|---|---|
| no_tooltype（不检查 toolType） | 1 failed |
| no_whitelist（不检查白名单） | 1 failed |
| no_search（action 前不 search） | 4 failed |
| no_cache（不缓存） | 1 failed |
| no_inner_check（不检查内层失败） | 1 failed |
| unknown_not_fatal（“未知工具”不算不可恢复） | 1 failed |
| accept_write（放行 write） | 4 failed |

- 不足：没有覆盖 N12、N14 的形态，也没有覆盖缺 toolId、Unicode 同形字、缓存过期这些情况。

## 六、回归与交付物

| 项目 | 结果 |
|---|---|
| pytest 全量 | 706 passed（78.7 s） |
| e2e 优先（5 个文件） | 90 passed |
| 全量倒序 | 706 passed |
| 随机 seed9101 | 706 passed |
| tsc --noEmit | 0 错误 |
| 冒烟 `--real-app-data=<原仓库 app_data 绝对路径>` | 19/19，53 个文件哈希不变 |
| golden 发票 | 225+2332=2557 格，已知差异 24，失败 0 |
| golden 报关 | 756 格，失败 0（test_known_diff_and_report 里的 1 个“失败”是该测试故意注入的） |
| 版本 | V3.1 未改 |
| zip | dist 下 V3.1 zip 仍是 13:31:35 ET、206,743,397 字节；13:00 之后没有新 zip |
| py3.9 | AST 解析通过 |
| 原仓库 | HEAD 804a14a，工作区干净（写报告前） |
| 快照 | app_data + backend\fba_master.db + config\sessions 共 58 个文件，SHA256、大小、mtime 前后 0 差异 |

## 七、探针位置（PC）
- %TEMP%\fba_review_s9s1\p_mcp.py：绕过 + 解析探针，输出 out\p_mcp.out
- %TEMP%\fba_review_s9s1\mut_plugin.py：变异插件，用 env MUT 选变异
- %TEMP%\fba_review_s9s1\shuffle_plugin.py、golden_tally.py、regress.ps1：回归用
- %TEMP%\fba_review_s9s1\out\：各项输出
- %TEMP%\fba_review_s9s1\snap_before.csv、snap_after.csv：快照

## 八、修复清单
- 必须修：无（本轮通过）。
- 强烈建议（S9 后续步骤前修）：
  1. N14：信封 code≠1 或 content 非 JSON 时报错；补测试。
  2. N12：只有 102 / “未找到已发布工具”才算未知工具；限流等改为可重试；补测试。
- 建议：
  1. N13：缺 toolId 时拒绝；白名单直接对照模块常量。
  2. N15：缓存按同步周期清空或加 TTL。
  3. N16：把文档验收基线更新为 706。
  4. 旧 fixture 脱敏。
