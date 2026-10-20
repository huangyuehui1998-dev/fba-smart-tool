# S9-step4-fix3 独立复测报告

- 被测提交：`8221d92`（s9-step4-fix3）。基线 `e3d3908`（s9-step4-fix2，上轮报告 `S9_step3_4_评审.md` 给 96.9，不通过，必须修 L-b / N1 / N2）
- 评审时间：2026-10-17 13:32–14:15（美东时间 ET）
- 方式：只读复测。副本在 `%TEMP%\fba_review_s9s4fix3\`：
  - `repo`（8221d92，回归、截图、运行时变异用）；
  - `repo_mut`（8221d92，探针和源码变异专用，每个变异跑完立即还原原文，结束时 `git status` 干净）。
- 隔离：每个探针都单独设 FBA_APP_DATA_DIR，FBA_NO_BROWSER=1。领星全部用 mock，假 Key `lxFAKE-TESTONLY-000`，没有调用真实领星接口。
- 没碰的东西：
  - 没碰 `%TEMP%\fba_s1`，没读开发方截图；
  - 146 个副本目录只读，没移动，没删除；
  - `frontend\node_modules` 是联接，指向上轮的只读副本，没有递归删除任何东西，也没删除任何文件。
- 原仓库只新增本报告，没 add，没 commit。真实数据快照前后 0 差异（见六）。
- 脱敏：本报告不写任何真实 store_id、sid、ASIN、MSKU、FNSKU、店铺名、品牌名或品名，只写「文件:行号 + 类型」、计数，或 DEMO 示例值。带品名或店铺名的文件名用「…」代替。

---

## 一、结论与得分表

**总分 99.5 / 100，通过（及格线 ≥ 99）。**

上轮 3 个必须修的项（L-b、N1、N2）和 4 个轻微项（L-c、N3、N4、UI）都已修好，并有测试和变异覆盖。回归全部通过：
- pytest 1090 正序、逆序、随机顺序（seed 20261017），先跑 step3/4/fix 相关文件 341；
- golden 82，tsc 0；
- 冒烟 20/20（新增“按内容比对临时目录无真实副本”一项）；
- 密钥扫描 0，脱敏无新增。

这次失分只来自 4 个轻微项（见二）。

| 项 | 结论 | 扣分 |
|---|---|---|
| L-b 护栏强度 | 改为按内容比对：大小粗筛 + SHA-256（只在内存）+ SQLite 表特征。上轮 9 种复制方式 **9/9** 拦住，另加 VACUUM INTO、journal 模式副本、改 1 字节的库也拦住；不误报；不输出哈希和来源路径；不改真实文件 mtime；性能无影响 | 0（盲区见三-1，属观察） |
| L-c FBA_NO_BROWSER 关闭打包版迁移 | 已修。frozen + NO_BROWSER 会迁移示例旧数据；pytest 或设了 FBA_APP_DATA_DIR 时仍不迁移 | 0 |
| N1 发票：只差大小写的两个 SKU 互相覆盖 | 已修。复现用例两行各自正确；全仓静态检查没有残留的 SKU upper/lower/casefold 键 | 0 |
| N2 S9-B 同一次促销小幅变价后提示消失 | 已修。16→15.5→17 提示保留；边界全对；申报价规则（D-12）不变 | 0 |
| N3 PATCH / Excel 同步冲突返回 409 | 已修 | 0 |
| N4 测试缺口（W1 / C7 / C8 / W3） | 已补，4 个变异全部被杀 | 0 |
| UI：「无变化」组折叠、错误 toast 不消失 | 已修 | 0 |
| **N5 listing / 箱规导入遇到大小写冲突：预览不提示，写入只写了一半** | 新发现（以前的探针表头写错，没测到） | **−0.2** |
| N6 确认成功后成功 toast 不出现 | fix3 新引入 | −0.1 |
| N7 测试缺口：护栏 3 处、90 天“正好等于” | 变异存活 | −0.1 |
| N8 决策文档措辞 | D-19 的授权标注与要求不一致；D-15 修订里“本次有效的领星常规价”比代码窄 | −0.1 |
| D-01..D-18 字节一致、D-15 原文只追加、D-19 示例模板、spec 排除、新 app_data 不混入示例行、升级用户主库不变、迁移矩阵、确认接口、422 行号、截图 | — | 通过 |
| 回归、密钥、脱敏、git 卫生 | — | 通过 |
| **合计** | | **−0.5 → 99.5** |

### 能否开始 V3.2 打包

**代码层面可以开始（fix3 达标）；但现在还不能直接打包发布，必须先处理随包模板里的真实数据（P-1）。** 前提：

1. **P-1（必须）：处理四节「打包前必须处理」清单里的文件。**
   - 这些文件含真实店铺数据，交叉比对与真实产品表一致：
     - `backend/templates/` 下 18 个文件；
     - `backend/config/` 下 4 个出厂默认 json。
   - spec 目前把它们全部打进 exe；其中 config 默认文件首次启动时还会复制进每个新用户的 app_data。
   - 处理方式建议（用户二选一，两 Bot 推荐 b）：
     - a. spec 只打白名单模板，排除清单里的文件，原文件留在仓库供测试和 golden 使用；
     - b. 在 a 的基础上，把运行时确实需要的那几个文件（`customs/报关资料模板.xlsx`、`invoice_template_map.json`、三个 sku / fnsku / metadata 默认 json）换成 DEMO 值的出厂版。测试继续读仓库里的原件，或改读 fixtures。
   - 再加一条打包测试：对 spec 收集到的全部 datas 扫 `B0…` / `X00…` / `FBA1…` 和真实 SKU 清单，命中即失败。
2. N5 建议打包前修（几行改动）：listing / 箱规导入先整体检查冲突，预览标出冲突行，写入要么全不写，要么跳过冲突行并在 skipped 里列出来。如果不修，要写进已知问题。
3. N6–N8 可以随包修，也可以留到下个版本。
4. 版本号统一改 V3.2（前端、后端、spec、HANDOFF），从 tag 的干净 checkout 打包。
5. 测试目录里那份真实产品信息表（`backend/tests/fixtures/product-info/<内部产品信息表>.xlsx`，16.6 MB，被跟踪）已确认不在 spec 里；`archive/private_data/产品信息表.csv` 也不在。是否停止跟踪由用户决定。

**打包后的交付物复核清单**（下一轮执行）：
- zip 的修改时间晚于对应提交时间（ET）；
- 解包后逐项确认没有：`.git`、`*.db`、`sessions/`、`lingxing.json`、`*.key`、`.env`、`app_data/`、含真实 SKU 的截图；
- `_internal\templates\` 里只有 `产品信息表_示例.csv`，没有 `产品信息表.csv`，也没有四节清单 A 里的任何文件；
- 对整个 `_internal\` 的文本、xlsx、pdf 扫 `B0…` / `X00…` / `FBA1…` 和真实 SKU 清单：0 命中（只输出计数）；
- 新 app_data 首次启动：`product_master` 0 行（不混入示例行），`config\` 里的默认 json 不含真实值；
- exe 只监听 127.0.0.1（`run_app.py:68`、`launcher_fastapi.py:45/64`）；
- 迁移，用示例旧数据：
  - frozen 加 FBA_NO_BROWSER=1 首次启动：搬进 app_data；
  - 二次启动不覆盖；
  - lingxing.json 不搬；
  - 设 FBA_APP_DATA_DIR 时不迁移；
- 升级用户：已有 app_data（示例主库加用户自己的 `templates\产品信息表.csv`）。启动后主库行数不变，仍用用户自己的表，不用示例表；
- 新包打开旧 schema 示例库，origin 为 legacy，regular_price_at 补成迁移时间；旧 V3.1 exe 再打开升级后的库，可正常读写；
- S9-B：在 1280 / 420 宽度下，「无变化」组有提示时默认展开；确认失败后再确认成功，错误 toast 消失（N6 修好后还应出现成功 toast）。

---

## 二、新缺陷

1. **N5 listing / 箱规导入遇到大小写冲突：预览不提示，写入只写了一半（轻微，−0.2）【step3 起就有，本轮第一次测到】**
   - 位置：
     - `backend/fba_tool/product_import.py` 的 `_diff`（约 L121）用 `get_products_by_skus` 查不到冲突 SKU，就当成「new」；
     - `_apply`（约 L171–180）逐个 SKU 调 `set_product_fields`，遇到冲突抛 SkuCaseConflict，中断循环；
     - 路由 `routers/master_data.py:308/338` 把这个异常转成 422。
   - 实测（`probe\t_f3.py`，产品库里已有 `DEMO-K1` 和 `demo-k1`，导入第三种写法 `Demo-K1`）：

     | 入口 | 预览 | 写入 | 实际写入了什么 |
     |---|---|---|---|
     | listing（MSKU 表头），冲突行在第 1 行 | 200，冲突行显示为「new」，没有错误 | 422「无法确定是哪一条」 | 什么都没写 |
     | listing，冲突行在中间 | 200，同上 | 422 | **冲突行之前的 DEMO-OK1 已写入，之后的 DEMO-OK2 没写** |
     | 箱规导入，冲突行在中间 | 200，同上 | 422 | **之前的 DEMO-CA1 已写入，之后的 DEMO-CA2 没写** |
     | 编辑导入（产品主数据表） | 冲突行列进 errors | 200，只写合法行 | 正确 ✓ |
     | 定时同步 | — | 跳过冲突行，记 sku_case_conflict | 正确 ✓ |
     | 手动同步确认 | — | 冲突行不写 | 正确 ✓ |
     | 票级导入 | 键是 FBA 号，不涉及 SKU | — | 不适用 |

   - 影响：冲突的那一条不会写错行，所以数据没有串。但 422 让用户以为整个文件都没写入，实际前面的行已经写了。预览也看不出问题。只在库里已经有大小写重复的旧数据时才会出现。
   - 修法：照编辑导入的做法，在 `_diff` 里先用 `resolve_stored_sku` 检查冲突，把冲突行列进 errors（带行号），写入时跳过这些行并在 `skipped` 里列出来。补 listing 和箱规两条测试。

2. **N6 确认成功后成功 toast 不出现（轻微，−0.1）【fix3 引入】**
   - 位置：`frontend/src/components/lingxing-preview-panel.tsx:130-131`，先 `toast.dismiss(toastId)`，紧接着用同一个 id 调 `toast.success`。
   - 实测（Edge 无头，示例 SKU）：
     - 先填 `abc` 再确认，出现错误 toast ✓；
     - 再填 15.50 确认，每 0.25 秒查一次，3 秒内都没有出现任何 toast；
     - 后端审计日志写了 2 条，提示也消失了，说明确认本身是成功的。
     - 第一次确认、之前没有错误 toast 时，同样没出现成功 toast。
   - 要求「确认后清掉错误 toast」做到了，但成功反馈也一起没了。
   - 修法：去掉 `toast.dismiss(toastId)`，只用同一个 id 调 `toast.success`，sonner 会原地把错误 toast 替换掉；或者成功 toast 改用另一个 id。

3. **N7 测试缺口（轻微，−0.1）**：下面 4 个源码变异存活，见五：
   - GR8：护栏不再把仓库根 `app_data/` 当真实来源。所有护栏测试的项目根都是 `tmp_path/"noroot"`，没有覆盖这个目录，而开发模式下真实数据主要就在这里。
   - GR5：缓存忽略文件变化。只测了“没变不重读”，没测“变了要重查”。
   - GR9：pytest_sessionfinish 不扫 basetemp。
   - W1c：`<=` 改成 `<`。`test_window_exact_90_days_is_inside` 留了 2 秒余量，实际测的是“差 2 秒到 90 天”，不是“正好 90 天”。
   - 修法：
     - 给 real_sources 补一条测试，让项目根下有 `app_data/fba_master.db` 和 sessions；
     - 缓存测试补“改内容并改 mtime 后会重查”；
     - 90 天边界用固定的 now，或 monkeypatch `_now`，测正好等于 90 天的情况。

4. **N8 决策文档措辞（轻微，−0.1）**
   - D-19 写的是「用户授权两 Bot 选定 2026-10-17，用户可推翻」。复测要求的标注是「授权由开发方 Bot 转述，用户可推翻」，D-16 用的就是这个写法。现在的写法把转述写成了用户直接授权，建议改成与 D-16 一致。
   - D-15 修订写「升为 confirmed 的参照只能是……本次有效的领星常规价」。代码（`product_fields.py` `_track_nonpromo` → `_recent_regular`）在本次没给常规价时，也会用库里已有的、90 天内有效的常规价当参照。实际行为合理，但文字比代码窄，建议改成「有效的领星常规价（本次给的，或库里 90 天内采集的）」。
   - 其余措辞准确：修订标了「两 Bot 修订，用户可推翻」；D-12 / D-13 不变；“售价变化本身不算参照”和代码一致（16→20 仍是 self_first，见三-3）。

---

## 三、逐项复核

### 1. 护栏 realdata_guard【fix3】

实验 `tools\exp_f3.py`，用哨兵造的“真实来源”：带 product_master 的 SQLite 库、两个会话文件，另有一个 WAL 模式、有未检查点数据的 app_data 库。直接调用 `RealDataIndex` / `find_real_copies`。

| 复制方式 | fix2（上轮） | fix3 |
|---|---|---|
| copy2 同名 db | ✓ | ✓ |
| copy2 改名 db | ✗ | ✓ |
| copy2 到 config/backup.sqlite | ✗ | ✓ |
| copyfile 同名 db（不保留 mtime） | ✗ | ✓ |
| copyfile 同名 sessions | ✗ | ✓ |
| copy2 改名放进 sessions | ✓ | ✓ |
| copyfile 改名放进 sessions | ✗ | ✓ |
| copy2 会话放到 sessions 以外 | ✗ | ✓ |
| copy2 后被 init 改写（加表、加列） | ✗ | ✓（按表特征） |
| 附加：改 1 字节的库（数据页） | — | ✓ |
| 附加：VACUUM INTO 出来的库 | — | ✓ |
| 附加：journal 模式下的库副本 | — | ✓ |
| 附加：WAL 主库副本，单独复制或连同 -wal | — | ✓ |
| 对照组：测试自建的库（同名 SKU）、同大小但内容不同的会话 | — | 不误报 ✓ |

- 输出只有临时目录里的相对路径和原因。逐条检查过，不含来源路径、哈希、SKU 或 ASIN；开发方测试和变异 GR6 / GR7 也覆盖了这一点。
- 只读：
  - 真实来源先 stat，再全部扫描、再 stat，mtime 和大小不变；
  - SQLite 用 `mode=ro&immutable=1` 打开，被测库旁没有生成 `-wal` / `-shm`；
  - 原仓库真实数据的快照前后 0 差异（含 mtime，见六）。
- 性能：
  - 3000 个小文件加一个 50 MB 文件的目录，第一次扫描 0.17 秒，第二次（走缓存）0.10 秒；
  - 全量 pytest 用时 100 秒，与上轮持平；
  - 用真实来源（20 个文件，只在内存）对本轮新建的 141 个 %TEMP% 目录做内容扫描，约 20 秒，真实副本 0 个。
- **盲区（观察，不扣分；超出“复制”的范畴）**：
  - SQLite 文件头被改坏的库；
  - 会话文件内容被改或被重新序列化；
  - 只复制 `-wal` 文件；
  - 复制后把所有行的 updated_at 改掉；
  - 导出成 CSV。

  这 5 种都拦不住。前 3 种在测试代码里不会自然发生。
- conftest：会话开始时建一次索引，之后每个测试都检查全局临时 app_data 和该测试的 tmp_path，会话结束时再扫 basetemp。smoke 也加了同样的检查。

### 2. SKU 键【fix3】

- N1 复现（`t_f3.py::test_invoice_collision_repro`）：键是 `DEMO-K2` 和 `demo-k2` 两个；甲品名 / 1111111111 和乙品名 / 2222222222 各归各的 ✓。
- 开发方的测试另外覆盖了：
  - CSV meta、workflow bundle、编辑行匹配、Step1 重量、产品目录；
  - 同票冲突的提示：「本票里有只差大小写…没有合并」。
- 静态检查：在 `backend` 和 `scripts` 的非测试代码里 grep `.upper()` / `.lower()` / `casefold`，共 174 处，逐条看过：
  - 剩下的都是 FNSKU（亚马逊规定大写）、FBA 号或箱号、单元格坐标、币种、扩展名、表头、品类等；
  - 没有拿 SKU 当键的；
  - casefold 只在 `sku_keys.sku_key` 和表头清洗里出现。
  - 前端只有搜索过滤用了 `toLowerCase`，不影响写入。
- 冲突 409：
  - PATCH 冲突返回 409，查不到返回 404；
  - local-excel/sync 冲突返回 409，并且整批都不写；
  - 确认接口冲突返回 409（沿用上一版）；
  - 变异 K7 / K8 / C6 都被杀。
- 其余写入口见二-1（N5）。

### 3. D-15 修订：self_first 不当升级参照【fix3】

探针 `t_f3.py::test_d15_*`（示例 SKU，mock 同步）：

| 场景 | origin | 提示 | 申报价 |
|---|---|---|---|
| 16 → 15.5 → 17 | self_first | 有 ✓ | 17（按售价） |
| 16 → 15.2（正好 −5%） | self_first | 有 | 15.2，不算促销（`>=`）✓ |
| 16 → 15.19（略低于 −5%） | self_first | 有 | 16，按非促销记录 ✓ |
| 16 → 15.2 → 14.44（连续两次 −5%） | self_first | 有 | 14.44（D-12 原规则：记录随之下移，与修订前一致） |
| 16 → 20（涨价） | self_first | 有 | 20。售价变化不算参照，与文字一致 |
| 16 → 12 → 16 | self_first | 有 | 16 |
| 16 → 15.5，这次给了有效常规价 16.9 | self_first | 无（有有效常规价） | 16.9 常规价 ✓ |
| 常规价等于或低于售价（没有信息量） | self_first | 有 ✓ | 售价 |
| 参照为 confirmed / legacy，10 天前 | → confirmed | 无 ✓ | — |
| 参照为 confirmed / legacy，91 天前（出了窗口） | self_first | 有 ✓ | — |
| 参照为 self_first，10 天前 | self_first | 有 ✓ | — |

- 被改写的旧测试：
  - `test_later_sync_with_reference_confirms`：先把记录改成 legacy，再断言升为 confirmed、无提示、无差异，断言没有放松；原来那条“self_first 当参照”的路径改成新测试 `test_later_sync_self_first_only_reference_stays_self_first`，断言更严。
  - `test_no_browser_counts_as_test_env` 改名为 `test_pytest_blocks_even_with_no_browser_and_switch`，断言照旧，因为 pytest 本身就是测试环境；NO_BROWSER 不再挡迁移，有新测试覆盖。
  - `test_guard_flags_old_files_and_ignores_fresh` 删了 mtime 规则，换成“只有旧 mtime、内容不同的文件不误报”。这是规则本身变了，不算放松。
- 决策文档（`tools\dec_chk.py`，按 `## D-` 切段比对）：
  - D-01..D-14 与 e3d3908 逐字节相同；D-16、D-17 也相同；
  - D-18 只在段末多了与 D-19 之间的空行；
  - 全文 diff 只有 15 行新增，没有删除；
  - D-15 新文本以旧原文开头，修订是追加的（474 字符）；
  - 文件仍是 LF。

