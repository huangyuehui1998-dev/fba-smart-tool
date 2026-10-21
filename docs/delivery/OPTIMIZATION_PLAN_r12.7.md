# FBA Smart Tool V3.3 优化方案 r12.7（交付关 r1 返工；交云代理执行）

> 产品版本 V3.3。文中 `delivery_review_*`、`plan_review_*`、`cross_score_*`、`review/work` 以及 `/workspace/...` 路径是 box 上的复核材料，不在本仓库。

- 版本：r12.7，2026-10-20（美东时间）。起草：代码 bot。
- 基线：`OPTIMIZATION_PLAN_r12.6.md`（保留不动）← r12.5 ← r12.4 ← r12.3 ← r12.2 ← r12.1 ← r12.0。r12.7 = r12.6 + 下面“r12.7 修订记录”。
- 依据的评审：
  - 交付关 r1：`delivery_review_code_r1.md`（72）、`delivery_review_test_r1.md`（45）、`delivery_review_ops_r1.md`（44）
  - 方案关 r12：`plan_review_code_r12.md`（97.6，7 项 −2.4）、`plan_review_test_r12.md`（99.1，4 项 −0.9）、`plan_review_ops_r12.md`（94.75，P1–P4 −5.25）
- 备份：`OPTIMIZATION_PLAN_r11.md`（sha256 前缀 a074a329b1e2305f）、`OPTIMIZATION_PLAN_r12.0.md`、`OPTIMIZATION_PLAN_r12.1.md`（181787b9f21323bf）。
- 交付评审最新版：`delivery_review_code_r1.5.md`（代码 bot，**53.5**）、`delivery_review_test_r1.5.md`（测试，**41**；第 16 条 −0.5：pr10 `volume_weight.py` 入库时舍入，318.90 不受影响）、`delivery_review_ops_r1.5.md`（运营，**41**；D12 −1 → −1.5）。
- **r11 仍然有效**：r11 的业务口径、§9 箱规库设计、§11 定论继续适用。r12.1 与 r11 冲突时以 r12.1 为准。
- **交付标准（Marco 2026-10-20 定）**：三个 bot 都用真实实例独立测试，再交叉评分，**独立分和交叉分全部到 100** 才算交付。合并由 Marco 批准。
- **新增状态标记**：凡是出处未在 box 上打开原文核实，或原文已逐字核实但适用读法未经亚马逊或主管部门确认的条目，一律标 `pending_verification`（后者在注中写明“读法待确认”）；冒烟和 pytest 不以它为断言依据，界面如实显示“待核实”。

## r12.7 修订记录（运营方案评审 r12.5 → r12.7 修改）

运营 r12.5 方案分 **99.5**（`plan_review_ops_r12.5.md`，P1 −0.25、P2 −0.15、P3 −0.1）。

| 来源 | 问题 | r12.7 修改 | 位置 |
|---|---|---|---|
| 运营 P1 | 用例尺寸段标错：34×20×10 in、22kg 应为 Small Bulky；40×20×10 in 体积重 57.6 lb，应为 Extra-large | 所有箱规用例补全三边尺寸，用 `work/tier_r12_7.py` 按官方尺寸段表（GC3Q44PBK8BXQW3Z Size 列；Small standard 计单件重，其余取 max(单件重, L×W×H/139)）逐条复算，11/11 一致（`work/tier_r12_7.out`）：40×20×10 改为 40×15×8 in（体积重 34.5 lb → Large Bulky）；34×20×10 改标 Small Bulky；Small Bulky 35 in 用例取 35×15×10 in（原先想用的 35×20×10 体积重 50.4 lb，会变成 Extra-large）。红绿判定一条不变 | R12-17 |
| 运营 P2 | R12-07 第 5 步句尾残留半个粗体和拼接的半句 | 改为“也不能把尺寸取整成 45/45/41。” | R12-07 |
| 运营 P3 | 运营 N1 用例写“原样纳入”，实际是转述 | 改为逐字引用运营 r1.4 第 10 节第 4 条，另把实现时补全的尺寸单独列出 | R12-17 |
| 运营（文首） | 版本和基线行 | 改为 r12.7，基线 r12.6 | 文首 |
| 父级 | 文首“交付评审最新版”过期 | 改为代码 r1.5（53.5）、测试 r1.5（41）、运营 r1.5（41） | 文首 |
| 父级 | `pending_verification` 只覆盖“出处未打开”，不覆盖“原文已核实、读法未确认” | 定义扩大为两种情形，后者在注中写“读法待确认” | 文首第 12 行 |
| 父级 | 运营 N1 引文里“24 kg Extra-large、40 in 商品装 42 in 箱、25 kg → 不阻断”与 31kg 用例依赖同一读法 | 加注：与第 494 行最后一条 31kg 用例同属一类，标 `pending_verification`（读法待确认），不作为冒烟断言依据 | R12-17 运营 N1 引文下的注 |
| 代码 bot（cross_score_code_r12.7.md −0.3） | 第 501 行的注所指不明、多一个空格；规则 (c) 没写明 (a)+(c) 叠加是本工具读法；r12.7 修订记录漏了第 12、501 行 | 注里写明 31kg 那条用例并去掉空格；规则 (c) 末尾加读法说明并标 `pending_verification`；补上本表这三行。红绿判定都不变 | R12-17、修订记录 |

## r12.6 修订记录（代码 bot 交叉评分 r12.5 → r12.6 修改）

| 来源 | 问题 | r12.6 修改 | 位置 |
|---|---|---|---|
| 代码 bot（cross_score_code_r12.5.md −0.2） | 修订记录第 35、36、65 行的旧判定未标作废 | 三行末尾加“（r12.5 作废，以 R12-17 为准）” | 修订记录 |
| 代码 bot（−0.1） | 重量用例缺 65 lb / 50 lb 精确边界 | 新增 29.48kg（64.99 lb）通过 + Team Lift、29.49kg（65.01 lb）红色、恰好 50.00 lb 不贴 Team Lift | R12-17 重量用例 |
| 父级 | Extra-large 68.3 lb 商品、最长边 50 in、52×30×20 in 箱 70.5 lb 判通过的依据 | 保留“通过”，加注“本工具读法，原文未写第 160 行与第 169 行如何叠加”，标 `pending_verification` | R12-17 重量用例 |

## r12.5 修订记录（r12.4 方案关 → r12.5 修改）

r12.4 方案分：运营 **99.5**（`plan_review_ops_r12.4.md`）；测试 **99.4**（测试对代码 r1.3 互评 98.5）。

| 来源 | 问题 | r12.5 修改 | 位置 |
|---|---|---|---|
| 运营 P1 | 用例“Large Bulky 商品 24kg ≤50 lb”自相矛盾：24kg = 52.9 lb > 50 lb | 商品改为 22kg（48.5 lb）；另加“1 件 Extra-large 商品 24kg（52.9 lb）→ 条件 a 放宽”。R12-17 全部 kg↔lb 换算已按 1 kg = 2.20462 lb 复核（见下） | R12-17 |
| 运营 P2 | §6 缺运营 D14，D2 分值过期 | §6 加“运营 D14 −5 → R12-13”；D2 改为 −5.5 | §6 |
| 运营（不扣分） | 修订记录第 21 行与第 9 行不一致 | 两处统一为代码 r1.4（53.5）/ 测试 r1.4（41.5）/ 运营 r1.4（41.5） | 文首、r12.4 修订记录 |
| 测试 r12.4（方案 99.4） | 单件超大箱 50–65 lb 的读法：测试 bot 认为 50–65 lb 只在箱子不超 36×25×25 时放宽，超长箱须 ≤50 lb | **采纳测试读法**（原文第 130、158–163、169 行逐字引在 R12-17）：长度例外只在 ≤50 lb 时适用；50–65 lb 只在 36×25×25 以内放宽 + Team Lift；“40 in 商品 42 in 箱 25/28kg”改为红色；删除“请向亚马逊核对”提示；新增“单件超大、箱在 36×25×25 内、50–65 lb → 通过 + Team Lift”；运营 P1 的条件 (a) 商品本身 >50 lb 照旧放宽；Small Bulky 23kg 用例按字面改判为通过 + Team Lift | R12-17、§5 |
| 测试 r12.4 | 第 ~425 行残留 r12.3 理由“只提示、不硬拦” | 删除，换成 r12.5 的逐字原文和判定 | R12-17 |
| 运营 r1.4 第 10 节 | 运营同意测试读法、作废对旧条件 b 的认可；D2 的 45.0 是 `to_cm()` 存储时舍入（`volume_weight.py:27-42`），不只是显示 | 判定段写明运营同意；原样纳入运营 5 个 N1 用例；R12-07 第 5 条写明 `to_cm()` 1 位存储舍入并改用不舍入换算；文首引用改为测试 r1.4（41.5）、运营 r1.4（41.5） | R12-17、R12-07、文首 |

- **换算复核**（kg × 2.20462，保留 1 位）：22.5→49.6；22.6→49.8；22.68→50.0；22.7→50.0（>50.00 lb，22.68kg = 50.00 lb）；8.5→18.7；22→48.5；23→50.7；24→52.9；25→55.1；25.5→56.2；28→61.7；29.48→65.0；31→68.3；32→70.5；30→66.1；45→99.2；46→101.4；18.2→40.1。全部与方案文字一致。

## r12.4 修订记录（r12.3 方案关 → r12.4 修改）

r12.3 方案分：运营 **99.75**（`plan_review_ops_r12.3.md`，仅 N1 −0.25）。

| 来源 | 问题 | r12.4 修改 | 位置 |
|---|---|---|---|
| 运营 N1 | 单件箱 >50 lb 的放宽比官方宽：用例“1 件 Small Bulky 23kg → 不阻断”没有满足任一前提 | 放宽条件写死为二选一：**(a) 商品本身 >50 lb**（200141510 Box weight 段：“unless they contain one single item that exceeds 50.00 lb”），或 **(b) 单件超大商品最长边 >36 in 且箱重 ≤65 lb**（同页单件超大一段）。都不满足 → 50 lb 红色阻断。(b) 下箱重 >65 lb 且商品本身 ≤50 lb → 红色。用例全部按此改写 | R12-17、§5 （r12.5 作废，以 R12-17 为准） |
| 代码 bot（本轮） | 第 160 行“Boxes may exceed 50 lb … must still adhere to 36×25×25”与尺寸例外（第 159 行）冲突：长于 36 in 的箱子超过 50 lb 时，页面两句话无法同时满足 | 单件超大箱、商品最长边 >36 in、箱重 >50 lb → 除 Team Lift 外再加**黄色、不阻断**“请向亚马逊核对：官方页面对超长且超过 50 lb 的箱子表述不一致”。用例：1 件 Large Bulky（40×20×10 in）装 42×22×12 in 箱、25kg（55.1 lb）→ 尺寸通过 + 黄色“请向亚马逊核对” + Team Lift | R12-17 （r12.5 作废，以 R12-17 为准） |
| 运营 r12.3 | 第 9 行仍引用运营 r1.1 | 改为最新文件，与文首一致：代码 r1.4（53.5）、测试 r1.4（41.5）、运营 r1.4（41.5）（r12.5 同步更新） | 文首 |
| 代码 bot（本轮补丁） | 文首引用、配置费逐档验收、D14 安全细节 | 文首改为代码 r1.3（52.5）/ 测试 r1.3（31）/ 运营 r1.3（41.5）；R12-17 加 12 个不符值的逐档验收表和重量基准用例（对照存档页第 129–135、210–227 行，Large Bulky 无截断）；R12-13 加 D14 六项逐项回归（CORS 带凭证、明文 cookie、GET 登录、localStorage Key、拒绝启动保留、脱敏 8/11 泄露） | 文首、R12-13、R12-17 |

## r12.3 修订记录（r12.2 方案关 → r12.3 修改）

r12.2 方案分：运营 **99.75**（`plan_review_ops_r12.2.md`，仅 P1 −0.25）；代码、测试的 r12.2 评审意见如下表。

| 来源 | 问题 | r12.3 修改 | 位置 |
|---|---|---|---|
| 代码 r12.2 | STA 标签行用固定行号描述，不是规则 | 改为规则：表头在第 5 行，SKU 明细区第 6 行到第 5+N 行（N = SKU 数），第 6+N 行空行，**第 N+7 到 N+11 行是箱信息标签行**。已在真实文件上核对：第 13 批 N=2 → **9–13**；第 14 批 N=6 → **13–17**；第 15 批 N=1 → 8–12（运营也在第 13 批核实为 9–13，与 Marco 实际上传成功的 STA 结构一致） | R12-18、§5 |
| 代码 r12.2 | download 接口没有说用同一个文件名校验 | `GET /api/history/files/download` 调用同一个 `safe_history_filename()`（与 `safe_history_path` 同一套拒绝规则 + `resolve()` 在目录内），不合法返回 400 `INVALID_FILE_NAME`；新增 4 条用例 | R12-12 |
| 测试 r12.2 | §5 写“单件超大箱 ≤65 lb”，与 R12-17“>65 lb 只提示不阻断”矛盾 | §5 改成与 R12-17 一致的表述 | §5 |
| 测试 r12.2 + 运营 P1 | 缺 200141510 的尺寸例外；“36.5×20×20 → 红色”会误拦单件 40 in 的 Large Bulky | 恢复尺寸例外（原文已在保存的页面全文核对，见 R12-17）：**箱内只有 1 件且该件最长边 >36 in** 时，箱子可以超过 36×25×25；新增通过用例和反例 | R12-17 |
| 运营 r12.2 | 反例“1 件 Large standard 23kg”不可能出现（Large standard 上限 20 lb） | 换成可出现的反例：1 件 Large standard 8.5kg（18.7 lb）装在 3 件一箱共 25.5kg 的多件箱 → 红色；以及 1 件 Small Bulky 23kg（50.7 lb）单件箱 → 不阻断 + Team Lift | R12-17 |
| 运营 r12.2 | 运营收回 r12.1 的 Q3 扣分 | 记录：Q3（尺寸段最大尺寸出处）运营已在 r12.2 评审中承认 GC3Q44PBK8BXQW3Z 的 Size 列有 “Max … inches”，上轮 −0.25 不应扣 | 本表 |
| 运营 r1.2 | 根因锚点 | R12-09 写明 `customs_package.py:202` 在 box_tares 长度不符时回退硬编码 0.2；R12-07 写明 −1271 来自 `measurement_adapters.py:88` 只认“实重 / 实重(kg) / 重量”，不认“单箱实重” | R12-07、R12-09 |

