# S9-step3 / step4 / step4-fix1 / step4-fix2 独立复测报告

- 被测提交：`db66207`（s9-step3）、`da14cf6`（s9-step4）、`17b2995`（s9-step4-fix1）、`e3d3908`（s9-step4-fix2，**主测对象**）。基线 `9793488`（s9-step2-fix2，上轮 v3 报告 99.1 通过）
- 评审时间：2026-10-17 11:21–12:25（美东时间 ET）。11:40 ET 接到新 tag s9-step4-fix2，主测对象从 fix1 改为 fix2。fix1 上已经做完的结果保留，每条都标明出自哪个版本（【fix1】/【fix2】/【step3 起】等）
- 方式：只读复测。副本在 `%TEMP%\fba_review_s9s4\`：`repo`（17b2995）、`repo_fix2`（e3d3908）、`repo_mut`（e3d3908，变异专用）、`repo_sentinel` / `repo_sentinel2`（哨兵实验）、`exe_sent`（V3.1 便携版副本）。每次运行都单独设 FBA_APP_DATA_DIR，FBA_NO_BROWSER=1；领星全部用 mock，假 Key（`lxFAKE-TESTONLY-000` / 测试自带假 Key），没有调用真实领星接口
- 没碰 `%TEMP%\fba_s1`，没读开发方截图和开发方的副本清单。node_modules 用 robocopy 只读复制一份（`repo\frontend\node_modules`），`repo_fix2` 用联接指向这份副本；没有递归删除任何东西，也没删除任何文件
- 原仓库只新增本报告，没 add，没 commit。真实数据快照前后 0 差异（见六）
- 脱敏：本报告不写任何真实 store_id、sid、ASIN、MSKU、FNSKU、店铺名、品牌名或品名，只写「文件:行号 + 类型」、文件名、大小、时间，或 DEMO 示例值

---

## 〇、真实数据泄漏调查（优先级 1）

### 0-1 结论

1. **泄漏属实，根因在代码，不在评审操作**【step3 / step4 / fix1 都有；从基线 8404f4b 起就存在】。`backend/fba_tool/app_paths.py:201-209` 的 `ensure_app_data_layout()` 无条件调用 `_migrate_legacy_data()`（`app_paths.py:154-180`）。开发模式（`sys.frozen` 为假）下，迁移来源是仓库根和 `backend/`，**设了 FBA_APP_DATA_DIR 也照样迁移**。所以 pytest（`conftest.py:17-21` 的会话 fixture）、smoke（`scripts/smoke_e2e.py:103`）、`main.create_app()`（`main.py:160`）每次新建临时 app_data 时，都会把仓库里的真实库和会话复制进去。
2. 迁移内容（`app_paths.py:168-180`）：
   - `fba_master.db`（缺失时整份复制）
   - `config/sessions/` 全部文件（逐个补缺）
   - `templates/`
   - `invoice_history.json`
   - 9 个用户配置 json（user_settings / formulas / product_catalog / sku_mapping / fnsku_mapping / amazon_sku_metadata / invoice_mapping / forwarders / forwarder_mapping）

   它只看代码自身的相对根目录，不写死原仓库路径。原仓库里实际存在、会被复制的真实来源只有两类：
   - `backend/fba_master.db`：20480 B，未跟踪，单表 `product_master`
   - `backend/config/sessions/`：4 个文件，未跟踪
3. **复制的是业务数据，不是领星凭据。** 只看键名、不看值：
   - sessions 的键名都是装箱 / 发票任务数据，例如 box_editor_df、input_df、fnsku_overrides、invoice_template_bytes、step4_*、react_*、task_id 等，没有 key / token / cookie / secret / auth 类字段。
   - 库里没有敏感命名的列。
   - 领星密钥在 `app_data/config/lingxing.json`，不在迁移名单里（`app_paths.py:16-26` 的名单不含它）。
   - 实验核实：打包模式下 exe 旁放一个示例 `config/lingxing.json`，迁移后的 app_data 里没有它。
4. **违反了「测试不碰真实数据」**：测试和冒烟的临时目录里有真实 SKU / ASIN / FNSKU 和装箱会话。**不违反「领星一律 mock」**：没有凭据被复制，也没有发生真实调用。
5. **定级：中等，必须修（−1）。【fix2 已修好，本轮不再扣分】** fix2 的 `legacy_migration_decision()`（`app_paths.py`，e3d3908）实测按矩阵工作正常（见 0-4）。修复后全套回归新建了 86 个临时目录，其中真实副本 0 个。唯一带哨兵的目录 `fba_test_app_data_ap2_klju`（11:49:54 ET）是我们的变异 G5 故意制造的，里面是假的哨兵数据，而且被护栏在会话初始化时拦下了。

### 0-2 副本清单（只按元数据和哈希判断，没移动，没删除）

扫描范围：`%TEMP%` 下 1133 个顶层目录，排除 `fba_s1` 和 node_modules。共有 **146 个顶层目录、611 个文件**与真实来源的 SHA-256 完全一致：

| 位置 | 目录数 | 一致的文件数 | 创建时间（ET） | 说明 |
|---|---|---|---|---|
| `%TEMP%\fba_test_app_data_*` | 141 | 564 | 10-16 05:49 ～ 10-17 11:06 | pytest 会话的临时 app_data。每个都有 sessions 4 件，少数还有整份库 |
| `%TEMP%\pytest-of-huang\pytest-414/415/430/431/432\…` | 1（顶层） | 22 | 子目录与开发方提交时间吻合 | 涉及 test_import_apply_writes_good…、test_first_run_seeds_app_data、test_e2e_manual_regular_price 等 tmp_path |
| `%TEMP%\fba_smoke_vymblssq` | 1 | 4 | 10-16 11:27 | 冒烟用 --keep 留下的目录 |
| `%TEMP%\fbasrc` | 1 | 11（另有 11 件与真实 app_data 会话一致，共 22） | 10-16 04:18 | 整个项目目录的快照（无 .git），含 `app_data\sessions\`、`backend\config\sessions\`、`_internal\config\sessions\`；没有 .db |
| `%TEMP%\fbasrc2` | 1 | 7（加上与 app_data 会话一致的共 18） | 10-16 04:22 | 同上，没有 .db |
| `%TEMP%\fba_s1_verify` | 1 | 3（加上与 app_data 会话一致的共 14） | 10-16 05:20 | 带 .git 的核对仓库。`app_data\fba_master.db` 2277376 B，与真实 app_data 库同大小、哈希不同（之后被改过），并有 app_data sessions 14 件 |

完整的逐目录清单（路径、文件数、DB 数、会话数、创建时间）在 `%TEMP%\fba_review_s9s4\out\copies_list.csv`，逐文件清单在 `out\temp_scan.csv`。

**另有 3 个疑似真实 app_data 库副本**。大小和真实 app_data 库接近，哈希不同，可能是迁移后改过，也可能是别的库，判断不了：
- `%TEMP%\fba_s2v2_mig_v0\fba_master.db`（10-16 08:06）
- `%TEMP%\fba_s2v2_mig_v2\fba_master.db`（10-16 08:06）
- `%TEMP%\fba_s2_appdata\fba_master.db`（10-16 05:56，同目录有 invoice_history.json）

**创建时间分布**：命中的目录集中出现在开发方每次提交之前的几分钟里。例如 22:20–22:27 → 804a14a 22:28；10:58–11:06 → 17b2995 11:17。共 8 组，全部是这种模式。

**我们评审目录里的副本**：
- `fba_review_s8docs` / `s9s1` / `s9s1fix` / `s9s2` / `s9s2fix` / `s9s2fix2` / `s9s4` 里都没有任何真实库或会话的副本（0 命中）。
- 我们 02h–03h 的密集测试时段建了 83 个目录，命中 0。
- 本轮 `fba_review_s9s4` 里只有我们自己做的哨兵假数据和快照 CSV（只含路径、大小、哈希）。

**开发方提到的 fbasrc、fbasrc2、fba_s1_verify**：
- 不是我们建的。三者创建于 10-16 04:18 / 04:22 / 05:20，早于我们第一个评审目录 `fba_review_s8docs`（10-16 12:44）。
- 内容是项目目录的整份拷贝（保留了原文件时间），不是迁移产物。
- 里面确有真实会话副本：fbasrc 22 件、fbasrc2 18 件、fba_s1_verify 14 件，哈希与真实文件一致。fba_s1_verify 还有一份与真实 app_data 库同大小的库。
- 都没动。

**建议**：全部清单交给用户决定是否清理。

### 0-3 哨兵实验【fix1 / V3.1 exe】

- 先确认副本里没有真实库：clone 不带未跟踪文件，`repo\backend` 里没有 db、没有 sessions。
- 对照组（没放哨兵）：新测试目录里 sessions = 0。
- 把假库（只有 `sentinel_marker` 表）和假 sessions 放进 `repo_sentinel2\backend\`，再分别运行：
  - pytest（`fba_test_app_data_a3p9nx2o`）
  - 显式 FBA_APP_DATA_DIR + ensure_app_data_layout
  - smoke --keep（`fba_smoke_dgnpkv2x`）

  三种情况哨兵**都被复制了**：sessions 2 件，哈希一致，DB 标记为真。
- V3.1 exe 副本，exe 目录里放哨兵：设 FBA_APP_DATA_DIR 和默认 `exe\app_data` 两种情况都会复制。打包模式下这本来就是预期的升级路径。

### 0-4 fix2 核实

**迁移判断矩阵**【fix2】。子进程实测，打包模式用 `sys.frozen=True` 加示例旧版目录模拟：

| 场景 | 判定 | 结果 |
|---|---|---|
| 开发，什么都不设 | dev_default，不迁移 | 哨兵未复制 ✓ |
| 开发，ALLOW=1 | explicit，迁移 | 复制 ✓（开关有效） |
| 开发，ALLOW=1 + FBA_APP_DATA_DIR | 不迁移 | ✓ **开关压不过** |
| 开发，ALLOW=" TRUE " + FBA_APP_DATA_DIR | 不迁移 | ✓ |
| 开发，ALLOW=1 + FBA_NO_BROWSER | test_env，不迁移 | ✓ |
| 打包，什么都不设 | frozen，迁移 | 库、sessions、user_settings 复制；lingxing.json 不复制 ✓ |
| 打包，ALLOW=0 | explicit_off，不迁移 | ✓ |
| 打包，ALLOW=1 | 迁移 | ✓ |
| 打包，FBA_APP_DATA_DIR（加或不加 ALLOW=1） | 不迁移 | ✓ |
| 打包，FBA_NO_BROWSER=1 | test_env，**不迁移** | 见 L-c |
| 打包，PYTEST_CURRENT_TEST | 不迁移 | ✓ |

- 打包版正式迁移路径（只用示例旧数据）仍然工作，没有退化。
- 用 fix2 的 `repo_fix2\backend` 起后端截图时，backend 里放着哨兵，设了 FBA_APP_DATA_DIR，临时 app_data 里只有新建的库，没有哨兵 ✓。

**护栏强度**【fix2，`backend/realdata_guard.py`】。哨兵逐项实验，`find_real_copies` 直接调用：

| 复制方式 | 拦住？ |
|---|---|
| copy2，同名 fba_master.db | ✓ |
| copy2 到 sessions/ 并改名 | ✓（靠“mtime 早于会话开始”） |
| copy2 改名为 old_master.db | ✗ |
| copy2 到 config/backup.sqlite | ✗ |
| copyfile（不保留 mtime），同名 fba_master.db | ✗ |
| copyfile，同名放进 sessions/ | ✗ |
| copyfile，改名放进 sessions/ | ✗ |
| copy2，会话文件放在 sessions/ 以外 | ✗ |
| copy2 后库被 init 改写（大小 / mtime 都变） | ✗（单独调用时；conftest 会话初始化那一处在 init 之前检查，能拦住这种情况） |

**9 种情况只拦住 2 种。** 原因有两个：
- 只检查名为 `fba_master.db` 的文件和 `sessions/` 下的文件；
- 只比“同名 + 同大小 + 同 mtime”或“mtime 偏旧”。

---

## 一、结论与得分表

**总分 96.9 / 100，不通过（及格线 ≥ 99）。必须修 3 项：L-b、N1、N2。**

fix2 把泄漏的根因修好了，决策矩阵全部正确，打包版升级路径没有退化。其余回归全部通过：pytest 1030 正序、逆序、随机顺序，golden 82，tsc 0，冒烟 19/19，py3.9，密钥扫描 0，脱敏无新增。

失分来自三件事：
- step3 的 SKU 大小写统一漏了发票路径，会写错行；
- step4 的 S9-B 提示在“同一次促销、第二次同步价格小幅变化”时会消失；
- fix2 的护栏只比 stat，改名或不保留 mtime 的复制拦不住。

| 项 | 版本 | 结论 | 扣分 |
|---|---|---|---|
| L 真实数据泄漏根因 | step3–fix1 有；fix2 修好 | 矩阵 11 种场景全对，回归后新建临时目录真实副本 0 个 | 0（fix1 时为 −1） |
| **L-b 护栏强度** | fix2 | 只比 stat，9 种复制方式拦住 2 种；没有按用户要求比较真实库哈希 | **−0.5 必须修** |
| L-c FBA_NO_BROWSER 关闭打包版迁移 | fix2 | 无浏览器模式首次启动新版时不搬旧数据，见二 | −0.2 |
| **N1 发票：只差大小写的两个 SKU 互相覆盖** | step3 起，fix2 仍在 | 写错行（HS 编码和品名串到另一个 SKU） | **−1 必须修** |
| **N2 S9-B：同一次促销第二次同步价格变动，提示消失** | step4 起，fix2 仍在 | 首同步的 self_first 被自己当参照，升成 confirmed | **−1 必须修（或用户改 D-15）** |
| N3 PATCH / Excel 同步对大小写冲突不返回 409 | step3 起 | PATCH 返回 404「产品库里没有」；local-excel/sync 的 ValueError 统一成 400 | −0.1 |
| N4 测试缺口 | step4 / fix2 | 变异存活：窗口 90→91 天、审计截断两处、空采集时间 | −0.1 |
| UI | fix1 = fix2（前端未改） | 确认流程顺畅；「无变化」组折叠时其中的提示看不到；失败 toast 不消失 | −0.1 |
| D-14..D-18 记录、D-01..D-13 字节一致、origin 主体逻辑、90 天窗口、确认接口校验 / 404 / 409 / 审计、迁移幂等、旧 exe 兼容、127.0.0.1、HANDOFF | — | 通过 | 0 |
| v3 的 9 个轻微项（Excel 提示、舍入、去重、鉴权判定、「频繁」、UI h/i/j/k） | step3 | 都已修，并有测试和变异覆盖 | 0 |
| 回归、密钥、脱敏、git 卫生、文档计数、版本号 | fix2 | 通过 | 0 |
| **合计** | | | **−3.1 → 96.9** |

### 能否进入 V3.2 打包

**现在不能。** 必须先满足以下前提：

1. 修好 N1、N2（或由用户书面改 D-15，接受“价格变动即视为有参照”）、L-b，出 s9-step4-fix3，复测达到 ≥ 99。
2. L-c 至少二选一：
   - 打包模式不把 FBA_NO_BROWSER 当成测试环境；
   - 跳过迁移但旧数据存在时，打日志并在界面提示。
3. 版本号统一改成 V3.2（前端、后端、打包脚本、HANDOFF），从对应 tag 的干净 checkout 打包。
4. 打包前决定 `backend/templates/产品信息表.csv` 是否随包分发。这是被跟踪的模板，含真实形态的产品数据（MSKU / ASIN / FNSKU / 品名 / 品牌各若干处）。启动时会通过 catalog_seed 灌进每个新 app_data，测试的临时库里也有。V3.1 的 `_internal\templates\` 里已经带了它。

**打包后的交付物复核清单**（下一轮执行）：
- zip 的修改时间晚于对应提交时间（ET）；
- 解包后逐项确认没有：`.git`、`*.db`、`sessions/`、`lingxing.json`、`*.key`、`.env`、`app_data/`、含真实 SKU 的截图（按文件名，并对 PNG 文件做哈希比对）；
- exe 只监听 127.0.0.1（`run_app.py:68`、`launcher_fastapi.py:45/64`；本轮 V3.1 实测是 `127.0.0.1:8002`）；
- 用示例旧数据跑一遍迁移：旧版目录结构的 exe 旁放示例库、示例 sessions 和 user_settings，首次启动后搬进 app_data，二次启动不覆盖，lingxing.json 不搬；
- 新包打开旧 schema 示例库，origin 为 legacy，regular_price_at 补成迁移时间；
- 旧 V3.1 exe 再打开升级后的库，可正常读写。

---

## 二、新缺陷

1. **N1 发票：只差大小写的两个 SKU 互相覆盖（中等，−1，必须修）【step3 起，fix2 仍在】**
   - 位置：
     - `backend/fba_tool/invoice_automation.py:526` 用 `sku_key = sku.upper()`，L556/557 用它作 `result` 和 `ai_keys_by_sku` 的键；
     - `backend/fba_tool/invoice_table.py:186-196` 用 `meta[sku.upper()]` 作键，存 CSV 里的品名、ASIN、FNSKU；
     - 之后 `invoice_table.py:283/286/287` 再用 `lookup_sku(...)` 去查。
   - 实测（探针 `probe\t_s94.py::test_invoice_customs_by_sku_collision`，示例 SKU）：
     - 产品库里有两条：`DEMO-K2`（甲品名，HS 1111111111）和 `demo-k2`（乙品名，HS 2222222222）。D-17 规定这是两个合法的不同 SKU。
     - `_customs_by_sku` 返回的键只有 `DEMO-K2` 一个；
     - `DEMO-K2` 这一行拿到的是 **乙品名 / 2222222222**，demo-k2 也一样。第二条覆盖了第一条，写错了行。
   - 对比：
     - 报关 `customs_package.py:297` 里的 `sku_key` 已经不用了，查库是原样优先，这条路径没问题；
     - 产品库的写入入口遇到冲突都拒绝写入：upsert / set_product_fields 抛 SkuCaseConflict，定时同步记 sku_case_conflict 差异、两行都不写。
   - 修法：
     - 键改成原样写法 `sku_text(sku)`，两处都改；
     - 加一条测试：同一票里同时有 X 和 x，HS 编码和品名各自正确。

2. **N2 S9-B：同一次促销里第二次同步价格小幅变化，提示消失（中等，−1，必须修，或由用户改 D-15）【step4 起】**
   - 位置：`backend/fba_tool/product_fields.py:200-220` `_track_nonpromo`。`ref = _max_ref(reg, _recent_nonpromo(existing))` 没有排除来源为 self_first 的记录，所以首次同步自己记下的促销价会被当成参照。
   - 实测（`t_s94.py::test_same_promo_second_sync`）：首同步售价 16（假定其实是促销价，领星没给常规价），第二次同步的价格分别是：

     | 第二次价格 | origin | 提示 |
     |---|---|---|
     | 16.0 | self_first | 有 ✓ |
     | 15.9 / 15.5 / 16.2 / 16.5 / 17.0 | **confirmed** | **消失** ✗ |

     促销中价格小幅调整很常见，比如 Lightning Deal 或优惠券变化。这时并没有任何“促销前历史价”的证据，提示却没了，违反复测要求「第二次同步、同一次促销时仍然提示」。
   - D-15 的说明写了「直到售价变化或人工确认」，所以现在的行为与文字一致，但与这次复测要求冲突，需要用户裁定。
   - 修法建议：只有参照来自有效常规价或非 self_first 的记录时才升为 confirmed。如果参照只有 self_first，新记录仍记 self_first；也可以要求本次价格比 self_first 高出 5% 以上才算新证据。
   - 本条另外核实通过的项：
     - self_first 不算有历史；
     - legacy 和空值算有历史；
     - 有效常规价时不提示；
     - 价格不变时提示保留；
     - 超过 90 天提示回来；
     - 提示不改申报价（self_first 和 legacy 的申报价相同）；
     - 文案不含 list_price 或「建议」。

3. **L-b 护栏只比 stat（中等偏轻，−0.5，必须修）【fix2】**
   - 位置：`backend/realdata_guard.py:42-60`、`backend/conftest.py`（e3d3908）。
   - 实测见 0-4 的表：改名，或用不保留 mtime 的方式复制（copyfile / 流式复制 / robocopy /COPY:D），都拦不住。用户上一轮明确要求「conftest 守卫测试临时 app_data 不含真实库哈希」。
   - 修法：
     - 会话开始时，对真实来源计算 SHA-256，只在内存里，不输出；
     - 扫描临时目录里**所有**文件（`.db` / `.sqlite` / `.json`）；
     - 先按大小过滤，再比哈希；
     - 对 SQLite 文件再加一个特征：`product_master` 表加上真实行数，或真实 sku 集合的哈希；
     - 覆盖范围加上 smoke 的临时目录。

4. **L-c FBA_NO_BROWSER 会关闭打包版迁移（轻微，−0.2，建议修）【fix2】**
   - 位置：`app_paths.py`（e3d3908）`_in_test_env()` 把 `FBA_NO_BROWSER` 当成测试环境，判定顺序在 frozen 之前。
   - 实测：打包模式加 FBA_NO_BROWSER=1，示例旧库和 sessions **没搬**，app_data 是空库。
   - 后果：用户如果用无浏览器模式（远程启动或脚本）第一次启动 V3.2，旧数据还在 exe 旁，没有丢，但界面看起来是空的。之后在空库里一操作，库文件就存在了，`_copy_if_missing` 以后也不会再搬，旧数据等于被搁置。
   - 修法：
     - 打包模式下不看 FBA_NO_BROWSER，只看 pytest 和 FBA_APP_DATA_DIR；
     - 跳过迁移、但检测到旧数据存在时，写日志并在首页提示。

5. **N3 冲突时 PATCH 返回 404、Excel 同步返回 400（轻微，−0.1）【step3 起】**
   - `routers/master_data.py:82`：库里有 `DEMO-K1` 和 `demo-k1`，PATCH `Demo-K1` 时，`get_product_by_sku` 遇到冲突返回 None（`master_db.py:607-618`），接口回 404「产品库里没有 SKU」。提示不对，但没有写错行。
   - `master_data.py:145`：SkuCaseConflict 是 ValueError 的子类，被统一成 400。
   - DELETE 和 confirm 已经返回 409 ✓。
   - 修法：两处都先捕获 SkuCaseConflict 再返回 409。

6. **N4 测试缺口（轻微，−0.1）**
   - 变异存活：
     - W1：窗口从 90 天放宽到 91 天，测试只测了 89 和 91 天。探针实测 90 天减 5 分钟在窗口内、加 5 分钟在窗口外，行为正确，只是没测；
     - C7 / C8：审计里 note 截到 200 字、input 截到 40 字，没测；
     - W3：采集时间为空时视为过期。迁移后不会出现空值，影响小。
   - MUT5 的 n2_import_no_rows 存活：全部坏行返回 422 时，没有测试断言 detail.errors 里带行号。
   - 其余 3 个存活变异是等价变异：S5（原样优先 / 去空白优先）、G6（pytest 里本来就是测试环境）、G9（初始化检查与每个测试的检查重复）。

7. **UI（轻微，−0.1）【fix1 = fix2】**
   - 「无变化」组默认折叠。组里 SKU 的 S9-B 提示看不到，示例里 DEMO-UI-02 就是这样，组标题上也没有提示数量。
   - 填非法值点确认后，红色 toast 一直留着，确认成功后两条 toast 同时显示。
   - 观察，不扣分：页面外壳（顶部步骤条）最小宽度约 1077px，窗口 ≤ 900px 时整页有横向滚动条。这是 S9 之前就有的，不属于本轮改动；预览面板本身在 420 / 600 / 900 都没有溢出。

---

## 三、规则决策与功能逐条复核

### step3：SKU 统一（sku_keys.py）

- `sku_key` = NFKC → strip → casefold。探针结果：

  | 输入 | 结果 |
  |---|---|
  | 全角 `ＡＢＣ－１` | → `abc-1` ✓ |
  | NBSP / 全角空格（首尾） | 被去掉 ✓ |
  | 中间的 NBSP | 被 NFKC 转成普通空格，`ABC\u00a0-1` 与 `ABC -1` 同键 |
  | ß | → ss（`straße-1` 与 `STRASSE-1` 同键，并报冲突组） |
  | 土耳其 İ | → `i̇`（i 加组合点），与普通 i **不同键** |
  | 零宽 ZWSP | 不去掉，成为不同的 SKU（miss → 新建一行） |

  以上都符合“只做 NFKC + 大小写”的定义，没有误合并。零宽字符不可见，可能造成看起来一样的两行，建议在导入时提示（观察，不扣分）。
- 精确优先、唯一规范命中、多条报冲突：变异 S1 / S2 / S3 / S4 / S7 全部被杀。
- 冲突时各写入口的表现：

  | 入口 | 结果 |
  |---|---|
  | DELETE、confirm | 409 ✓ |
  | upsert、set_product_fields | 抛 SkuCaseConflict ✓ |
  | 定时同步 | 记 sku_case_conflict 差异，两行都不写 ✓ |
  | 报关 | 出 sku_case_conflict 警告，不写错 ✓ |
  | PATCH | 404 ✗（N3） |
  | local-excel/sync | 400 ✗（N3） |
  | 发票 | 写错行 ✗（N1） |

  listing 导入探针用错了表头（需要 MSKU 列），这条记为未测。
- 显示和导出保留原写法 ✓。golden 82 passed（2557 格）✓。

### v3 的 9 个轻微项【step3】

| 项 | 结果 |
|---|---|
| Excel 只跳坏行、全坏才 422 | test_import_apply_* ✓ |
| ROUND_HALF_UP | 三处一致 ✓（`lingxing_adapter.py:111`、`customs_package.py:37`、`invoice_rules.py:70`） |
| 重复提示去重 | ✓ |
| `is_auth_failure` 三通道统一 | ✓（`lingxing_mcp_client.py:111`） |
| 「频繁」改成具体短语 | ✓（`lingxing_mcp_client.py:86-88`） |
| UI h / i / j / k | ✓（截图核对） |
| price_max 可配置 | ✓ |

旧变异 a3 / m4 / MUTA 系列全部被杀。

### step4：决策文档

- `docs/用户决策记录.md`：9793488 到 e3d3908 只在第 186 行之后追加了 D-14..D-18。**D-01..D-13 前缀逐字节一致** ✓。
- D-14 标「用户确认 2026-10-17（经主对话转达）」✓。
- D-15..D-18 都标了「两 Bot 选定，授权由开发方 Bot 转述（…），用户可推翻」✓。
- 内容与实现一致。注意 D-15 的说明「直到售价变化」正是 N2 的来源。

### origin 三态与 90 天窗口

- 见 N2。
- 升级后的提示：
  - 有近期非促销记录的旧行 → legacy，无提示 ✓；
  - 常规价有信息的旧行 → 无提示 ✓；
  - 下面两种旧行**会提示**，按定义是正确的，但升级后这类 SKU 会集中出现提示，建议在 HANDOFF 里说明：
    - 没有非促销记录的旧行（S8 之前的老数据）；
    - 记录已超过 90 天的旧行。
- 窗口边界：

  | 距今 | 常规价 | 非促销价 |
  |---|---|---|
  | 89 天 | 有效 | 有效 |
  | 90 天减 5 分钟 | 有效 | 有效 |
  | 90 天加 5 分钟 | 无效 | 无效（提示出现） |
  | 91 天 | 无效 | 无效 |

  全部符合 `<= 90 天`。
- 旧常规价从迁移时间起算 ✓。

### confirm-normal-price 接口

- 输入校验：
  - 返回 422：`12,5`、`abc`、`0`、`-1`、`1e3`、`100000.01`、空串、None、`0.004`、True，以及非 JSON 请求体；每次库都没被改；
  - 接受：`１２．５`（全角）、`$12.50`、`1,299.00`、`100000`（等于上限）、`12.345`（存为 12.35）；
  - 价格上限可配置 ✓。
- 其他情况：
  - 未知 SKU → 404 ✓；
  - 规范化唯一命中 → 200，写到原样那一条 ✓；
  - 冲突 → 409，提示列出候选 ✓。
- 重复提交：每次都写库并追加一条审计。没有防重，但每条审计都记录了旧值，可以追溯，可接受。
- 审计字段：time、action、sku、input（截到 40 字）、price、listing_price、old_last_nonpromo_price/at、old_origin、note（截到 200 字）。没有 key 或 token，不含假 Key ✓。
- 只绑 127.0.0.1：`run_app.py:68`、`launcher_fastapi.py:45/64`；开发用 main 时由 `security.py` 检查，非本机地址必须设口令 ✓。

### 迁移（只用示例库）

- 旧代码（9793488）建示例库 → fix2 升级两次：
  - 列数 41 → 42；
  - origin 为 legacy；
  - 空的 regular_price_at 补成迁移时间；
  - 第二次升级结果不变（幂等）✓。
- 旧代码再打开升级后的库：init 正常 ✓。
- V3.1 exe 副本用升级后的示例库启动：`/api/health` 200，列表 200，示例行 2 条，只监听 `127.0.0.1:8002` ✓。
- 中途失败（模拟 ensure_v3 抛错）：ADD COLUMN 已经生效（SQLite 的 DDL 自动提交），补时间的 UPDATE 回滚了。不是原子操作，但再跑一次就能补齐，结果与正常升级一致，可接受（观察，不扣分）。

### HANDOFF

- 列出了含真实值的历史提交：25 个，只写提交号和类型。我们的脱敏扫描对 e3d3908 与 9793488 的计数完全相同，说明 step3–fix2 没有新增真实值 ✓。
- 写明了：zip 不含 .git、对外用新的脱敏仓库、整页截图用示例 app_data、截图只归档在 docs ✓。
- fix2 一节写明副本 153 个目录，与我们的统计一致：146 个顶层目录，加上 pytest-of 下的子目录 ✓。
- 文档里的测试数 1030 与实测一致 ✓。

---

## 四、未测

- `import/listing/apply`、`import/edits/apply`、`import/carton/apply`、`tickets/import/apply`、`lingxing confirm / schedule` 这几个入口遇到大小写冲突时的返回值：listing 探针表头用错，其余没逐个造数据。目前只做了静态核对：都经过 upsert / set_product_fields，冲突时会抛异常。
- 货代路径（shipment_cross_check）遇到大小写重复：没单独造数据。
- py3.9：全部测试在 3.9.13 的 venv 里运行，没有另装其他版本对比。

---

## 五、测试质量（变异）

- **旧变异**（mut3 / rpc / muta / mut4，46 个，跑在 fix2 上）：
  - 杀死 43 个；
  - MUT=none 是对照组；
  - `m4_no_auth_codes`、`m4_429_fatal` 的打桩点 `AUTH_CODES` 在 S9-step2-fix2 后已经不是判定入口，由 MUT5 的 m4v2_* 代替。上轮也是同样的情况。
- **MUT5**（17 个，跑在 fix2 上）：
  - 杀死 7 个：n1_strip_commas、n1_thousands_loose、n2_no_row_try、n2_import_no_generic、n3_allow_sci、n5_403_always_auth、a3v2_parse_loose。
  - 打桩点已经变化、变异没打进去的有 8 个：
    - 7 个在 step3 统一鉴权判定和舍入时被重构了：n3_check_before_round、n5_403_never_auth、n5_401_ratelimit_retry、n6_rpc_substring、n6_rpc_no_prefix、m4v2_no_auth_codes、m4v2_429_fatal。
    - n2_no_max：step3 起由 `price_max()` 读取设置，`PRICE_MAX` 只是兜底值。

    这 8 个改用源码变异重做，A1–A6（`is_auth_failure` 的 403 / 401 / 封禁 / 宽泛「频繁」 / JSON-RPC Key 无效 / 前缀）、R1（先判 0 再舍入）、N2v3（去掉价格上限），**8 个全部杀死**。
  - 存活 2 个：
    - n2_no_catch_parse：上轮也存活，是等价变异；
    - n2_import_no_rows：「全部坏行才 422」时，422 不带行号明细，测试也发现不了，算到 N4。
- **本轮新增源码变异**（34 个，另外替换上面的旧变异 8 个，共 42 个，跑在副本 `repo_mut` 上，逐个修改、跑完立刻还原，git status 保持干净）：
  - 新增的 34 个里杀死 27 个；替换旧变异的 8 个全部杀死；
  - 存活 7 个：W1、C7、C8、W3（见 N4），S5、G6、G9（等价变异）。
- 新增变异分组：
  - SKU：S1 / S2 / S3 / S4 / S7 杀死，S5 存活（等价）。
  - origin：O1–O4 杀死。
  - 窗口：W1b / W2 / W4 杀死，W1 / W3 存活。
  - 迁移：M1 / M2 / O4 杀死。
  - 确认接口：C1 / C3 / C4 / C5 / C6 杀死，C7 / C8 存活。
  - 迁移判断与护栏：G1 / G2 / G3 / G4 / G5 / G7 / G8 / G10 杀死，G6 / G9 存活（等价）。

---

## 六、回归与交付物

| 项 | 17b2995【fix1】 | e3d3908【fix2】 |
|---|---|---|
| pytest 正序 | 1014 passed | **1030 passed** |
| 先跑 step3/4 相关文件 | 324 | 340 |
| 逆序 / 随机（seed1017） | 1014 / 1014 | 1030 / 1030 |
| golden | 82 passed | 82 passed |
| tsc | 0 错误 | 0 错误 |
| vite build | 通过 | 通过 |
| 冒烟 | 19/19，真实 app_data 哈希不变（53 个文件） | 19/19，同左 |

- 密钥扫描（4 个模式加通用模式）：
  - e3d3908 树里有 7 处命中，全在 `frontend/bun.lock` 和 `package-lock.json`，是依赖包的 integrity 哈希，属于误报，与上轮相同；
  - `git log -p 9793488..e3d3908` 命中 0 ✓。
- 脱敏扫描：e3d3908 与 9793488 各类计数逐项相同，没有新增；「评审/文档」和「源码」两类都是 0 ✓。
- git 卫生：原仓库 HEAD e3d3908，工作区干净（只有本报告一个新增文件）。11:20 那时看到的开发方未提交修改已经进了 e3d3908。
- 版本号仍是 V3.1，与 HANDOFF 一致。
- **真实数据快照**：原仓库 `app_data\`（57 个文件）、`backend\fba_master.db`、`backend\config\sessions\` 共 58 个文件，评审前后大小和 SHA-256 **0 差异，0 新增，0 缺失**。

### 截图【fix1 = fix2，前端无改动；用 repo_fix2 构建】

- 环境：临时 app_data 加示例 SKU，mock 领星，假 Key，Edge 无头加 CDP。
- 位置：PC 上 `%TEMP%\fba_review_s9s4\shots\`，box 上 `/workspace/fba_s9s4_*.png`，共 12 张：
  - `1280` / `900` / `600` / `420`（预览面板，滚到 S9-B 提示处）和对应的 `*_top`；
  - `hint`（S9-B 提示特写）；
  - `confirm_bad`（填 12,5，提示无效原因）；
  - `confirm_done`（填 18.50 确认后提示消失，申报价随之按 D-12 更新）；
  - `after_reload`（刷新后仍保持）。
- 体验：
  - 提示是琥珀色，位置统一在价格说明下一行；
  - 新品显示「写入产品库后可确认」，不出现输入框；
  - 确认后不用刷新页面，提示立即消失；
  - 420px 下提示换成 3–4 行，不溢出（提示框宽度在面板内）。
  - 问题见二-7。

---

## 七、探针位置（都在 `%TEMP%\fba_review_s9s4\`）

- `probe\t_s94.py`：origin 第二次同步、legacy 升级、窗口边界、申报价、确认接口的各种输入和 404 / 409 / 重复 / 审计、sku_key 对照表、冲突时的各写入口、报关、发票覆盖。输出在 `out\probe1-5.out`。
- `tools\exp_fix2.py`：护栏 9 种复制方式和迁移判断矩阵。输出在 `out\exp_fix2.out`。
- `tools\mig_probe.py`：示例库升级、幂等、中途失败、旧代码重开；旧 exe 实测结果在 `out\oldexe.out`。
- `tools\cmp3.py`：fbasrc / fbasrc2 / fba_s1_verify 的哈希比对（只输出路径、大小、是否一致）。输出在 `out\cmp3.out`。
- `tools\mutsrc.py` / `mutsrc2.py`：源码变异，实时结果在 `out\mut_src_live.out`。`mut6.ps1`：旧变异，结果在 `out\mut_live_old.out` / `mut_live_new.out`。
- `regress.ps1` / `regress_fix2.ps1`：全量回归，输出在 `out\` 和 `out_fix2\`。
- `tools\keyscan.py`、`desens_scan.py`：密钥和脱敏扫描，只输出文件、行号和类型。
- 副本清单：`out\copies_list.csv`、`out\temp_scan.csv`。快照：`snap_before.csv`、`snap_after_fix2.csv`。

---

## 八、修复清单（按优先级）

1. **N1（必须）**：`invoice_automation.py:526/556-557`、`invoice_table.py:186-196` 改用原样写法作键；补“同票 X / x”测试。
2. **N2（必须，或用户改 D-15）**：`_track_nonpromo` 只把有效常规价和非 self_first 记录当参照；参照只有 self_first 时仍记 self_first（或要求高出 5% 以上）。补“同一次促销价格小幅变化仍提示”的测试。
3. **L-b（必须）**：护栏改为按真实来源的 SHA-256（只在内存里）加 SQLite 特征比较，扫描临时目录全部文件，并覆盖 smoke。补“改名 / copyfile 也能拦住”的测试。
4. L-c：打包模式不把 FBA_NO_BROWSER 当测试环境；跳过迁移但旧数据存在时写日志并提示。
5. N3：PATCH 和 local-excel/sync 先捕获 SkuCaseConflict，返回 409。
6. N4：补 90 天加或减几分钟的边界测试，以及审计截断的测试。
7. UI：「无变化」组标题显示提示数，或有提示时默认展开；确认成功后清掉之前的错误 toast。
8. 打包前：决定 `产品信息表.csv` 是否随包；版本号改 V3.2；之后按一节的交付物清单复核。
9. 副本清理：清单见 0-2，由用户决定。我们没有删除或移动任何文件。