### 4. 小项

- **NO_BROWSER 迁移矩阵**（`exp_f3.py`，子进程，模拟 frozen，exe 旁放示例旧库、sessions、user_settings、假的 lingxing.json）：

  | 场景 | 决定 | 示例库 / 会话 |
  |---|---|---|
  | frozen 默认 | 迁移（frozen） | 搬了 ✓ |
  | frozen + NO_BROWSER=1 | **迁移** ✓（上轮不迁移） | 搬了 |
  | frozen + NO_BROWSER + ALLOW=0 | 不迁移（explicit_off） | 没搬 |
  | frozen + FBA_APP_DATA_DIR（另加 ALLOW=1 + NO_BROWSER） | 不迁移 | 没搬 ✓ |
  | frozen + PYTEST_CURRENT_TEST + NO_BROWSER | 不迁移（test_env） | 没搬 ✓ |
  | 开发模式 + FBA_APP_DATA_DIR（加 NO_BROWSER 或 ALLOW） | 不迁移 | 没搬 ✓ |

  所有场景都不搬 lingxing.json，与上一版相同。
- 90 天窗口的分钟级边界：
  - 有 ±1 分钟和 ±5 分钟的测试，变异 W1 / W1b 被杀；
  - “正好 90 天”没有真正测到，W1c 存活，见 N7。