## r12.2 修订记录（r12.1 剩余扣分 → r12.2 修改）

| 来源 | 问题 | r12.2 修改 | 位置 |
|---|---|---|---|
| 代码评审 | R12-12 用 `{task_id:path}` 会吞掉 history 下已有的子路由 | 不改路由模板（保持 `{task_id}`），改为在中间件里对**原始路径** `/api/tasks/history/` 前缀做解码校验，非法一律 400；新增子路由回归用例 | R12-12 |
| 代码评审 | “单件超大箱”定义不清 | 定义为：箱内**恰好 1 件**，且该件尺寸段为 Small/Large Bulky 或 Extra-large；新增反例：2 件超大商品 28kg 一箱 → 按多件箱在 50 lb 红色阻断 | R12-17 |
| 测试评审 | 重复箱 NX8HH U000017 的处理没写清 | 写明：重复箱号的**两条记录都剔除**（156 − 2 = 154），不保留任一条 | R12-07 |
| 测试评审 | 口径 B 的适用范围 | 写明：口径 B **只在九方第 13 批上验证过**（5/5 票）；其他货代、其他批次未验证 | R12-07、§8 |
| 测试评审 | 第 15 批 101 vs 100 | 列为待定项（6JJ6A、S97BA 账单 101，Σ 计费重 100），不断言 | R12-07、§8 |
| 测试评审 | r12.1 写“运营已自行将 D2 改为 −6”与运营 r1 文件不符 | 更正：运营 `delivery_review_ops_r1.md` 仍是 −8；运营在随后的 `delivery_review_ops_r1.1.md`（46 分）才改为 −6。§6 改写为两份文件分别的值 | §6 |
| 运营 Q1 | R12-07 文字是 max(实重, 体积重2位) 不再舍入，`rounding_r12_1.py` 第 30 行是对 max 再舍入，两者不一致 | 统一为**对 max 结果再 ROUND_HALF_UP 到 2 位**（与脚本第 30 行一致）。复算：两种写法在第 13 批上结果完全相同（实重占优 0/160 箱），都复现 5 张账单；选“再舍入”是因为九方“计费重”列本身是 2 位。新增实重占优用例 | R12-07 |
| 运营 Q2 | 65 lb 红色阻断与 >100 lb Mechanical Lift 冲突 | 按 200141510：多件箱 >50 lb 仍红色阻断；单件超大箱 >50 lb 黄色 + Team Lift，>65 lb 黄色“超过 65 lb，请核对”（不阻断），>100 lb 黄色 + Mechanical Lift。单件重物不硬拦 | R12-17 （r12.5 作废，以 R12-17 为准） |
| 运营 Q3 | 尺寸段边界缺官方出处 | 四个尺寸段的最大尺寸取自已核实的 GC3Q44PBK8BXQW3Z 费率表；尺寸段帮助页 201105770《Product size tiers》在 box 上用无头 Chrome 两次都没渲染出正文，其中的重量上限、长+围长 130 in、Extra-large 分档标 `pending_verification` | R12-17、§5 |
| 运营 D13（交付复验） | STA 预检把第 13–17 行箱信息标签行当作 SKU 行，20 条假“必填项为空”；`sta_precheck.py` 第 68–90 行只跳过 SKU 为空的行 | R12-18 改写：识别 SKU 明细区边界，标签行不检查；新增第 13 批 0 误报验收 | R12-18 |

## r12.1 修订记录（r12 方案关扣分 → r12.1 修改）

| 来源 | 扣分 | 分值 | r12.1 修改 | 位置 |
|---|---|---|---|---|
| 代码 1 | 第 15 批表尾写成每文件 3 行 | −0.5 | 改为**非空表尾每文件 2 行、共 10 行**；空行忽略、不计数 | R12-07 |
| 代码 2 | 第 15 批两个目录同名文件，未定导入哪份、是否幂等 | −0.5 | 冒烟写死 `货代计费重确认文件/`（与 `货代入库数据/` 已 cmp 逐字节相同）；同运单号再导入覆盖；新增验收“导入两次仍 5 条 bill / 30 行” | R12-07、R12-03 |
| 代码 3 | 外箱号描述成 `1.0`；QGXTA 含 12 | −0.3 | 改为“外箱号为纯数字（float 或 str）一律 invalid_id”；锚点注明 QGXTA 含 `12` | R12-07 |
| 代码 4 | 退税折合率出处偏弱 | −0.4 | 已核实：12 个月不得变更的出处是《增值税法实施条例》（国务院令第 826 号）第十七条；退税管理文件（国家税务总局公告 2026 年第 5 号）的具体条款标 `pending_verification` | R12-05、§5 |
| 代码 5 | 计征汇率规则未进验收；《关税法》条款号未核实 | −0.3 | fx_rate 增加 `source=CFETS 中间价（上月第三个星期三，非交易日顺延）`；月份按报关申报日确定；新增 10-31 / 11-01 两条用例；《关税法》不写条款号，标 `pending_verification` | R12-05、§5 |
| 代码 6 | 2024-30 引用不全；缺 <1kg 两位小数 | −0.2 | §5 写成“2019 年第 18 号公告第二十五、二十六条，经 2024 年第 30 号修改”；R12-09 新增 0.456 → 0.46 | R12-09、§5 |
| 代码 7 | R12-01 未逐项列出 realdata 3 个失败 | −0.2 | 列出 3 个用例全名和根因 | R12-01 |
| 测试 a | R12-07 未规定舍入顺序，锚点自相矛盾 | −0.4 | 以货代账单为证据写死**口径 B**（逐箱计费重 2 位），全部锚点只按 B 重算；A/C/D/拼接/取整/170 行列为反例 | R12-07、X1 |
| 测试 b | §8.1 / X1 根因叙述不准确 | −0.2 | 更正：318.90 = 口径 B 的箱级差（申报体积重 13.8375 每箱舍入成 13.84）；表尾 10 行只解释运营那次 170 行 / −1271 的运行 | X1、§8 |
| 测试 c | E2E-06 条数与 0.5kg 阈值无定值或出处 | −0.2 | E2E-06 改成可机械判定的规则（按类型计数）；0.5kg 由运营用真实数据验证 0 误报，定为内部可配置值 | R12-10、R12-16 |
| 测试 d | R12-12 未写编码方式和 404 是否通过 | −0.1 | 全部变体按 %2F 编码发送；**只有 400 算通过**，任何 404/500/200 都判失败 | R12-12 |
| 运营 P1 | 320.01 / 323.85 拼接两种口径；318.90 定性错误；未写舍入规则 | −2.5 | 同测试 a、b；新锚点 **+320.20（154 行）/ +324.04（156 行）** | R12-07、X1、§8 |
| 运营 P2 | 箱规政策与官方不符；出处页错（G201081250） | −1.5 | 多件箱 36×25×25 in、≤50 lb；单件超大箱 50–65 lb；Team Lift >50、Mechanical Lift >100；珠宝手表 ≤40 lb；出处改为 200141510（2026-10-20 核实） | R12-17、§5 |
| 运营 P3 | 配置费数值未按官方 2026 表更正；缺计费重量规则 | −1 | 按 GC3Q44PBK8BXQW3Z（2026-01-15 起）更正 Small standard 2 档、Large Bulky Minimal 5 档 + Partial 5 档；按尺寸段选重量基准 | R12-17 |
| 运营 P4 | 2.3 ≤ 2.3 边界未规定 Decimal 与容差；阈值未标内部可配置 | −0.25 | Decimal 比较 + 0.01 容差 + 边界用例；阈值 `suspect_unit_weight_kg` 默认 0.5，内部、可配置 | R12-16 |

交叉分里提到的问题（代码给测试 −1.0、运营 −1.2；测试给代码 93、运营 94；运营给代码 79、测试 88）属于对交付评审 r1 报告的评价，不改方案条目；其中“318.90 的定性”已按上表在 X1 更正。
## 0. 执行约束（云代理，延续 r11 第 0 章，新增 4 条；r12.1 不变）
1. 只开 PR，不合并，不推 main。真实数据只放在 box 上，不进仓库。领星接口一律用 mock。
2. **新增：只在一条线性集成分支 `plan/integration-r12` 上验收**（见第 2 章）。r11 的 10 个分支只作历史参考，不再单独验收。
3. **新增：每个 r12 条目都写成单独的提交**（提交信息以 `R12-xx` 开头），全部叠在 `plan/integration-r12` 上，方便逐条审查。
4. **新增：真实数据冒烟脚本**（第 3 章）放在仓库 `backend/tests/smoke/`。脚本只读 `FBA_REALDATA_DIR`（box 默认 `/workspace/fba_tool/realdata`），没有这个目录时 skip。**期望值在运行时从真实文件独立复算**；方案里写的数字只作锚点，再断言一次相等。
5. **新增：生产代码里不能写测试断言**（例如 `declared_value.py:195-197` 用字符串查找 "1021.76"），一律移到 pytest。
6. 模型：Grok 4.7，xhigh，关闭 fast（Marco 2026-10-20 定，所有 bot、所有任务都只用这一种）。

## 1. 三方分歧的核实结论（代码 bot 用 box 真实数据复跑，2026-10-20 17:40–18:10 美东时间）

| # | 分歧 | 各方说法 | 复跑命令 / 证据 | 结论 |
|---|---|---|---|---|
| X1 | 箱规计费重总差 | r12 写 +320.01；测试、运营复算指出它拼接了两种舍入口径 | `cd /workspace/fba_tool && venv/bin/python review/work/rounding_r12_1.py`（r12.1 新增，只读 realdata 原始 CSV 和九方 xlsx）；运营独立脚本 `/workspace/ops_run/r12_carton_indep.py` | **r12.1 定为口径 B，总差 +320.20（154 行）/ +324.04（156 行）**。判据是货代自己的账单：每票 Σ逐箱计费重向上取到 0.5kg 必须等于“入库计费重”。只有逐箱计费重保留 2 位（B、D）时 5 票全部吻合；全精度（A、C）时 PU1DA Σ=332.5033125 → 333 ≠ 账单 332.5。**更正 r12**：318.90 不是“三个缺陷叠加”，而正是口径 B 的箱级差（申报体积重 45.01×45.01×41.00/6000 = 13.8375，每箱舍入为 13.84，系统性地 +0.0025/箱）；表尾 10 行被算进去只解释运营那次 170 行 / 实重差 −1271 的运行，与 318.90 无关。320.01 = A 的 318.71 + B 的 1.30，是拼接值，作废 |
| X2 | 干净导出 pytest 是 0 failed 还是 2 failed | 测试、PR 自报：0F（git worktree）；代码：2F（git archive） | `delivery_r1/<分支>/pytest_clean.log`；`wt_p0` 里 `test_no_real_data_in_repo.py` 4/4 通过 | **两边都属实，差别在环境**：扫描测试依赖 `.git`（`tests/realdata_scan.py:41`）。r11 §8 门禁用的是 `git archive`，所以按门禁算 **2F**。R12-01 修复 |
| X3 | PR-5 是否写申报快照 | 运营：`snapshot_from_validation` 没有调用方，快照 0 行；代码：有调用 | `verify_r12.py validate`：在 p5 上调用 `/api/shipments/validate`，快照写入 **160 行**；`routers/shipment.py:125` 只在非流式接口里调用 | **运营结论在 UI 路径上成立**：前端走 `/api/shipments/validate/stream`，这个接口不写快照，所以 UI 全流程下快照为 0 行。R12-08：两个接口都要写 |
| X4 | 默认净重口径 | 测试：新装环境默认 minus_per_box，算出 257.6；运营：mode 是 tare_from_carton，但皮重取了 0.2 | p2d 新库 `GET /api/master-data/customs-rule-profile` → `net_weight_mode: tare_from_carton`；`customs_package.py` 里 8 处调用 `compute_net_weight(gross, boxes)`，都**不传 box_tares** | **运营的根因正确**：mode 对，但每箱皮重没有传入，于是回退到 0.2，得到 264 − 32×0.2 = 257.6。另外 `_net_weight_params()` 在字段为空时回落到 `"minus_per_box"`（`:184`），老库升级时也有风险。R12-09 两处都修 |
| X5 | p2b 路径穿越返回码 | 代码：被拦截（函数层 ValueError）；测试：拦住了，但 HTTP 500 | `verify_hist.py`：p2b 上 4 种写法的 POST 都是 **500**，没有文件写到外面；p5/p3（不含 p2b）上 `../../TEST_evil` 返回 **200**，并写出 `<AD>/TEST_evil.json` | **测试结论成立**。R12-12：统一返回 400 |
| X6 | 第 13 批箱唛识别 | 代码：p1b 的仓码 15/15 通过；测试、运营：p1b 报 160 条“箱唛未识别” | `verify_r12.py validate`：p1b 返回 ok=False，“箱唛未识别” 160 条；p5、p0 返回 ok=True，0 条 | **两边都对**。仓码函数通过了，但整条校验链路在 p1b 上回归。R12-10 |
| X7 | DOWD | 代码：p1b 上不再出现 DOWD；测试：p10 上 CL2=DOWD | p5 校验响应里 CL2=DOWD，响应全文 “DOWD” 出现 **242** 次；p1b 为 0 次 | 叠栈缺 p1b 造成的。R12-11 要求在集成分支上，响应全文 DOWD 出现 0 次 |
| X8 | `npm ci` 失败是谁引入的 | 代码、测试：p4/p5 引入；运营：main 上就已失败 | 对 `git archive origin/main frontend` 执行 `npm ci` → EUSAGE（Missing @emnapi/core@1.11.3） | **运营正确**：main 上就存在；p3 重新生成了 lock，所以通过；p4/p5 沿用了坏 lock。R12-02 |
| X9 | 删除不存在的任务 | 测试：p10 返回 200，p9 返回 404 | p2b、p5 返回 200；p3 返回 404 | 测试正确。R12-14 统一为 404 |
| X10 | 运营建议“箱体积密度 < 30 kg/m³ 时提示疑似单件重” | 运营 §4 第 9 条；运营 r12 评审 8-4 已收回 | 第 13 批：1.8kg ÷ (0.40×0.22×0.22 m³ = 0.01936) = **93 kg/m³** | **不采纳，三方一致**。R12-16 用“单个重量为空或 0，且单箱毛重 ≤ 装量 × 0.5kg + 皮重”（Decimal，0.01 容差），第 13 批命中（1.8 ≤ 2.3；2.3 ≤ 2.3） |

仍有分歧的点见第 8 章。

## 2. R12-00 集成分支（唯一验收对象）
- **分支名**：`plan/integration-r12`，从 `main@11c05d2` 开始，**线性**（不用 merge commit）。
- **重建顺序**：按 r11 §7，cherry-pick 或重放以下提交，在每一步上解决冲突：
  `9e7a2e6、14178f0 (PR-0) → ec0be02 (1a) → 1407d21 (1b) → e0f2a19 (2b) → de2c401 (2a) → 7c0e819 (2c) → 50f1d6a (2d) → 93bdfa4 (PR-4) → 0585761 (PR-3，去掉 fe2c1e3 这个 merge) → 6a91827 (PR-5，去掉 740e0a3 这个 merge)`。
  之后再叠 R12-01 … R12-21 的提交。
- **已知冲突（四方复核）**，要逐个说明怎么解决：
  - `test_acceptance_baseline.py`（1b/2b/2c）
  - `master-data-workspace.tsx`、`step1-workspace.tsx`（PR-3）
  - `session_store.py`、`master_db.py`、`customs_package.py`、`step4-workspace.tsx`、`boxing.py`、`package.json`、`package-lock.json`（PR-5 与 PR-3/2x）
  - 2c、PR-3 改过的 `legacy_streamlit/*` 在 PR-4 里整目录删除，**以删除为准**
- **验收**：
  1. `git log --merges main..plan/integration-r12` 输出为空；`git log --oneline` 能依次看到 r11 的 10 个 PR 主题和 R12-01…21。
  2. `repro_code_review.py`（box，带 realdata）：**0/12 REPRODUCED**。逐项结果都应为 NOT REPRODUCED：
     - R1：只出 kind=unit_weight_missing 提示，不给建议值
     - N-07：187.5
     - N-02：2.5 → 422
     - D-01：22.44
     - D-05：返回 400
     - R3：None
     - D-03a/b、D-04：有报错
     - R2 合成：CLT2
     - R2 真实：CL2 页面上的仓码统计里没有 DOWD
     - R4：已按产物屏蔽过期标记
  3. 第 3 章冒烟脚本全部通过；pytest（干净导出 / 带 realdata）、vitest、`npm ci`、build 全部为 0 失败（R12-01/02）。
  4. 每个 r12 条目的验收（第 4 章）都在这个分支上执行，并把命令输出写进 PR 描述。
  5. 只开一个 PR：`plan/integration-r12 → main`，**不合并**。r11 的 PR #1–#10 保持打开，在描述里注明“已并入 integration-r12，不单独验收”（由父级 bot 请 Marco 决定是否关闭）。

## 3. R12-03 box 真实数据冒烟脚本（新增）
- **文件**：`backend/tests/smoke/test_box_realdata_smoke.py`，标记 `@pytest.mark.realdata_smoke`。
- **入口**：`scripts/box_smoke.sh`，内容是：
  1. 按 r11 §8 重建 testrun（git archive；提交号写进 COMMIT.txt）
  2. `FBA_REALDATA_DIR=/workspace/fba_tool/realdata FBA_APP_DATA_DIR=$(mktemp -d) pytest -m realdata_smoke -q`
  3. 输出 `smoke_report.json`，内容为每项的实测值、期望值和是否通过
- **用法**：每次都用 `TestClient(main.app, raise_server_exceptions=False)` 走 HTTP 接口，不直接调内部函数（领星用真实导出 xlsx，不连 MCP）。**任何 5xx 都直接判失败**。
- **复算原则**：参考实现放在 `backend/tests/smoke/reference.py`，用 pandas、csv 直接读原始文件，独立于产品代码。产品接口的输出必须 == 参考值；参考值还要 == 方案锚点。三者不一致时，在报告里同时列出三个数。
- **覆盖范围**（每项对应第 4 章的验收编号）：
  1. S-01 第 13/14/15 批 Step1 → Step2 → Step3 预览/导出 → Step4 校验（流式和非流式两个接口都跑）（R12-10/11/14/16）
  2. S-02 九方 LCL 文件导入：第 13 批 5 个、第 15 批 5 个（只读 `货代计费重确认文件/`）→ 对比页；每批再重复导入一次验证幂等（R12-07/08）
  3. S-03 领星导出 xlsx 导入（新接口，以及旧接口改造后的路径）（R12-06）
  4. S-04 产品信息表导入 + 申报价报价 + Step5 预览/导出：第 13 批 CL2 三种口径（R12-04/05/09）
  5. S-05 历史任务路径穿越（R12-12）
  6. S-06 日志脱敏：用真实接口触发错误日志（R12-13）
  7. S-07 STA 预检：第 14 批（R12-18）

## 4. r12 条目与验收（期望值都来自 box 真实数据；复算命令附在后面）

### R12-01 测试基建在干净导出下全部通过（代码 D8；测试 −3、第 2 节；运营 0.5）
- **realdata 下的 3 个失败（出处 `delivery_r1/*/pytest_realdata.log`，r12.1 补全名和根因）**：
  1. `tests/test_no_real_data_in_repo.py::test_whitelist_templates_exist_and_text_scan_matches_baseline`：扫描调用 `git ls-files`，`git archive` 导出的树里没有 `.git`，命令失败。
  2. `tests/test_no_real_data_in_repo.py::test_new_shipment_id_in_backend_foo_txt_fails_scan`：同一根因（`git ls-files` 依赖 `.git`）。
  3. `tests/test_s4fix_invoice_export.py::test_test1_five_tickets_export_smoke`：断言 `assert 0 == 5`。根因：用例写死 `HERE.parent/"test1"`，干净导出里没有 test1/，也没有 skip。
- **改法**：
  - `tests/realdata_scan.py`：没有 `.git` 时（`git rev-parse` 失败）改用文件系统遍历；排除 `node_modules`、`dist`、`.venv`、`__pycache__`；扩展名规则与 git 模式相同。两种模式对同一棵树必须得到同一份文件清单（新增一致性用例，在 worktree 里跑）。修复失败 1、2。
  - `test_test1_five_tickets_export_smoke` 改用 `requires_realdata(<test1 目录>)`，路径从仓库根 `ROOT/"test1"` 计算。修复失败 3。
- **验收**：
  - `git archive plan/integration-r12` 干净导出：`pytest -q` **0 failed / 0 errors**；skipped 都带“需要 box realdata”。
  - 带 realdata 的 testrun（r11 §8）：**0 failed / 0 errors**；上面 3 个用例逐个 PASSED 或带原因 SKIPPED（第 3 个在没有 test1 时 SKIPPED，原因含“test1”）。

### R12-02 lock 文件重新生成（代码 D9；测试 −3；运营 D10；X8）
- **改法**：在集成分支上 `rm -rf node_modules && npm install`，提交新的 `package-lock.json`；`bun.lock` 已在 PR-4 删除。CI 和冒烟脚本都改用 `npm ci`。
- **验收**：干净导出后 `npm ci` 退出码为 0；`npx vitest run` 和 `npm run build` 退出码都为 0。vitest 用例数 ≥ 75 + R12 新增数（p3 实测 15 个文件 / 75 个用例），以实测为准写进 PR 描述。

### R12-04 缺价时返回 409，不允许申报 0（代码 D4；运营 D11）
- **改法**（`declared_value.py`）：
  1. 每一行先算出该行的单价来源，**算不出就整次报价返回 409**：`code=DECLARED_VALUE_MISSING`，`detail.missing=[{sku, basis, tried:[...]}]`，中文提示“以下 SKU 缺申报价：…，请在产品库补齐”。**任何口径都不能返回 0.00**。
  2. 回退链逐行判断（不再因为一行缺手填就整票改用历史价）：
     - retail：领星售价(USD) → 历史申报价(USD) → 产品成本(CNY) ÷ fx → 409
     - fob：手填 FOB（按 r11 换算方向表）→ 历史申报价（加“该值为零售价口径，非 FOB”提示）→ `purchase_price_cny × (1 + fob_domestic_cost_rate) ÷ fx`（`fob_domestic_cost_rate` 存在 customs_rule_profile，默认 0，界面注明是内部口径）→ 409
     - cost：`purchase_price_cny` → 409
  3. 每一行都返回 `price_source ∈ {lingxing, legacy, product_cost, manual_fob, purchase}`。提示文案按实际来源生成：只有来源是 legacy 时才出现“取自历史申报价”。
  4. `fx` 参数接受数字或对象；不合法时返回 422，不能是 500（运营 D11：现在传 7.2 返回 500，`declared_value.py:129`）。
  5. `to_dec(None)` 不能再在金额路径上被当成 0 使用：改用 `_num()`，遇到 None 抛 MissingPrice。
- **验收**（pytest 合成数据 + 冒烟 S-04 真实数据，fx = 7.2）：
  - 合成：cost 缺采购价 → 409；fob 三级都缺 → 409；retail 缺售价、历史价和产品成本 → 409；`fx: 7.2`（数字）→ 200；`fx: "abc"` → 422。
  - 合成：fob 两行，TEST_A 手填 30 USD、TEST_B 没有手填但有历史价 49.99 → 80×30 + 48×49.99 = **4799.52**；只有 TEST_B 带提示。
  - 合成：fob 没有手填也没有历史价，采购价 50 CNY，rate = 0 → 50 ÷ 7.2 = **6.94**；price_source=purchase。
  - 真实 CL2（第 13 批，80 + 48 件）：retail 5598.72、cost 7360.00 CNY → 1022.22（555.56 / 466.66，均价 7.99）、fob 回退 5598.72 并带提示——与 r11 相同，在集成分支上复验。
  - 反例：任何报价或导出接口的响应里，不应出现 `total_usd == 0` 且 HTTP 200 的情况（冒烟脚本对所有响应做全局断言）。

### R12-05 Step5 和报关导出真正使用报价引擎和汇率（代码 D2；运营 D5；测试 3.3）
- **改法**：
  1. `customs_package.build_customs_data`（以及按票装配和合并装配两条路径）的金额统一由 `quote_declared_value(lines, basis, fx_snapshot, month)` 计算。lines 的数据来源：任务快照里的件数 + 产品库（领星售价、历史价、产品成本 CNY、采购价 CNY、手填 FOB）。`hints["单个货值"]` 只作为“历史申报价”这一级的来源，不再直接成为单价。
  2. 新增 `GET/PUT/DELETE /api/fx-rates`（字段按 r11 §4 P1-16 的 fx_rate 表），以及 `POST /api/fx-rates/import`（CSV 导入）。Step5 显示当月汇率，并可以编辑。
  3. 预览和导出时，按**报关申报月份**取 `customs_monthly` 汇率；取不到 → 409 `FX_RATE_REQUIRED`，前端弹出 ErrorNotice，并给出“去录入汇率”按钮。retail 口径且全部为 USD 时可以不需要汇率（与 r11 相同）。
  4. 导出时把 5 个 fx 字段、`declared_value_basis`、`trade_term`、`retail_source`、`retail_synced_at`、逐行 `price_source` 写进任务快照；重新导出时用快照值（r11 §4 P1-16 原规则）。
  5. Step5 切换口径后立即重新预览；fob 回退时，在页面和导出的“备注”列都显示“该值为零售价口径，非 FOB（取自历史申报价）”。
  6. 出口退税折合率 `tax_fx_basis`：选定后 12 个月内修改要弹出 ConfirmDialog（r11 已定，交付时缺失，补上）。
- **验收**（冒烟 S-04：真实第 13 批 CL2 报关；产品库由真实产品信息表 + 两个 ZHENTOU 构成，ZHENTOU 售价来自领星导入 39.99 / 49.99，采购价 50 / 70 CNY 来自真实发票 Q 列；fx 用合成的 2026-10 customs_monthly = 7.2）：