- 审计截断（C7 / C8）：已有测试，变异被杀 ✓。
- 422 带行号：listing、箱规、编辑三种导入的全坏行都返回 422，并带「第 2、3 行」和 errors 列表。变异 E1 和运行时 n2_import_no_rows 都被杀（后者用上轮的测试集时存活，原因是那个测试集里没有 fix3 的测试文件）。
- UI：
  - 「无变化」组里有提示时默认展开，标题显示「· ⚠ 1 个需人工确认正常价」，组里的提示可见 ✓；
  - 没有提示的组仍然折叠；
  - 确认后之前的错误 toast 会消失 ✓（成功 toast 的问题见 N6）。

### 5. D-19 示例模板【fix3】

- `产品信息表_示例.csv`：
  - 3 行，1 行表头加 2 行数据，12 列；
  - 列名：二级产品线、产品名称、SKU、ASIN、FNSKU、中文名称、报关名、海关编码、材质、成本、包装尺寸、装箱明细；
  - 每行都含 DEMO。ASIN 形态 2 处、SKU 形态 2 处，全部带 DEMO；FNSKU 形态 0 处，链接 0 处；
  - 与真实产品表交叉比对 0 命中 ✓。
- spec：
  - `_bundled_templates_datas` 逐个列出模板，排除文件名含「产品信息表」但不含「示例」的文件；
  - config 仍然排除 sessions、lingxing.json、invoice_history；
  - spec 只收 `backend/dist`、`backend/config`、`backend/templates` 加依赖包。`archive/`、`backend/tests/fixtures/`（含那份 16.6 MB 的内部产品信息表）都不在里面 ✓；
  - 变异 D3 被杀。