| profile 设置 | `/api/customs/preview` 总额 | 导出 xlsx 总价单元格 | 其它 |
|---|---|---|---|
| basis=retail（默认） | **5598.72 USD**，均价 43.74 | 5598.72 | trade_term **C&F**；32 箱 / 128 件 / 264.0kg |
| basis=cost | **1022.22 USD**，均价 7.99 | 1022.22 | 行金额 555.56 / 466.66；预警“低于售价 30%”；全文不含 1021.76 |
| basis=fob，无手填 | **5598.72 USD** | 5598.72 | 页面和备注含“该值为零售价口径，非 FOB” |
| basis=cost，删掉 2026-10 汇率 | **409** FX_RATE_REQUIRED | 不生成文件 | 提示“缺 2026-10 USD/CNY 汇率” |
| basis=cost，先导出一次，再把汇率改成 7.1 后重新导出旧任务 | 仍是 1022.22 | 仍是 1022.22 | 快照 fx_rate=7.2 |
| trade_term=FOB，basis=retail | 5598.72 | 成交方式单元格 = FOB | basis 仍是 retail |
- **r12.1 补充：计征汇率来源与月份（代码 5）**
  - fx_rate 表增加 `source` 字段，customs_monthly 的值固定为 `CFETS 人民币汇率中间价，上月第三个星期三；非银行间外汇市场交易日顺延到下一交易日`（署令第 272 号第十三条，已核实）。界面录入时显示这句说明和“对应日期”。
  - 适用月份按**报关完成申报之日**确定（署令第 272 号第十四条，已核实），不按发货日、导出日。
  - 合成用例（fx 2026-10 = 7.2，2026-11 = 7.1）：申报日 **2026-10-31** → 取 2026-10 的 7.2；申报日 **2026-11-01** → 取 2026-11 的 7.1；申报日 2026-11-01 且没有 2026-11 汇率 → 409 `FX_RATE_REQUIRED`（不得回退到 10 月）。
  - 出口退税折合率（`tax_fx_basis`）：只允许“销售额发生当日”或“当月 1 日有效的中间价”两种；选定后 12 个月内修改要弹 ConfirmDialog。出处：《增值税法实施条例》（国务院令第 826 号）第十七条（2026-10-20 核实，2026-01-01 起施行）。

### R12-06 领星导入读写产品库，成本以 CNY 存储（代码 D3；测试 −4；运营 D6）
- **改法**：
  1. 新增 `POST /api/master-data/retail-prices/upload`（multipart xlsx/csv）。products **从产品库读取**，不再接收请求体里的 products（请求体字段保留但忽略，并在响应里返回 warning）。
  2. `imported[]` 写回 `product_master`：`listing_price`、`listing_price_currency='USD'`、`listing_price_at`、`retail_source=lingxing_xlsx|lingxing_mcp`、`retail_synced_at`，`field_sources.listing_price=lingxing`。手填值也会被覆盖（r11 定论）。
  3. 旧接口 `/api/master-data/import/listing/{preview,apply}` 改为调用同一套两层逻辑（价格链、站点过滤、币种为空时跳过、只按 MSKU 匹配），并且**不得新建 SKU**：未匹配的行只列在 `unmatched[]` 里。前端“领星导入”按钮改走新接口。
  4. 产品信息表“产品成本”列映射到新字段 `product_cost_cny`（`product_cost_currency='CNY'`），**不再写进 `declared_value`**。迁移时，`column_note` 为“产品成本→declared_value（CNY）”的老数据要迁移到新字段，`declared_value` 清空，并在 history 里记一条。报价引擎的末级回退读取 `product_cost_cny ÷ fx`。
  5. MCP 主路径：`/api/lingxing/sync` 的 listing 结果用同一个 `import_retail_rows`，source=lingxing_mcp（pytest 用 mock fixture）。
- **验收**（冒烟 S-03 / S-04，真实 `review/lingxing_listing_prices.xlsx` + 真实产品信息表；每档都用全新的数据目录）：
  - 空库上传 → `parsed_count=43`、`imported_count=0`、`unmatched_count=43`；skipped 只有 1 条：J-PETWOODSTAIRS-P-QingCang（“价格链无值”）。上传后库内 SKU 数仍是 **0**。
  - 只 PATCH 两个 ZHENTOU（create=true）→ **2 / 41**；然后 `GET /api/master-data/sku/J-PETMAT-CAR-ZHENTOU-1PC-FBA` 的 `listing_price == 39.99`、currency USD；TANZI 为 **49.99**。库内 SKU 数仍是 **2**。
  - 产品信息表（parsed 31 / upserted 31）+ 两个 ZHENTOU → **26 / 17**；库内 SKU 数**导入前后都是 33**（旧接口原来会把库从 31 改成 43，现在必须保持 33）。7 行组合装都在 unmatched，解析值为 62.68 / 90.23 / 89.28 / 61.73 / 102.58 / 73.13 / 73.13。
  - 用旧接口 `/api/master-data/import/listing/apply` 导入同一个文件，结果与新接口完全相同（26 / 17），且不新建 SKU。
  - `GET /api/master-data/sku/J-PETBARRIERS-FBA` → `product_cost_cny == 110`、`product_cost_currency == 'CNY'`、`declared_value is None`。该 SKU 没有售价也没有历史价时，报价 → **15.28 USD**，price_source=product_cost；合成用例 TEST_COST_A 80 CNY → **11.11**。
  - 请求体带 products 时，结果与不带时相同，并返回 warning“products 参数已忽略，按产品库匹配”。

### R12-07 货代过机表解析：认真实表头和表尾，舍入口径写死为 B（代码 D5/D6；测试 −6；运营 D1/D2；r12 方案关：代码 1–3、测试 a/b、运营 P1）
- **真实格式**（box 核实，第 13 批 5 个文件、第 15 批 5 个文件）：
  - 表头：`序号 | 入库时间 | 运单号 | 追踪号 | 件数 | 外箱号 | 单箱追踪号 | 单箱实重 | 长 | 宽 | 高 | 体积 | 单箱材重 | 计费重`
  - 表尾：**两批都是每个文件 2 行非空表尾，共 10 行**（另有空行，忽略、不计数）。文字标签落在“高”或“单箱材重”列：`入库体积 x | 入库计费重 bill`、`渠道最小计费重 30 | 平均单箱计费重`。
  - 第 15 批文件：`货代入库数据/` 与 `货代计费重确认文件/` 下各有 5 个同名 LCL 文件，已 `cmp` 确认逐字节相同。**冒烟脚本只读 `货代计费重确认文件/`**（与第 13 批“九方确认账单文件”口径一致），不用 glob 扫两个目录。
- **改法**（`measurement_adapters.py`）：
  0. **根因锚点（运营 r1.2）**：`measurement_adapters.py:88` 的 weight_kg 只认“实重 / 实重(kg) / 重量”，不认真实表头“单箱实重”，实测重量全为 None，所以 PR-10 的实重差是 −1271（实测侧为 0）。
  1. 列别名补上 单箱实重→weight_kg、单箱材重→volumetric_kg、计费重→chargeable_kg、运单号→waybill。
  2. 逐行分类：外箱号不为空且“单箱实重”能转成数字的行是箱数据；能找到“入库计费重 / 入库体积 / 渠道最小计费重”标签的行是 `forwarder_bill`（数值取标签右侧那一格）；全空行直接跳过、不记 issue；其余行忽略并记进 issues。**任何单元格转数字失败都只记 issue，不能 500**。
  3. **外箱号为纯数字时（openpyxl 读出 float 如 `1.0`，或字符串如 `'1'`、`'12'`），一律规范成整数字符串后判 `match_status=invalid_id`**，不自动配对。
  4. 一个文件 = 一个运单号 = 一条 `forwarder_bill`（bill_chargeable_kg、channel_min_kg、inbound_cbm）。**同一运单号再次导入时覆盖原记录（幂等）**，箱行按运单号整体替换，不重复计入。
  5. 申报侧尺寸取快照里 CSV 的英寸原值 × 2.54、重量取 lb × 0.45359237，**换算时全精度，不做中间舍入**。现状不只是显示精度：`volume_weight.py:27-42` 的 `to_cm()` 把 in×2.54 `round(…, 1)` 后**存储**（17.72 in → 45.0088 → 存 45.0），`to_kg()` 存 2 位；箱规对比路径改用不舍入的换算函数，`to_cm()` 保留给显示。也不能把尺寸取整成 45/45/41。
  6. 删除 `carton_math.published_batch13_identity()` 和用到它的测试。
- **舍入口径（r12.1 写死，口径 B）**，全部用 `Decimal`：
  1. 单箱体积重 = 长 × 宽 × 高 ÷ 6000（cm），**ROUND_HALF_UP 到 2 位**。这与九方表“单箱材重”列一致（例 47×46.5×44/6000 = 16.027 → 16.03）。
  2. 单箱计费重 = **ROUND_HALF_UP(max(单箱实重 kg, 上一步的 2 位体积重), 2)**，即对 max 的结果再保留 2 位（与 `review/work/rounding_r12_1.py` 第 30 行口径 B 一致）。申报侧用同一规则（申报 kg 由 lb 全精度换算后参与 max，max 结果再保留 2 位）。实测侧用实测“长宽高”按第 1 步自算，并断言与“单箱材重”列逐行相等（第 13 批 160/160 相等）。
  3. 每票 Σ单箱计费重（实测侧）；**推算账单 = Σ 向上取到 0.5kg**；冒烟断言推算账单 = 表尾“入库计费重”。
  4. 进位 = 账单 − Σ单箱计费重（实测侧）。
  5. 箱级差 = Σ实测单箱计费重 − Σ申报单箱计费重（只算匹配上的箱）；汇总值 ROUND_HALF_UP 到 2 位。总差 = 箱级差 + 进位合计。
  6. 实重差仅作参考：Σ实测单箱实重 − Σ申报 kg（**申报 kg 全精度，不逐箱舍入**）。
- **重复箱号**：同一外箱号在过机表里出现多于 1 次（第 13 批 FBA19P4NX8HHU000017 两条，9.90 / 7.19kg），**两条都剔除**，不挑其中一条；154 行 = 精确匹配 156 − 2。156 行口径只作对账参考。
- **适用范围**：口径 B 只在**九方第 13 批**（5 票）上用账单验证过。第 15 批两票账单与 Σ 不符（见第 8 章），其他货代未验证；换货代时必须先用其账单重跑本验证。
- **为什么是 B（证据，2026-10-20 box 复算，`review/work/rounding_r12_1.py`）**：判据是货代账单本身。

| 票（第 13 批） | 账单 入库计费重 | B：Σ逐箱 2 位 | B 推算（↑0.5） | A：Σ全精度 | A 推算（↑0.5） |
|---|---|---|---|---|---|
| EZGXA | 509 | 508.70 | 509 ✅ | 508.70 | 509 ✅ |
| PU1DA | 332.5 | **332.48** | **332.5 ✅** | **332.5033125** | **333 ❌** |
| V7GBA | 604 | 603.62 | 604 ✅ | 603.61 | 604 ✅ |
| W3JYA | 584 | 583.76 | 584 ✅ | 583.76 | 584 ✅ |
| WED2A | 517 | 516.64 | 517 ✅ | 516.64 | 517 ✅ |

  B 下 5 票全部复现账单；A、C（全精度体积重）在 PU1DA 上 Σ=332.5033125（显示为 332.50），向上取 0.5 得 333，与账单矛盾。“四舍五入到 0.5”在 EZGXA 得 508.5 ≠ 509，也被排除，所以账单规则是“向上取 0.5”。

- **验收**（冒烟 S-02 在运行时按上面口径独立复算，再与下表锚点断言相等）：

| 项 | 第 13 批锚点 | 第 15 批锚点 |
|---|---|---|
| 导入 HTTP 状态 | 5 个文件全部 200 | 5 个文件全部 200 |
| 箱数据行（逐文件） | 32 / 21 / 38 / 37 / 32 = **160**（EZGXA / PU1DA / V7GBA / W3JYA / WED2A） | 5 / 6 / 6 / 5 / 8 = **30**（6JJ6A / DHTZA / QGXTA / S97BA / UKEKA） |
| 非空表尾行（不算箱） | 每个文件 2 行，共 **10** 行 | 每个文件 2 行，共 **10** 行 |
| forwarder_bill 入库计费重 | 509 / 332.5 / 604 / 584 / 517 | 101 / 120 / 120 / 101 / 160 |
| 推算账单 = 账单 | 5/5 相等（见上表） | **不断言**（见第 8 章第 1 条：两票 Σ=100、账单 101） |
| 重复导入 | 同一 5 个文件再导一次 → forwarder_bill 仍 5 条、箱行仍 160 | 再导一次 → 仍 5 条、箱行仍 **30** |
| Σ 单箱实重（全部过机行） | **1287.50** kg（254.75 / 169.89 / 305.05 / 299.78 / 258.03） | 100 / 120 / 120 / 100 / 160 = **600.0** |
| 匹配情况 | 精确匹配 156、去重后 154；invalid_id 3（"1"）；unmatched 1（FBA19P4P4CL2U003937）；duplicate FBA19P4NX8HHU000017 ×2（9.90 / 7.19）；无过机记录 5 箱（CL2 U000001、U000025；N6MM2 U000005、U000006、U000020） | 30 行全部 invalid_id（外箱号是纯数字序号：1–5、1–6、1–5 加 12、1–5、1–8；QGXTA 含 `12`） |
| Σ申报 → Σ实测 单箱计费重（154 行） | **2131.36 → 2450.26** | — |
| 箱级差（154 行） | **+318.90** = 实重贡献 **0.00** + 尺寸贡献 **+318.90** | — |
| 进位（实测侧 Σ，全部过机行） | +0.30 / +0.02 / +0.38 / +0.24 / +0.36，合计 **+1.30** | +1.0 / 0 / 0 / +1.0 / 0，合计 **+2.00**（只作数据记录） |
| **总差（154 行）** | **+320.20** = 318.90 + 1.30 | 只显示整票对比 |
| 对账口径（156 行，含重复箱） | 箱级差 +322.74，总差 **+324.04** | — |
| 实重差（仅参考） | 154 行 1270.69 → 1242.32，**−28.37**；156 行 **−30.28** | — |
| 尺寸系统偏差 | 实测均值 46.96×46.39×43.81 vs 申报 45.01×45.01×41.00，**+14.9%**，154/154 箱为正 → 出现“建议更新箱规” | — |
| 守恒（全部 160 行，阈值 8.5） | 实测 轻 101 / 重 59 vs 申报 100 / 60 → “轻箱多 1、重箱少 1” | — |
| 单箱 | CL2 U000002：+2.49 / +1.49 / +4.00；MBQ U000031 显示“异常” | — |

- **反例用例（得到下列任一数值即判失败）**：

| 反例口径 | 154 行总差 | 156 行总差 | 说明 |
|---|---|---|---|
| A 全精度，不逐箱舍入 | 320.00（318.71 + 1.29） | 323.84 | PU1DA 推算 333 ≠ 账单 |
| C 申报 cm 2 位 / kg 3 位，不逐箱舍入 | 319.65（318.36 + 1.29） | 323.49 | 同上 |
| D 实测用“单箱材重”列、申报全精度 | 319.98（318.68 + 1.30） | 323.82 | 两侧口径不一致 |
| r12 拼接锚点 | 320.01 | 323.85 | A 的箱级差 + B 的进位 |
| 申报尺寸取整成 45/45/41、体积重不舍入 | 箱级差 319.31 | — | 尺寸被取整 |
| 表尾算作过机行（170 行）、实重 0、进位 0 | 实重差 −1271 | — | 运营 r1 实测的 PR-10 运行 |
| 申报 kg 逐箱保留 2 位 | 实重差 −28.68 | — | 实重差必须是 −28.37 |

- 复算命令：`cd /workspace/fba_tool && venv/bin/python review/work/rounding_r12_1.py`。参考实现写进 `tests/smoke/reference.py`（只读 realdata，不调用产品代码）。
- **实重占优用例（运营 Q1）**：第 13 批没有实重占优的箱（0/160），所以另加：
  - 合成：实测 20.004kg、61×46.5×37.5cm（体积重 17.73）→ 计费重 **20.00**；20.005kg → **20.01**（证明 max 结果再舍入）；申报 16.53 lb（7.4980kg 全精度）、尺寸 30×30×40cm（体积重 6.00）→ 计费重 **7.50**。
  - 真实：第 15 批 30 箱全部实重占优（20kg > 17.73），Σ 计费重 100 / 120 / 120 / 100 / 160，断言计费重逐箱 = 实重。
- 合成 pytest：表尾文字放在数字列 → 200 + issues；`1.0`、`'1'`、`'12'` → invalid_id；全空行不产生 issue；缺“单箱实重”列 → 422 中文提示；体积重 13.8375 → 13.84、16.027 → 16.03；Σ 332.48 → 推算 332.5，332.50 → 332.5，332.5033125 → 333.0（取整前不得先显示舍入）。

### R12-08 箱快照在 UI 路径上也要写入（运营 D3；代码 D7；X3）
- **改法**：
  - `/api/shipments/validate` 和 `/api/shipments/validate/stream` 都调用 `snapshot_from_validation`。异常不能被吞掉（现在是 `except Exception: pass`），要记日志并在响应里返回 `snapshot_warning`。
  - 写入 `batch`（从任务快照或文件名“第N批”取得）和 `declared_to_amazon_json`（CSV 原值 in/lb）。
  - 对比页没有快照时显示“尚无申报快照，请先完成第 4 步校验”。
- **验收**（冒烟 S-01/S-02，第 13 批 5 票 CSV + 5 个 PDF）：
  - 用流式接口校验后，`shipment_box_snapshot` 共 **160** 行（CL2 32 / MBQ 32 / N6MM2 37 / NX8HH 21 / P3PZC 38）。
  - CL2 U000002 的 `declared_to_amazon_json` = `{in: [17.72, 17.72, 16.14], lb: 16.53}`；换算后 45.01 / 45.01 / 41.00 cm、7.498 kg。
  - `GET /api/carton-compare?batch=13` 返回 `mode=box`，主表 **154** 行（而不是 ticket_only）。

### R12-09 净重默认口径（CL2 = 254.4）（测试 −2；运营 D7；X4）
- **改法**：
  1. `compute_net_weight` 的所有调用点（`customs_package.py` 里 8 处）都传入每箱皮重：先取 `carton_spec_id.tare_kg`（PR-5），再取任务快照里 Step1 的“空纸箱重(kg)”（混装箱取 `carrier_tare`），最后才回退到 0.2，并提示“第 N 箱缺皮重，按 0.2kg 计”。
  - **根因锚点（运营 r1.2）**：`customs_package.py:202`——`box_tares` 长度与箱数不符时直接 `net_weight_minus_per_box(gross, count, Decimal("0.2"))`，而 8 个调用点都不传 box_tares，所以总是走硬编码 0.2。修复后此处回退必须带“第 N 箱缺皮重”提示。
  2. `_net_weight_params()` 在字段为空时默认 `tare_from_carton`。迁移规则：老库 profile 是 `minus_per_box`、且 `updated_at` 早于本次升级、且没有用户编辑记录时，改成 `tare_from_carton`，在 history 记一条，并在 Step5 首次进入时显示 UI-5 ErrorNotice（r11 文案）。
  3. ratio 模式下 `net_ratio` 为空时默认 0.95（与 `DEFAULT_NET_RATIO` 一致），不能 422；界面显示“比例法无法规依据，非规范口径”。
- **验收**（冒烟 S-04；全新数据目录和升级库各跑一遍）：
  - 第 13 批 CL2：默认口径 **254.4** = 264.0 − 32 × 0.3（皮重 0.3 取自真实 `发货录入样表.xlsx`）；ratio 口径（不填 net_ratio）**250.8** = 264.0 × 0.95；毛重 264.0、32 箱不变。
  - 第 14 批 H13MS **112.8**、第 15 批 G1WQ **120.0**（皮重 0.2；第 15 批录入表是 `发货录入样表 (3).xlsx`）。
  - 用 user_version=3、profile 为 minus_per_box 的库升级 → 升级后 mode 为 tare_from_carton，CL2 为 254.4；如果用户之前手动选过 minus_per_box，升级后不改。
  - **r12.1 新增（代码 6）**：毛重、净重不足 1kg 时保留 2 位小数（ROUND_HALF_UP），不得填 1。合成用例：净重 0.456 → **0.46**；0.999 → 1.00；0.5 → 0.50；≥ 1kg 的按现有规则不变。出处：报关单填制规范（2019 年第 18 号）第二十五、二十六条，经海关总署公告 2024 年第 30 号修改，2024-04-10 起施行（已核实）。

### R12-10 第 13 批箱唛识别回归（测试 −8 之一；运营 D4；X6）
- **根因**：真实标签上 SKU 折成两行（`J-PETMAT-CAR-ZHENTOU-\n1PC-FBA`），`parse_pdf_pages` 解析出空 SKU；PR-1b 在 `shipment_cross_check.py:204` 把空 SKU 判为 ❌。
- **改法**：
  - 解析 PDF 时，如果 “Single SKU” 下一行以 `-` 结尾，或者下一行能和它拼成 CSV 里的某个 SKU，就拼接起来，再用 CSV 的 SKU 做前缀校验。
  - 拼不出 SKU、但 FNSKU 或数量与 CSV 一致时，按 ⚠️ 处理（“箱唛 SKU 未识别，已按 FNSKU/数量核对”），不报 ❌。只有 SKU、FNSKU、数量都识别不出时才报 ❌。
- **验收**（冒烟 S-01，第 13 批真实 5 个 CSV + 5 个 PDF，其中包括文件名为 `FBA19P4P4MBQ6` 的那个 PDF；流式和非流式接口都跑）：
  - HTTP 200、`ok=true`；响应全文“箱唛未识别”出现 **0** 次；160/160 页的 SKU 都能解析出来（CL2 32 页都是 J-PETMAT-CAR-ZHENTOU-1PC-FBA 或 TANZI，与 CSV 一致）。
  - 第 14 批 105 箱、第 15 批 30 箱：ok=true，“箱唛未识别”0 次。
  - **E2E-06（r12.1 改成可机械判定，测试 c）**：告警按类型计数，冒烟断言如下；任何不在下表里的告警类型出现即判失败。
    - 第 13、14、15 批：“箱唛未识别”= **0**；“箱唛 SKU 未识别，已按 FNSKU/数量核对”= **0**（真实标签 160/160、105/105、30/30 都能拼出 SKU）；DOWD 出现 **0** 次。
    - 其余 ⚠️（例如仓码不一致、申报总重不符）：每条告警的数值由 `tests/smoke/reference.py` 从真实文件独立复算，冒烟断言“告警集合 = 复算集合”（类型 + 票号 + 数值逐条相等），不再写死 5 / 5 / 0。r11 在 main 上的 5 / 5 / 0 作为参考写进 PR 描述；若不同，PR 描述按类型逐条解释。

### R12-11 N-01 仓码：DOWD 必须彻底消失（测试 −8 之一；运营 E2E-03；X7）
- **改法**：
  - 仓码只接受 `fba_warehouse` 白名单（`known_warehouse_codes()`），再加上 CSV 里出现过的仓码。
  - 页面上解析出的、不在白名单里的 4 字母片段不写进 `PdfBoxPage.warehouse_code`（存到 `ignored_tokens` 字段，只在调试日志里出现）。
  - CSV 与 PDF 不一致时采用 CSV，并生成 `warehouse_warnings`（UI-4 卡片）。
- **验收**（冒烟 S-01）：
  - 15 票的结果：CL2=CLT2、N6MM2=LAS1、MBQ=LAX9、P3PZC=TEB9、NX8HH=SBD1；CXY6X=TEB9、D3V7G=LAS1、H13MS=SBD1、CC1BM=LAX9、CV4RX=CLT2；KWP9=LAX9、937CV=LAS1、G1WQ=CLT2、5YXQQ=SBD1、5CCXC=TEB9。
  - 第 13 批 validate 响应全文中 “DOWD” 出现 **0** 次（集成前 p5 是 242 次）；状态行不出现“智能修正 … → DOWD”。
  - 第 13 批 CL2 的 warehouse_warnings 为 0 条（CSV 与 PDF 的白名单仓码一致）。

### R12-12 历史任务路径：统一返回 400（测试 −5；X5；r12 方案关测试 d）
- **改法**：
  - 新增 `safe_history_path(task_id)`：先做 URL 解码，再拒绝 `/`、`\`、`..`、NUL、冒号、长度 > 128 的 task_id；然后用 `resolve()` 检查路径仍在 `HISTORY_DIR` 内。
  - POST（快照里的 task_id）、GET、PATCH、DELETE 四个入口都调用它。不合法时返回 **400**，`code=INVALID_TASK_ID`，中文提示“任务编号不合法”。
  - 函数层的 ValueError 由路由层转换，不能再冒成 500。
  - **不改路由模板**（保持 `{task_id}`，不用 `{task_id:path}`，否则会吞掉 history 下已有或将来的子路由）。改为加一个中间件：请求的**原始路径**（`scope["raw_path"]`）以 `/api/tasks/history/` 开头时，取其后的整段做 URL 解码（最多两轮），交给 `safe_history_path` 同一套规则校验；不合法直接返回 400 `INVALID_TASK_ID`，请求不进入路由。POST 的请求体 task_id 仍在处理函数里调用 `safe_history_path`。
  - **子路由回归（新增）**：中间件上线后，`GET /api/tasks/history`（列表）→ 200；`GET /api/history/files` → 200；`GET /api/history/files/download?name=<已存在文件>` → 200、`name=../x` → 400；合法 `GET /api/tasks/history/Task-20260907-1344` → 200。
  - **download 接口（r12.3）**：`GET /api/history/files/download?name=` 的处理函数调用同一个校验函数 `safe_history_filename(name)`（拒绝 `/`、`\\`、`..`、NUL、冒号、长度 > 128，解码最多两轮，再用 `resolve()` 确认在 history 目录内），不合法返回 **400** `INVALID_FILE_NAME`，不得 404/500。用例：`name=../x`、`name=..%2Fx`、`name=%252e%252e%252fx`、`name=a\\..\\x` → 都是 400；存在的文件 → 200；合法但不存在 → 404。以后在 `/api/tasks/history/` 下新增子路由时，此用例必须扩充。
- **发送方式（r12.1 写死）**：
  - GET、PATCH、DELETE：task_id 放在 URL 路径里，**所有变体先整体做百分号编码**（`/` → `%2F`、`\` → `%5C`、`.` 保留，已编码的 `%2e%2e` 再编码成 `%252e%252e`），用 httpx 发送，并关闭客户端路径规范化（直接用编码后的原始路径字符串）。
  - POST：task_id 放在 JSON 请求体的快照字段里，原样发送，不编码。
- **验收**（冒烟 S-05，全新数据目录）：
  - 对 `../../TEST_evil`、`TEST_ok/../../x`、`..\..\x`、`%2e%2e/x`、`a%2F..%2F..%2Fx` 这 5 种写法，POST、GET、PATCH、DELETE 都返回 **400** 且 `code=INVALID_TASK_ID`，共 20 次请求。**只有 400 算通过；404、405、422、500、200 都判失败**（404 说明请求没到校验函数，不能证明已拦截）。
  - 数据目录里，除 `history/` 以外没有任何新增 json（集成前 p5 会写出 `<AD>/TEST_evil.json`）。
  - 正常的 `Task-20260907-1344` 可以保存和读取；删除不存在的 `NOPE_123` → **404**（R12-14；这是合法 id 找不到资源，与穿越无关）。

### R12-13 安全：P1-7 全部 5 条 + 日志脱敏补漏（代码 D1/D10）
- **改法**：r11 §4 PR-2b 的 P1-7 第 1–5 条**一条都不能少**：
  1. CORS 白名单，删除 `CORS_ALLOW_ORIGIN_REGEX`
  2. HMAC 签名 cookie `fba_session`，12 小时过期
  3. 删除 GET 登录
  4. DeepSeek Key 改存后端，`PUT /api/settings/deepseek-key`，Windows 用 DPAPI，非 Windows 返回 422
  5. 监听地址不是本机回环且没有口令 → 拒绝启动
- **日志脱敏**（`log_redact.py`）：
  - 先处理 `Authorization: Bearer <tok>`
  - 再处理 JSON 引号形式 `"(access_token|refresh_token|api_key|token|secret|password)"\s*:\s*"…"`
  - `(?i)\b[\w-]*(key|token|secret)\b\s*[:=]`
  - `sk-[A-Za-z0-9]{16,}`
  - 手机号 `(?:\+?86[- ]?)?1[3-9]\d[- ]?\d{4}[- ]?\d{4}`
  - **不对**报关单号 JUS、运单号 LCL 做日志脱敏（它们是业务号，用于排错）；r11 第 0 章的仓库扫描规则不变
- **验收**（pytest + 冒烟 S-06）：
  - **D14 逐项回归（r12.4 补，运营 r1.3 D14 的实测证据，集成前全部复现为失败）**：
    1. CORS 带凭证：`curl -i -H 'Origin: http://localhost:9999' http://127.0.0.1:<port>/api/health` 响应**不得**含 `access-control-allow-origin: http://localhost:9999`，也不得含 `access-control-allow-credentials: true`（集成前两者都有，来自 `settings.py:31` `CORS_ALLOW_ORIGIN_REGEX` + `main.py:178` `allow_origin_regex=`）；`rg CORS_ALLOW_ORIGIN_REGEX backend` 为 0。
    2. 明文 cookie：登录后 `Set-Cookie` 的名字是 `fba_session`，值**不等于、也不包含**口令原文（集成前 `security.py:74` 直接 `set_cookie(COOKIE_NAME, token)` 写口令）；改一个字节 → 401；12 小时后 → 401。
    3. GET 登录：`GET /api/auth/login?...` → **405**（集成前 `security.py:89` 仍有 `@app.get("/api/auth/login")`）。
    4. DeepSeek Key：vitest 断言 `localStorage` 里没有任何 key（集成前 `frontend/src/lib/deepseek-settings.ts:28` 从 localStorage 读）；`PUT /api/settings/deepseek-key` 存在，GET 只返回“已设置/未设置”。
    5. 非本机无口令拒绝启动：旧代码已有（`security.py:4、:56`），保留为回归用例，不能被改坏。
    6. 日志脱敏：下面 11 个样本集成前有 **8 个泄露**（只有后 3 个被脱敏），集成后 11/11 输出 `***`。
  - r11 P1-7 的全部验收：Origin 9999 的响应没有 ACAO 头；篡改 cookie、过 13 小时、改口令之后 → 401；GET 登录 → 405；`--host 0.0.0.0` 且没有口令 → 退出码非 0；vitest 检查 localStorage 里没有 key。
  - 脱敏表：下面 11 个输入都要输出 `***`，原值不能出现：`Authorization: Bearer abc.def.ghi1234`、`"access_token": "abcd1234efgh"`、`token=abcdef123456`、`DEEPSEEK_KEY=sk-1234567890abcdef`、`sk-1234567890abcdef1234`、`+8613812345678`、`138-1234-5678`、`138 1234 5678`、`api_key=sk-abcdef123456`、`x-api-key: zzzz9999yyyy`、`phone 13812345678`（集成前 p2b 实测漏掉 8 个，只有后 3 个被脱敏）。
  - 冒烟：用错误的领星凭据调用一次同步接口，再看日志文件，不能出现凭据原文。