- 新 app_data：
  - 截图服务首次启动后，`templates\` 里只有 `产品信息表_示例.csv`；
  - `product_master` 只有截图种子写的 5 条 DEMO-UI 行，没有混入示例表的行 ✓；
  - `find_catalog_path` 跳过「示例」，变异 D2 被杀。
- 升级用户（`t_f3.py::test_d19_*`）：
  - 主库已有 1 条用户数据，且没有真实表：catalog_seed 扫描 0 条，写入 0 条，主库不变 ✓；
  - 用户自己的 `templates\产品信息表.csv` 在场：读用户的表（不读示例表），只补空字段，写入 1 条用户自己的行 ✓；
  - 用户从旧版 exe 升级时迁移自己的 templates 不受 skip 影响，符合 D-19 的说明。

---

## 四、模板盘点：「打包前必须处理」清单

方法（`tools\tpl_inv.py`、`xmatch.py`、`skumatch.py`、`cfg_inv.py`，只输出计数）：
- 对 `backend/templates/**` 和 `backend/config/*.json` 读出文本，统计这几种值模式：ASIN（`B0` 加 8 位）、FNSKU（`X00` 加 7 位）、FBA 货件号、FBA 箱号（货件号加 `U` 和 6 位）、SKU 形态；
- 和真实产品表（`archive/private_data/产品信息表.csv`，加测试目录那份内部表）的 ASIN、FNSKU、SKU 清单做交叉比对；
- 再和 golden 样本里的货件号比对。

这些文件全部被跟踪，spec 目前全部打包。

**A. 含真实数据，必须处理：**

| 文件 | 内容形态（只计数） | 运行时是否用到 |
|---|---|---|
| `亚马逊FBA表.csv`、`亚马逊FBA表1–5.csv`（6 个） | 每个文件：ASIN + FNSKU 共 12 个，**全部在真实产品表里**；真实 SKU 12 处；真实 FBA 货件号 1 个、箱号 23–28 个；品牌名（脱敏扫描「产品目录/模板」类，7 个文件共 37 处） | 测试和 golden 读仓库里的原件；生产代码只在 1 处按文件名关键字查找 |
| `J-US-第四批第N票…发票.xlsx`（5 个，每个约 9.5 MB，**文件名本身带品名**） | 真实 ASIN / FNSKU 6 个、真实 SKU、FBA 货件号 1–6 个 | 只在测试里用 |
| `箱唛1–5-*.pdf`（5 个） | 真实 FBA 箱号 23–28 个 | 只作参考 |
| `发货录入样表.xlsx` | 真实 ASIN / FNSKU 6 个、真实 SKU | 生产代码 4 处引用 |
| `已填写好的send to amazong.xlsx` | 真实 ASIN / FNSKU 8 个、真实 SKU | 没有代码引用 |
| `customs/报关资料模板.xlsx` | 真实 FBA 货件号 5 个（golden 里也有） | **运行时模板**，要换成 DEMO 值 |
| `config/amazon_sku_metadata.default.json` | 真实 ASIN / FNSKU 12 个、真实 SKU、品牌名 | **出厂默认，首次启动复制进用户 config** |
| `config/fnsku_mapping.default.json` | 真实 FNSKU 6 个、真实 SKU | 同上 |
| `config/sku_mapping.default.json` | 真实 SKU 12 处 | 同上 |
| `config/invoice_template_map.json` | FBA 货件号 6 个（4 个在 golden 里） | 运行时配置 |

另外，`backend/fba_tool/product_catalog.py` 源码里有 1 处真实品牌字样（脱敏扫描「产品目录/模板」类计在里面），会随代码打包，建议换成通用写法。

**B. 要人工看一眼**（只有 SKU 形态命中，与真实清单交叉比对 0 命中，可能是货代自己的渠道码或仓库码）：
- `forwarders/deshu_t3.xlsx`（67 处）；
- `forwarders/qiluo_t6.xlsx`（98 处）；
- `工厂表.xlsx`（130 处）。

**C. 没发现真实值形态，可以照常打包**：
- `forwarders/jiufang.xlsx`、`qiluo.xlsx`、`qiluo_t5.xlsx`、`send.xlsx`；
- `内部留档表.xlsx`、`箱规导入模板.xlsx`、`货代表.xlsx`、`Send to Amazon表格.xlsx`；
- `README.txt`、`产品信息表_示例.csv`。

**测试目录（登记，不随包）：**
- `backend/tests/fixtures/product-info/<内部产品信息表>.xlsx`（16.6 MB，被跟踪；ASIN 形态 51 处、FNSKU 形态 31 处，是真实值）；
- `archive/private_data/产品信息表.csv`（被跟踪，ASIN 3、FNSKU 3、MSKU 6、品名 3）。

两者都不在 spec 里 ✓。是否停止跟踪由用户决定。

**建议处理方式**：见一节 P-1。spec 改成白名单，并加一条打包测试扫 datas。测试继续用仓库里的原件，不要移动这些文件，否则 golden 和测试会断。

---

## 五、测试质量（变异）

- **源码变异 70 个**：`tools\mutsrc4.py`，在 repo_mut 上跑，每个跑完立即还原；结果在 `out\mut_src4_live.out`。**64 个被杀，6 个存活**：
  - 新增的 fix3 变异 31 个，27 个被杀：
    - F1–F4：self_first 参照、常规价参照、可信记录参照、D-12 不变；
    - NB1：NO_BROWSER 重新算测试环境；
    - GR1–GR4、GR6、GR7、GR10、GR11：护栏的哈希、表特征、大小粗筛、输出不泄漏、文件头、小库；
    - K1–K10：7 个模块的原样键、匹配、409、catalog_seed 冲突；
    - D1–D3：示例模板 / 真实表排除；
    - E1：422 行号；
    - 存活 4 个：W1c、GR5、GR8、GR9。
  - 上轮的变异按 fix3 代码重定位后重跑：
    - S1–S7、O1–O4、W1/W1b/W2–W4、M1–M2、C1–C8、G1–G5、G9、G10、N2v3、A1–A6、R1，共 39 个，37 个被杀，**上轮存活的 W1、C7、C8、W3 这次全部被杀**；
    - 存活 2 个：S5、G9，与上轮相同，是等价变异。
  - 存活的 GR5、GR8、GR9、W1c 计入 N7。
- **运行时变异**（`mut6.ps1` old / new，插件与上轮相同）：
  - old：45 个，43 个被杀，与上轮完全相同。m4_no_auth_codes 和 m4_429_fatal 目标已过时，上轮已用源码变异替代；
  - new（MUT5）：被杀 7 个，与上轮相同；
  - 8 个目标已过时，由源码变异 A1–A6、R1、N2v3 替代，全部被杀；
  - n2_no_catch_parse 存活，与上轮相同，是等价的兜底；
  - n2_import_no_rows 用旧测试集时存活，加上 fix3 的测试文件后被杀（3 条 422 测试失败）。

---

## 六、回归与交付物

| 项 | e3d3908【fix2，上轮】 | 8221d92【fix3】 |
|---|---|---|
| pytest 正序 | 1030 | **1090 passed**（100 秒） |
| 先跑 step3/4/fix 相关文件 | 340 | 341 |
| 逆序 / 随机（seed 20261017） | 1030 / 1030 | **1090 / 1090** |
| golden | 82 | 82 passed（分类计数在 `out\golden_tally.json`） |
| tsc | 0 | 0 |
| vite build | 通过 | 通过 |
| 冒烟 `--real-app-data=<原仓库 app_data 绝对路径>` | 19/19 | **20/20**：新增“临时目录里没有真实库 / 会话副本（按内容比对）”；真实 app_data 哈希不变 |

- 开发方自报的数字（1090 ×3、golden 0 失败、smoke 20/20、tsc 0）与本轮重跑结果一致。开发方提交后只改了文档、没有重跑全量，本轮已经补跑。
- 密钥扫描（4 个模式加通用模式）：
  - 8221d92 树里有 7 处命中，全在 `frontend/bun.lock` 和 `package-lock.json`，是依赖包的 integrity 哈希，误报，与上轮相同；
  - `git log -p e3d3908..8221d92` 命中 0 ✓。
- 脱敏扫描：与 e3d3908 逐类比较：
  - golden 样本：ASIN 8、FNSKU 10、MSKU 24、品牌 131，不变；
  - 业务配置：品牌 8，不变；
  - 其他：ASIN、FNSKU、MSKU 各 10，品牌 31，不变；
  - 测试代码：MSKU 2，不变；
  - 「产品目录/模板」类：ASIN 3、FNSKU 3、MSKU 6、品名 3、品牌 37，计数不变，但真实表现在在 `archive/private_data/`，不在 `backend/templates/`；
  - 「评审/文档」和「源码」两类仍是 0。fix3 提交的上轮报告没有新增命中。
  - 没有新增 ✓。
- git 卫生：原仓库 HEAD 8221d92，工作区干净（本报告是唯一新增的文件）。
- **真实数据快照**：原仓库 `app_data\`（57 个文件）、`backend\fba_master.db`、`backend\config\sessions\` 共 58 个文件，评审前后大小、mtime、SHA-256 **0 差异，0 新增，0 缺失**。原仓库 backend 下没有生成 `-wal` / `-shm`。
- %TEMP% 内容扫描：
  - 本轮（13:30 以后）新建的 141 个顶层临时目录、本评审目录的全部子目录，真实副本都是 0 个；
  - 146 个旧副本目录只读，没有动过。

### 截图【fix3，用 repo 构建】

- 环境：临时 app_data 加示例 SKU（DEMO-UI-*），mock 领星，假 Key；Edge 无头 + CDP，用 guest 模式；只连本机临时后端 `127.0.0.1:8765`。
- 位置：PC 上 `%TEMP%\fba_review_s9s4fix3\shots\`，box 上 `/workspace/fba_s9s4fix3_*.png`，共 13 张：
  - `1280` / `900` / `600` / `420` 和对应的 `*_top`；
  - `unchanged_group`：「无变化」组默认展开，带提示数；
  - `hint`：S9-B 提示特写；
  - `confirm_bad`：填 12,5，提示无效原因；
  - `confirm_done`：填 18.50 确认后，提示消失，错误 toast 已清掉；
  - `after_reload`：刷新后仍保持。
- 各宽度下提示都不溢出，提示框在面板内。页面整体最小宽度约 1077 px 是外壳的问题，属观察，与上轮相同。

---

## 七、未测

- 真实的 V3.2 exe：还没打包。frozen 只用 `sys.frozen` / `_MEIPASS` 模拟过。
- 真实领星接口：按要求不连。
- 护栏放在原仓库里、用真实来源跑全量 pytest 时的耗时：不在原仓库跑测试。只在评审副本里测了性能，并用真实来源在内存里扫了 %TEMP%，约 20 秒。
- 非无头浏览器、触屏、深色模式下的 UI。
- B 类 3 个模板的值是什么：只做了模式计数，要人工看。
- `tests/fixtures/product-info` 是否停止跟踪、历史是否改写：由用户决定，没有动。

---

## 八、探针位置（都在 `%TEMP%\fba_review_s9s4fix3\`）

- `tools\exp_f3.py`：护栏 9 种加附加复制方式、性能、只读检查、迁移矩阵。输出在 `out\exp_f3b.out`。
- `probe\t_f3.py`：冲突写入口、N1 复现、D-15 边界、D-19 升级用户。复制到 repo_mut 里跑，跑完删掉。输出在 `out\probe_f3.out`、`out\probe_f3_d19.out`。
- `tools\mutsrc4.py`（变异清单在 `tools\mlist.py`），结果在 `out\mut_src4_live.out`；`mut6.ps1` 的结果在 `out\mut_live_old.out` / `mut_live_new.out`。
- `tools\tpl_inv.py`、`xmatch.py`、`skumatch.py`、`cfg_inv.py`、`ex_chk.py`：模板盘点，只输出计数。
- `tools\dec_chk.py`：决策文档逐段比对。
- `tools\shot3.py`、`toast_probe.py`、`ui_seed.py`：截图和 toast 检查。
- `regress.ps1`：全量回归，输出在 `out\`。快照在 `snap_before.csv` / `snap_after.csv`。
- 注意：`edge_prof\` 是第一次截图尝试的 Edge 配置目录，Edge 自动登录了本机的 Microsoft 账户。那次的截图已被第二次（guest 模式）同名覆盖，box 上的副本已删。这个配置目录可能含登录信息，建议用户自行删除。我们按规则没有删除任何东西。

---

## 九、修复清单（按优先级）

1. **P-1（打包前必须）**：处理四节 A 类文件。
   - spec 改成白名单；运行时需要的文件换成 DEMO 出厂版；
   - 加打包 datas 扫描测试；
   - `product_catalog.py` 里的品牌字样换成通用写法；
   - B 类 3 个文件人工确认。
2. N5（建议打包前）：listing / 箱规导入在 `_diff` 里先检查冲突，预览标出冲突行，写入跳过冲突行并列进 skipped；补测试。
3. N6：去掉 `toast.dismiss(toastId)`，同 id 直接 `toast.success`。
4. N7：补 real_sources 覆盖项目根 `app_data/` 的测试、缓存“变了要重查”的测试，以及固定时间下正好 90 天的测试。
5. N8：D-19 的授权标注改成「授权由开发方 Bot 转述，用户可推翻」；D-15 修订里的常规价措辞放宽到与代码一致。
6. 版本号改 V3.2，从 tag 干净 checkout 打包，然后按一节的交付物清单复核。