### R12-14 交叉校验与删除的残留缺陷（测试 −3）
- **改法**：在集成分支上确认 p2a 的 D-04、N-09 和 p3 的 D-06 都生效。
- **验收**（冒烟 S-01，基于第 13 批真实文件构造变体，只在临时目录里处理）：
  - E2E-07：把 CL2 的 PDF 第 1 页复制一份 → 报“U000001 出现 2 页”，ok=false。
  - E2E-08：去掉 CL2 的 PDF → ok=false，最后一行以 ❌ 开头，页面上不出现“✅ 交叉校验通过”。
  - 删除不存在的任务 → 404。

### R12-15 过期误报（运营 D8）
- **改法**：过期判断改为比较各步骤输入的 sha256，不再依赖“上一步是否重新生成过”。
- **验收**（Playwright，第 14 批）：Step4 通过后，什么都不改，依次进入 4.5、5、6 → 页面上都没有“当前结果已过期”；修改 Step1 一个装量后再进入 5 → 出现过期提示，并列出受影响的步骤。

### R12-16 PR-1a 补“一键修正 / 去填单个重量”按钮（运营 D9；X10；r12 方案关运营 P4、测试 c）
- **改法**：Step1 的 `unit_weight_missing` 警告旁边加两个按钮：
  - “去填单个重量”：定位到单元格并聚焦
  - “一键修正”：弹出 ConfirmDialog，让用户输入单重，按 `装量 × 单重 + 皮重` 重算毛重并写回
- **新增判定**：单个重量为空或 0，且 `单箱毛重 ≤ 装量 × suspect_unit_weight_kg + 皮重 + 0.01` → 黄色警告“疑似把单件重填进了单箱毛重”，不阻断。
  - 全部用 `Decimal`（由字符串构造，不经过 float），容差 0.01kg 写成常量。
  - `suspect_unit_weight_kg` 存在 customs_rule_profile，**默认 0.5，内部经验值、可配置**，界面写“内部阈值，非官方规定”。
  - 依据（运营 r12 评审 8-3 实测）：产品信息表有数值的 SKU 单件包装重最小 1.06kg（STAIRS-2PCS），其余 1.3–2.48kg；第 13/14/15 批真实单重 1.8、2.3 / 1.5、1.7 / 4.0 → 按真实装量模拟 **0 次误报**。领星样表没有重量列，这一来源无法验证。
- **验收**（Playwright，第 13 批真实录入表 + pytest 边界）：
  - 两行都出现警告（1.8 ≤ 4×0.5+0.3 = 2.3；2.3 ≤ 2.3 相等边界也命中）。
  - pytest 边界：毛重 `2.3` → 命中；`2.31` → 命中（容差内）；`2.32` → 不命中；毛重以 float 0.1+0.2 方式产生的 2.3000000000000003 → 命中。
  - 一键修正时输入 1.8 / 2.3 → 毛重变为 7.5 / 9.5；Step1 合计 **1320.0kg**；STA 第 10 行 **16.53 / 20.94 lb**。
  - 不修正直接导出 → 409 `WEIGHT_CONFIRM_REQUIRED` + ConfirmDialog。
  - 第 14 批（单重 1.5/1.7，皮重 0.2）、第 15 批（单重 4.0）不出现这条警告。

### R12-17 政策数值依据官方资料（运营 D12；测试第 6 节第 3 条；r12 方案关运营 P2、P3）
- **出处（2026-10-20 在 box 上用无头 Chrome 渲染公开页面核实，不需要登录；WebFetch/curl 只能拿到 JS 外壳，不能当作页面不存在）**：
  - 箱规：Seller Central《Shipping and routing requirements》 `https://sellercentral.amazon.com/help/hub/reference/external/200141510?locale=en-US`。**policy 里原来写的 `G201081250`（《How Amazon receives and stores your inventory》）全部替换**。
  - 配置费：《FBA inbound placement service fee》 `https://sellercentral.amazon.com/help/hub/reference/external/GC3Q44PBK8BXQW3Z?locale=en-US`，适用 United States，**effective January 15, 2026**。
  - 两页的渲染全文存 box：`/workspace/ops_d1/sc_routing.txt`、`sc_placement.txt`（运营），`review/work/sc_200141510.txt`、`sc_GC3Q44PBK8BXQW3Z.txt`（代码 bot 复核，内容一致）。不进仓库。
- **箱规（`config/policy.default.json`，`source_type=amazon_official`，`source_url`=200141510，`verified_at=2026-10-20`）**：
  - 多件箱尺寸上限 **36.00"(L) × 25.00"(W) × 25.00"(H)**（长边 36、另两边 25；r12 的“每边 25 in”作废）。
  - 多件箱重量上限 **50.00 lb = 22.68 kg**，红色阻断。
  - **单件超大箱的判定（r12.2）**：箱内**恰好 1 件**（装量 = 1，且不是混装），并且该件尺寸段为 Small Bulky、Large Bulky 或 Extra-large（按 SKU 包装尺寸和下面的尺寸段表判定；缺尺寸时不算单件超大，按多件箱处理）。
  - **箱重与尺寸规则（r12.5 定稿，按 200141510 字面）**：
    - **原文**（`review/work/sc_200141510.txt`，2026-10-20 渲染；运营存档 `sc_routing.txt` 对应约第 93、128–142 行）：
      - 第 130 行：“Boxes must not exceed these maximum size and weight requirements: Dimensions: 36.00"(L) x 25.00"(W) x 25.00"(H), and weight: No more than 50.00 lb total. These limits apply unless the box contains an individual oversize item that exceeds these dimensions or weight.”
      - 第 158 行（小标题下）：“Boxes that contain a single oversize item that do not fit the above dimension limitations must comply with the following requirements:”
      - 第 159 行：“A box may exceed these dimensions only if it contains a single oversize unit that measures longer than 36 inches. If this is the case, then the box must only contain one single oversized item and must not be significantly longer than the item dimensions. …”
      - 第 160 行：“Boxes may exceed 50 lb, but must not weigh more than 65 lb. If this is the case, the box must still adhere to the maximum dimensions of 36.0"(L) x 25.0"(W) x 25.0"(H).”
      - 第 161–163 行：“Any box that weighs more than 50 lb must contain "Team Lift"/"Heavy Package" safety label displayed on top and sides of each heavy-weight box (5 labels in total).”
      - 第 169 行：“Boxes must not exceed the standard weight limit of 50.00 lb, unless they contain one single item that exceeds 50.00 lb.”；第 170–175 行：单件 >50.00 lb 贴 Team Lift，单件 >100.00 lb 贴 Mechanical Lift。
    - **判定（采纳测试 bot 的读法，运营也已同意，不折中）**：运营在 `delivery_review_ops_r1.4.md` 第 10 节同意此读法，并**作废**其此前对“条件 b = 最长边 >36 in 且 ≤65 lb”的认可（运营存档 `sc_routing.txt` 第 130 行只放宽尺寸，第 131 行的 50–65 lb 仍须在 36×25×25 内，第 139 行商品本身 >50 lb 放宽重量、无尺寸条件）。第 160 行的条件句是“If this is the case [箱子超过 50 lb], the box must **still** adhere to 36×25×25”。字面意思是：50–65 lb 的放宽只给尺寸在 36×25×25 以内的箱子；第 159 行的长度例外（箱子超出尺寸）与第 160 行的超重放宽**不能叠加**，长于 36 in 的箱子必须 ≤50 lb。r12.3/r12.4 把两者叠加（超长箱 50–65 lb 放行并提示“请向亚马逊核对”），比原文宽，作废。第 169 行是独立的另一条：箱内单件商品本身 >50 lb 时不受 50 lb 标准上限约束（运营 N1 的条件 a 保留）。第 130 行“unless … oversize item that exceeds these dimensions or weight”与此一致：超尺寸靠第 159 行，超重量靠第 160 行或第 169 行。
    - **规则**：
      1. 默认：尺寸超出 36×25×25 或箱重 >50 lb（22.68kg）→ **红色阻断**（多件箱、混装箱、非超大单件箱一律如此）。
      2. **(a) 商品本身单件重量 >50 lb**（第 169 行）：不按 50/65 lb 阻断；>50 lb 黄色 + Team Lift（5 处），>100 lb 黄色 + Mechanical Lift。尺寸仍按第 3、4 条判断。
      3. **(b) 单件超大商品、箱子在 36×25×25 以内**（第 160 行）：50 lb < 箱重 ≤ 65 lb → **通过** + 黄色 Team Lift；>65 lb 且不满足 (a) → 红色。
      4. **(c) 长度例外**（第 159 行）：箱内恰好 1 件单件超大商品，且该件最长边 >36 in → 箱子可以超出 36×25×25；但**箱重须 ≤50 lb**（不满足 (a) 时 >50 lb 红色，因为第 160 行要求超重箱仍在 36×25×25 以内）。箱子最长边比商品长 >4 in → 黄色“箱子明显长于商品”（4 in 为内部可配置值，原文只说“not significantly longer”）。**满足 (a) 时，箱子可以同时超出 36×25×25 和 50 lb（(a)+(c) 叠加），这是本工具自己的读法**：原文第 160 行与第 169 行怎样叠加没有写明，标 `pending_verification`（读法待确认），界面显示“待核实”，不作为冒烟断言依据。
      5. 不设“请向亚马逊核对”提示（r12.4 的该提示删除：按字面读法两条并不冲突，只是不能叠加）。
    - 亚马逊不提供提升标签。
  - 珠宝、手表箱 **≤ 40.00 lb**（SKU 带 jewelry/watch 标记时适用）。
  - AWD 25×25×25 in 不在本页，保留但 `source_type=pending_verification`。
- **尺寸段边界（运营 Q3）**：
  - 最大尺寸（已核实，出处 GC3Q44PBK8BXQW3Z 费率表的 Size 列，2026-10-20）：Small standard 15×12×0.75 in；Large standard 18×14×8 in；Small Bulky 37×28×20 in；Large Bulky 59×33×33 in；超出 Large Bulky 即 Extra-large。
  - 重量上限（Small standard 16 oz、Large standard 20 lb 由费率表的重量档上限可推出；Bulky 50 lb 同理）：`source_type=amazon_official_derived`，note 写“由费率表重量档推出”。
  - 《Product size tiers》帮助页 `https://sellercentral.amazon.com/help/hub/reference/external/201105770?locale=en-US`：box 上无头 Chrome 两次渲染都只拿到外壳（G201105770 与 201105770 都试过），**未核实**。其中的长+围长 ≤130 in、Extra-large 0–50 / 50–70 / 70–150 / 150+ lb 分档、体积重除数 139、Bulky 最小宽高 2 in，全部标 `pending_verification`，不作为阻断依据。
  - **22.5 kg 内部预警（运营 8-1 拍板）**：`internal_warn_kg` 默认 22.5（= 22.68 − 0.18 余量），可配置；黄色、**不阻断**；界面写“内部余量，非亚马逊规定”；**单件超大箱不触发**。真实批次 13/14/15 单箱最重 9.5 / 10.4 / 20kg，不会触发。
- **入库配置费（`source_type=amazon_official`，`source_url`=GC3Q44PBK8BXQW3Z，`effective_date=2026-01-15`，`verified_at=2026-10-20`）**。按官方 2026-01-15 起的表**整表替换**，与 p2c 现值对比：

| 尺寸段 | 重量档 | 官方 Minimal（单仓） | 官方 Partial（2–3 仓） | p2c 现值 | 处理 |
|---|---|---|---|---|---|
| Small standard（≤15×12×0.75 in） | ≤8 oz | $0.14–0.32 | 无此选项 | 0.16–0.30 | **改** |
| Small standard | 8+–16 oz | $0.16–0.32 | 无此选项 | 0.18–0.36 | **改** |
| Large standard（≤18×14×8 in） | ≤12 oz / 12 oz–1.5 / 1.5–3 / 3–5 / 5–7 / 7–10 / 10–15 / 15–20 lb | 0.20–0.40 / 0.24–0.50 / 0.34–0.60 / 0.38–0.76 / 0.40–0.98 / 0.42–1.20 / 0.44–1.50 / 0.55–1.90 | 无此选项 | 一致 | 不改 |
| Small Bulky（≤37×28×20 in） | ≤5 / 5–12 / 12–28 / 28–42 / 42–50 lb | 1.10–1.60 / 1.75–2.40 / 2.74–3.50 / 3.95–4.95 / 4.80–5.95 | 0.55–1.10 / 0.65–1.75 / 0.81–2.19 / 1.05–2.83 / 1.23–3.32 | 一致 | 不改 |
| Large Bulky（≤59×33×33 in） | ≤5 / 5–12 / 12–28 / 28–42 / 42–50 lb | **1.30–1.80 / 2.10–2.90 / 3.40–4.10 / 4.70–5.60 / 5.50–6.50** | **0.55–1.25 / 0.65–1.80 / 0.81–2.30 / 1.05–2.95 / 1.23–3.50** | 2.40–3.20 起，10 个区间全不同 | **改** |
| Extra-large | — | 不收此费 | — | 0 | 不改 |

  - Amazon-optimized（≥5 仓）：免费；条件是每个商品至少 5 个相同纸箱（同装量、同混装组合），工具在不满足时不显示 $0 选项。
  - **计费重量基准（按尺寸段选档）**：Small standard 用**单件重**；Large standard、Small Bulky、Large Bulky 用 **max(体积重, 单件重)**。`policy` 每个 class 增加 `weight_basis ∈ {unit, max_dim_unit}`。
  - 收费时点写进 note：入仓 45 天后按实收数量收费。
  - 旧表（2025-02-20 至 2026-01-15）不保留在默认配置里；需要回算历史时，另建带 `effective_to` 的条目。
- **验收**：
  - pytest：policy 里每个数值都有 `source_type`、`source_url`、`verified_at`；`rg G201081250 backend` 结果为 0。
  - 多件箱 22.6kg → 黄色“超过内部余量 22.5kg”；22.7kg（50.04 lb）→ 红色“超过亚马逊 50 lb（22.68kg）上限”；多件箱尺寸 36.5×20×20 in → 红色；36×25×25 → 通过。
  - **尺寸用例**：1 件 Large Bulky 商品 40×15×8 in（22kg）装 42×22×12 in 箱、箱重 22.5kg（49.6 lb）→ **通过**（条件 c）；同一商品装 48×22×12 in 箱、22.5kg → 通过 + 黄色“箱子明显长于商品”；**反例：2 件 40 in 商品装一箱 → 红色**；**1 件 Small Bulky 商品 35×15×10 in（15kg），装 37×26×20 in 箱 → 红色**（商品不长于 36 in，不适用条件 c）。
  - **重量用例（r12.5 按字面读法改写）**：
    - **改判：1 件 Large Bulky（40×15×8 in，商品 22kg = 48.5 lb）装 42×22×12 in 箱，25kg（55.1 lb）→ 红色**（超长箱须 ≤50 lb；r12.4 写成“不阻断 + 请向亚马逊核对”，作废）；同一箱 28kg（61.7 lb）→ **红色**。
    - **新增：1 件 Small Bulky 商品 34×20×10 in（22kg）装 35×22×12 in 箱（在 36×25×25 以内），25kg（55.1 lb）→ 通过 + 黄色 Team Lift**（条件 b）；同一箱 28kg（61.7 lb）→ 通过 + Team Lift；30kg（66.1 lb）→ **红色**（>65 lb，商品不 >50 lb）。
    - **改判：1 件 Small Bulky，30×20×10 in，商品 22kg（48.5 lb），装 32×22×14 in 箱后 23kg（50.7 lb）→ 通过 + 黄色 Team Lift**（条件 b；r12.4 按运营 N1 当时的读法写成红色，r12.5 按字面改判）。
    - 1 件 Extra-large 商品自身 24kg（52.9 lb > 50 lb）、30×20×10 in，装箱 25kg（55.1 lb）→ 通过 + Team Lift（条件 a）；1 件 Extra-large 商品自身 45kg（99.2 lb）、30×20×10 in，装箱 46kg（101.4 lb）→ 通过 + Mechanical Lift（条件 a，不受 65 lb 限制）；**1 件 Extra-large 商品自身 31kg（68.3 lb）、50×28×18 in，装 52×30×20 in 箱、32kg（70.5 lb）→ 通过 + Team Lift**（条件 a 放宽重量，条件 c 放宽尺寸）。**注：这是本工具自己的读法**：原文第 160 行（超重箱仍须在 36×25×25 内）与第 169 行（单件商品 >50 lb 可超 50 lb）怎样叠加没有写明，此用例按“第 169 行独立于第 160 行”判通过，标 `pending_verification`，界面显示“待核实”，不作为冒烟断言依据。
    - **反例：2 件 Large Bulky 商品（各 40×15×8 in、12kg）装一箱 28kg → 不是单件箱，红色“超过 50 lb”**；**3 件 Large standard 商品（每件 18×14×8 in、8.5kg = 18.7 lb）装一箱 25.5kg（56.2 lb）→ 多件箱，红色**。
    - **运营 N1 用例（`delivery_review_ops_r1.4.md` 第 10 节第 4 条，逐字引用）**：
      > - 1 件 40 in Large Bulky（商品 22 kg / 48.5 lb）装 42×22×12 in 箱、25 kg（55.1 lb）→ **红色**；
      > - 同一商品装 42 in 箱、箱重 22.5 kg（49.6 lb）→ 尺寸通过、重量通过；
      > - 1 件 30 in Small Bulky（商品 22 kg）装 32×22×20 in 箱、28 kg（61.7 lb）→ 不阻断 + Team Lift（条件 b：尺寸在 36×25×25 内、≤65 lb）；同一箱 30 kg（66.1 lb）→ 红色；
      > - 1 件 Extra-large 商品 24 kg（52.9 lb），最长边 40 in，装 42 in 箱、25 kg → 不阻断 + Team Lift（第 139 行）。
      - 实现时补全的尺寸（引文未给出，按尺寸段复算选取，红绿判定不变）：40 in Large Bulky 取 40×15×8 in；30 in Small Bulky 取 30×20×10 in；24 kg Extra-large 取 40×15×8 in（按重量就是 Extra-large）。运营存档第 139 行对应本方案 `work/sc_200141510.txt` 第 169 行。注：上面引文中“24 kg Extra-large、40 in 商品装 42 in 箱、25 kg → 不阻断”一条，与第 494 行最后一条“1 件 Extra-large 商品自身 31kg（68.3 lb）、50×28×18 in，装 52×30×20 in 箱、32kg（70.5 lb）→ 通过 + Team Lift”同属一类（箱超 36 in 且超 50 lb），依赖同一读法，同标 `pending_verification`（读法待确认），不作为冒烟断言依据。
    - **边界用例（r12.6 新增）**：1 件单件超大商品、箱子在 36×25×25 in 以内，箱重 29.48kg（64.99 lb）→ **通过** + 黄色 Team Lift；29.49kg（65.01 lb）→ **红色**（>65 lb，商品本身不 >50 lb）；任一箱重恰好 50.00 lb（22.6796kg）→ 不算“>50 lb”，**不贴** Team Lift（多件箱同样通过）。换算按 1 kg = 2.20462 lb、1 lb = 0.45359237 kg，脚本复核。
    - 珠宝箱 18.2kg（40.1 lb）→ 红色。
  - **配置费逐档验收（r12.4，对照 `review/work/sc_GC3Q44PBK8BXQW3Z.txt` 第 129–135、210–227 行，“starting January 15, 2026”表；Large Bulky 表在存档里完整，无截断；测试 r1.3 第七节列出的 12 个不符值逐个改正）**：pytest 逐档断言 `policy.default.json` 的数值：
    | 尺寸段 | 重量档 | Minimal（单仓） | Partial（2–3 仓） | p2c 原值（错） |
    |---|---|---|---|---|
    | Small standard | ≤8 oz | 0.14–0.32 | 不可选 | 0.16–0.30 |
    | Small standard | 8+–16 oz | 0.16–0.32 | 不可选 | 0.18–0.36 |
    | Large Bulky | ≤5 lb | 1.30–1.80 | 0.55–1.25 | 2.40–3.20 / 1.20–2.10 |
    | Large Bulky | 5+–12 lb | 2.10–2.90 | 0.65–1.80 | 3.10–4.00 / 1.40–2.60 |
    | Large Bulky | 12+–28 lb | 3.40–4.10 | 0.81–2.30 | 4.20–5.40 / 1.80–3.40 |
    | Large Bulky | 28+–42 lb | 4.70–5.60 | 1.05–2.95 | 5.50–6.80 / 2.20–4.10 |
    | Large Bulky | 42+–50 lb | 5.50–6.50 | 1.23–3.50 | 6.40–7.90 / 2.60–4.80 |
    - 不变的档也逐档断言（Large standard 8 档、Small Bulky 5 档、Amazon-optimized No fee），防止整表替换时改坏。Extra-large：官方写“doesn't apply”，配置 0 并带 source_url。
    - **重量基准用例**：Small standard 只看单件重（单件 0.4 lb、体积重 2 lb → ≤8 oz 档，0.14–0.32；单件 0.6 lb → 8+–16 oz 档，0.16–0.32）；Large standard / Small Bulky / Large Bulky 用 max(体积重, 单件重)（Large Bulky 单件 4 lb、体积重 6 lb → 5+–12 lb 档 2.10–2.90；单件 6 lb、体积重 4 lb → 同档；单件 4 lb、体积重 4.5 lb → ≤5 lb 档 1.30–1.80）。
  - 配置费合成用例：Small standard 0.4 lb（6.4 oz）、体积重 2 lb → 按单件重落 ≤8 oz 档 **$0.14–0.32**；Large standard 单件 1 lb、体积重 4 lb → 按 4 lb 落 3–5 lb 档 **$0.38–0.76**；Large Bulky 10 lb Minimal → **$2.10–2.90**、Partial → **$0.65–1.80**；Small standard 选 Partial → 不可选；Extra-large → $0。

### R12-18 STA 预检：只检查 SKU 明细区，不检查箱信息标签行（运营 D13，r1.1 已复验确认）
- **STA 模板结构（r12.3，按规则描述）**：表头（SKU / 商品名称 / ASIN …）在第 5 行；SKU 明细区是第 6 行到第 5+N 行（N = 本装箱组 SKU 数，第 3 行“SKU 总数：N”）；第 6+N 行为空行；**第 N+7 到 N+11 行是 SKU 明细区之后的 5 行箱信息标签行**（包装箱名称 / 包装箱重量（磅）： / 包装箱宽度（英寸）： / 包装箱长度（英寸）： / 包装箱高度（英寸）：）。真实文件核对（2026-10-20，openpyxl 读 `realdata/batches/*/Send to Amazon表格.xlsx`）：第 13 批 N=2 → 第 **9–13** 行；第 14 批 N=6 → 第 **13–17** 行；第 15 批 N=1 → 第 8–12 行。第 13 批就是 Marco 实际上传成功的文件，运营也核实为 9–13。
- **根因**（运营 r1.1 复验，代码 bot r1.2 自己复现，:8044 回放第 14 批）：`backend/fba_tool/sta_precheck.py` 第 68–90 行从表头往下逐行检查，只跳过全空行和 SKU 列为空的行。第 14 批 STA 第 13–17 行（N=6 时的标签行）的 A 列是“包装箱名称 / 包装箱重量（磅）： / 包装箱宽度·长度·高度（英寸）：”等标签文字，不为空，于是每行报“商品名称 / ASIN / FNSKU / 预计数量 必填项为空”，5 行 × 4 = **20 条误报**。
- **改法**：
  1. SKU 明细区 = 表头下一行起共 N 行（N 取第 3 行“SKU 总数”）；同时做兜底：遇到第一个“全空行”或第一个 A 列命中箱信息标签（`包装箱名称`、`包装箱重量`、`包装箱宽度`、`包装箱长度`、`包装箱高度`、`箱号`，前缀匹配，忽略全角冒号和空格）的行为止。之后的行不做 SKU 必填检查。
  2. 另外，SKU 必须出现在本次录入的 SKU 清单里才检查；不在清单里的非空 A 列记一条 debug 日志，不出高亮。
  3. 标签集合写成常量，并有单元测试；以后模板改版时只改这一处。
- **验收**（冒烟 S-07）：
  - **第 13 批**：Marco 实际上传成功的 STA，以及工具对第 13 批导出的 STA，预检“必填项为空”类提示都为 **0** 条；第 **9–13** 行（N=2 的标签行）高亮 **0** 条。
  - **第 15 批**：第 8–12 行（N=1 的标签行）高亮 **0** 条。
  - 合成：N=3 的模板，标签行在第 10–14 行 → 0 条；“SKU 总数”与实际 SKU 行数不一致 → 按兜底规则截断并给一条黄色提示。
  - **第 14 批**（运营 r1 请求体 `/workspace/ops_d1/p3_b14_export_step3_sta_precheck.req.json` 回放）：第 13–17 行误报 **0** 条（集成前 20 条）；第 6–11 行缺 ASIN/FNSKU 的提示条数 = 请求体里这几项为空的 SKU 数（冒烟时从请求体复算后断言，不写死）。
  - 合成：A 列写“包装箱名称”且其余列为空 → 不报；把一个真实 SKU 写到标签行下面 → 不检查且有 debug 日志；SKU 明细区内真缺 FNSKU → 照常报。
- **验收**（冒烟 S-07，第 14 批）：第 12–17 行的“商品名称 / 预计数量 必填项为空”这类提示 **0** 条；第 6–11 行缺 FNSKU 的提示条数等于录入表里 FNSKU 为空的 SKU 数（运营核实为 4，冒烟时从真实 `发货录入样表.xlsx` 复算后断言）。第 13 批“Marco 实际上传成功的 STA”预检 **0** 条高亮（r11 UI-3）。

### R12-19 UI-Q 实测、STA 下拉清单（代码 D12）
- **改法**：
  - `docs/ux_baseline.json` 里的数字必须来自 Playwright 实跑 `scripts/e2e/click_count.py --live`，原始事件日志存 `docs/ux_baseline_events.json`。
  - `sta_dropdowns.default.json` 由 box bot 从 Marco 提供的卖家后台空白 STA 模板抽取（只提交抽出来的清单）。在模板到手之前，文件里标 `status=provisional`，并在 UI 上提示。
- **验收**：baseline 和 current 两次实跑的点击数，都要和事件日志条数一致；current ≤ baseline × 0.5（r11）。

### R12-20 清理生产代码里的测试断言（代码 D13）
- **验收**：`rg "1021\.76" backend --glob '!**/test*'` 结果为 0；pytest 里保留“全文不含 1021.76”的断言。

### R12-21 Figma（Marco 要求，r11 已列）
- PR-3 和第 9 章箱规库的两个页面，先出 Figma 稿，三方打分都 ≥ 99.5 后再定稿。设计稿链接写进集成 PR 的描述。这一项不计入代码交付分，但交付前必须完成。

## 5. 官方依据（r12.1 复核；其余见 r11 第 11 章）
| 主题 | 依据 | 核实状态 | 用在哪里 |
|---|---|---|---|
| 申报必须如实，不能用 0 价 | 《中华人民共和国海关法》第二十四条（如实申报）；《中华人民共和国海关进出口货物申报管理规定》（申报内容必须与实际相符）；海关总署公告 2020 年第 75 号（9810 模式：企业对传输数据的真实性承担相应法律责任） | 沿用 r11 | R12-04、R12-05 |
| 美国进口发票价值 | 19 CFR 141.86 | 沿用 r11 | R12-04、R12-05 |
| 计征汇率 | 海关总署令第 272 号《进出口货物征税管理办法》（2024-12-01 施行）第十三条：上月第三个星期三 CFETS 人民币汇率中间价，非交易日顺延，四舍五入至分；第十四条：适用完成申报之日实施的计征汇率 | **已核实** 2026-10-20（gov.cn 国务院公报 2024 年第 33 号） | R12-05 |
| 《关税法》计征汇率条款 | 《中华人民共和国关税法》（计征汇率相关条款）——**不写条款号** | `pending_verification` | R12-05（仅作背景，不作断言依据） |
| 出口退税折合率 | 《增值税法实施条例》（国务院令第 826 号，2026-01-01 施行）第十七条：可选销售额发生当日或当月 1 日有效的人民币汇率中间价，确定后 12 个月内不得变更 | **已核实** 2026-10-20（gov.cn 政策库） | R12-05 |
| 出口退（免）税管理办法 | 国家税务总局公告 2026 年第 5 号《出口业务增值税和消费税退（免）税管理办法》（广东省税务局 2026-04 问答引用，含“退税率以报关单实际出口日期为准”的口径）——具体条款号未打开原文 | `pending_verification` | R12-05（退税率适用日期；不作断言依据） |
| 毛重、净重填制 | 《报关单填制规范》（海关总署公告 2019 年第 18 号）第二十五、二十六条，经海关总署公告 2024 年第 30 号修改（2024-04-10 施行）：净重 = 毛重 − 外包装材料重；不足 1kg 精确到小数点后 2 位 | **已核实** 2026-10-20（海关总署 PDF 原文） | R12-09 |
| 9810 海外仓 | 海关总署公告 2024 年第 167 号 | 沿用 r11 | R12-05 |
| 箱重与尺寸 | Seller Central 200141510《Shipping and routing requirements》：多件箱 36×25×25 in、≤50 lb（红色阻断）；单件箱 >50 lb 只在 (a) 商品本身 >50 lb（第 169 行），或 (b) 单件超大商品、箱子在 36×25×25 以内且 ≤65 lb（第 160 行）时放宽（黄色 + Team Lift，>100 lb Mechanical Lift）；(c) 单件超大商品最长边 >36 in 时箱子可超出尺寸，但箱重须 ≤50 lb（除非满足 a）；其余红色（与 R12-17 一致）；珠宝手表 ≤40 lb；箱重和尺寸必须准确 | **已核实** 2026-10-20（无头 Chrome 渲染） | R12-07、R12-16、R12-17 |
| 入库配置费 | Seller Central GC3Q44PBK8BXQW3Z《FBA inbound placement service fee》，2026-01-15 起 | **已核实** 2026-10-20 | R12-17 |
| AWD 25×25×25 in | 未在上面两页找到 | `pending_verification` | R12-17 |
| 尺寸段最大尺寸 | GC3Q44PBK8BXQW3Z 费率表 Size 列（15×12×0.75 / 18×14×8 / 37×28×20 / 59×33×33 in） | **已核实** 2026-10-20 | R12-17 |
| 尺寸段其余规则（长+围长 130 in、Extra-large 分档、除数 139） | Seller Central 201105770《Product size tiers》 | `pending_verification`（页面未渲染出正文） | R12-17 |
| STA 模板结构 | 第 13/14/15 批真实 STA 文件（Marco 第 13 批实际上传成功）：标签行 = 第 N+7 到 N+11 行（9–13 / 13–17 / 8–12） | box 真实文件，2026-10-20 核对 | R12-18 |
| 每箱贴箱标 | FBA_SPD_Shipments_en-US.pdf | 沿用 r11 | R12-11 |
| 商品级实测 | SP-API Fee Preview 报告（r11 §9.4） | 沿用 r11 | 不变 |
| 个人信息与密钥 | 《个人信息保护法》第五十一条；《数据安全法》第二十七条 | 沿用 r11 | R12-13 |

> `verified_at` 只能由 bot 在 box 上打开原文后填写，云代理不能自己编 URL 或日期。标 `pending_verification` 的出处，界面显示“待核实”，pytest 和冒烟不以它为断言依据。

## 6. 交付关 r1 扣分 → r12 对照表（r12 方案关扣分 → r12.1 见文首修订记录）
| 来源 | 扣分点 | 分值 | r12 条目 |
|---|---|---|---|
| 代码 D1 | P1-7 安全项完全没做 | −6 | R12-13 |
| 代码 D2 | 申报价口径没接进导出；没有 fx 接口 | −4 | R12-05 |
| 代码 D3 | 领星导入不读也不写产品库；产品成本没带币种；回退链没串起来 | −4 | R12-06、R12-04 |
| 代码 D4 | 缺价时申报 0；fob 少一级；整票回退 | −3 | R12-04 |
| 代码 D5 | 真实过机表导入时 500；表头和表尾都不认 | −4 | R12-07 |
| 代码 D6 | 320.01 是硬编码的自证测试 | −1 | R12-07、R12-03 |
| 代码 D7 | 快照没存 in/lb，也没存 batch | −1 | R12-08 |
| 代码 D8 | 扫描测试依赖 .git；test1 冒烟测试没有 skip | −2 | R12-01 |
| 代码 D9 | lock 文件不同步 | −1 | R12-02 |
| 代码 D10 | 日志脱敏有漏洞 | −1 | R12-13 |
| 代码 D11 | 叠栈不完整、合并冲突 | −1 | R12-00 |
| 代码 D12 | UI-Q 不是实测；STA 下拉清单是手写的 | −0.5 | R12-19 |
| 代码 D13 | 生产代码里写 1021.76 断言 | −0.5 | R12-20 |
| 测试 1 | 没有可交付的完整分支 | −12 | R12-00 |
| 测试 2 | N-01 DOWD 没修；#3 箱唛回归 | −8 | R12-11、R12-10 |
| 测试 3 | D-05 没修，或者返回 500 | −5 | R12-12 |
| 测试 4 | 九方文件 500；实重没入库；数字对不上 | −6 | R12-07、R12-08 |
| 测试 5 | 领星写入层和产品成本回退；新旧接口规则不一致 | −4 | R12-06 |
| 测试 6 | 净重默认 257.6 | −2 | R12-09 |
| 测试 7 | npm ci 失败；realdata 3 个失败；扫描依赖 .git | −3 | R12-01、R12-02 |
| 测试 8 | N-09、D-04、D-06 没修；`TEST_ok/../../x` 返回 500 | −3 | R12-14、R12-12 |
| 测试 9 | 缺真实数据回归 | −12 | R12-03（冒烟脚本）、R12-00 第 3 条 |
| 运营 D1 | 九方导入 500 | −8 | R12-07 |
| 运营 D2 | +320.01 写死；实算 318.90 | −5.5（r1 −8 → r1.1 −6 → r1.3 −5.5） | R12-07（X1 在 r12.1 更正：318.90 是口径 B 的箱级差。分值：运营 `delivery_review_ops_r1.md` 仍记 −8；运营更正版 `delivery_review_ops_r1.1.md` 改为 −6，总分 44 → 46。r12.1 写“已自行改为 −6”时 r1.1 尚未发布，属于提前转述，r12.2 更正） |
| 运营 D3 | 正常流程不写快照 | −5 | R12-08（X3） |
| 运营 D4 | p1b 箱唛全部未识别 | −8 | R12-10 |
| 运营 D5 | Step5 不受口径影响 | −8 | R12-05 |
| 运营 D6 | 领星 UI 路径还是旧行为、会新建 SKU | −5 | R12-06 |
| 运营 D7 | 净重 257.6；ratio 不填 net_ratio 时 422 | −3 | R12-09 |
| 运营 D8 | 过期误报 | −2 | R12-15 |
| 运营 D9 | 缺一键修正按钮 | −2 | R12-16 |
| 运营 D10 | 集成与构建 | −3 | R12-00、R12-02 |
| 运营 D11 | 报价接口传数字 fx 时 500；fob 回退为 0 且提示与事实不符 | −2 | R12-04 |
| 运营 D12 | 配置费来源不是官方 | −1 | R12-17 |
| 运营 D13 | STA 预检把第 13–17 行箱信息标签行当 SKU 行（r1.1 复验确认） | −1 | R12-18 |
| 运营 D14 | P1-7 安全项基本没做（CORS 带凭证、明文 cookie、GET 登录、Key 在 localStorage）；日志脱敏 11 个样本泄露 8 个（r1.3 新增；非本机无口令拒绝启动已有） | −5 | R12-13 |

## 7. r12 交付流程
1. 云代理按 r12.1 在 `plan/integration-r12` 上完成 R12-00…R12-20，开一个 PR，不合并。
2. 三个 bot 在 box 上各自：重建 testrun → 跑冒烟脚本 → 起服务做 UI 回放 → 独立打分 → 交叉打分。全部 100 分才交付。
3. 不满 100 分时，按“扣分 → r13 条目”的对照表写下一轮方案，三方方案分和交叉分 ≥ 99.5 后再交给云代理（与 r11 流程相同）。

## 8. 仍待定的点（r12.5）
r12 第 8 章的第 1 条（318.90 来源）、第 2 条（22.5 预警）、第 3 条（配置费出处）、第 5 条（0.5kg 阈值）已在 r12.1 关闭，见修订记录。剩下：
0. **口径 B 的适用范围**：只在九方第 13 批 5 票上验证。换货代或新批次时先用账单复跑 `rounding_r12_1.py` 再用。
1. **第 15 批两票账单多 1kg（待定）**：6JJ6A、S97BA 都是 5 箱 × 20kg，Σ单箱计费重 = 100.00，账单 = 101；另三票 120 / 120 / 160 与 Σ 相等。任何舍入规则都解释不了（体积重 61×46.5×37.5/6000 = 17.73 < 20kg，计费重就是实重）。r12.1 只把 +2.00 作为数据记录，不对第 15 批断言“推算账单 = 账单”。需要 Marco 向九方确认（可能是 5 箱票的最低收费或附加计重）。
1a. **尺寸段帮助页 201105770 未渲染出正文**：长+围长、Extra-large 分档等标 `pending_verification`，需要有人在可登录的浏览器里打开核实。
2. **国家税务总局公告 2026 年第 5 号的具体条款号**、**《关税法》计征汇率的条款号**：都是 `pending_verification`，等打开原文后补。
3. **E2E-06 的 ⚠️ 实际条数**：r12.1 已改成“告警集合 = reference.py 复算集合”的机械规则；实际数字要在集成分支上跑出来写进 PR 描述。
4. **官方页面需 JS 渲染**：后续复核要用无头浏览器（WebFetch/curl 只能拿到外壳）。官方页面变动时要重新核实并更新 `verified_at`。
5. **r11 的 PR #1–#10 是否关闭**：由 Marco 决定（关闭 PR 是对外可见的操作，r12.1 不会自行关闭）。
