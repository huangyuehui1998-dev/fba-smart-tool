# 交接文档（给新 Bot，完全独立版）

> 写于 2026-10-16 约 12:00（美东，UTC-4）。接手方是**另一个账号上的 Bot**：看不到原来的盒子 `/workspace`、记忆和聊天记录。**本文件就是全部上下文**，文中引用的报告、决策、清单都已原文内联在附录里。
> 本文件在用户电脑仓库根目录：`C:\Users\huang\Desktop\FBA_Smart_Tool_Cursor2026.7.1\FBA_Smart_Tool_Cursor\交接文档_给新Bot.md`。仓库里另有滚动更新的 `HANDOFF_交接清单.md`（附录 D 是它在交接时的全文）。

> **更新记录（s8-docs，2026-10-16 约 12:30 ET）**：按 FBA测试员《交接文档评审》（93 分，`docs/评审报告/交接文档_评审.md`）和《S8 复测评审 v2》（S8-fix1 99.5 分，`docs/评审报告/S8_测试评审_v2.md`）修订：① v8 方案、规则清单、待确认问题初版答案、用户决策记录、发票模板清单、S1–S8 全部评审报告与深度测评报告已提交到仓库 `docs/`（见第 14 节），文中引用改为仓库路径；② 附录 D 去掉“和盒子同步/盒子镜像工作流”的要求，新 Bot 只在用户电脑上工作；③ 冒烟命令改为 `--real-app-data=app_data`；④ 速览改指第 12 节，第 12 节写明 D-12 四个场景；⑤ 补 tag `handoff-newbot` 说明、S1（99）和 S3（99.5）通过分数；⑥ 钓鱼线 HS 改正（HQ 954309 的结论是 9507.90.20，不是 5404）；⑦ 琪珞“重量口径未定”提示改用琪珞的例子；⑧ 新增 D-12“手动同步 → 预览 → 确认”端到端测试；D-12 用户原话补全为选项卡片上的逐字回复。全仓文档按代码核对更新（tag `s8-docs`）。

---

## 0. 一页速览

| 项 | 现状 |
|---|---|
| 项目 | FBA 发货助手（FastAPI + React + SQLite，Windows 便携版 exe） |
| 当前版本 | **V3.2**（`dist/FBA_Smart_Tool_V3.2_便携版.zip`，从 tag `v3.2` 的干净检出打包；大小和 SHA-256 见交付报告；旧版 zip 全部保留） |
| 当前阶段 | **S9 已完成（tag `v3.2`，同时算 s9-final）。用户决定在此停止，S10 Figma 改版已取消；项目停止开发。**（S7、S8 已完成，tag `s8-final`） |
| 最新 tag | `v3.2`（PC 仓库；之前 `s9-step5`、`s9-step4-fix3`、`s9-step4-fix2`、`s9-step4-fix1`、`s9-step4`、`s9-step3`、`s9-step2-fix2`、`s9-step2-fix`、`s9-step2`、`s9-step1-fix`、`s9-step1`、`s8-final` = `s8-fix5`） |
| PC 实测 | pytest **1119 passed**（v3.2，正序 / 倒序 / 随机各一遍；s9-step5 时 1115，s9-step4-fix3 时 1090，s9-step4-fix2 时 1030，s9-step4 时 1014，s9-step3 时 991，s9-step2-fix2 时 918，s9-step2-fix 时 832，s9-step2 时 765，s9-step1-fix 时 729，s9-step1 时 706，s8-final 时 695）；tsc 0 错误；冒烟 20/20；golden 失败 0；exe 临时目录启动正常 |
| 下一步 | 无（项目停止）。如果用户以后要继续，从 tag `v3.2` 开始 |

---

## 1. 用户与工作方式（必须遵守）

- 用户：**Christopher**（Christopher Roberts），电脑用户名 `huang`，在美东时区。**所有回复用简体中文**；报告时间一律写美东时间（如“11:51 ET”）。
- 风格：要结论、要证据（测试数、提交号、文件路径），不要空话；说明写清楚“改了什么、为什么、怎么验证”。
- **一步一步改代码**：每个缺陷一个可验证的改动，改完跑全套测试；阶段完成后打 tag。
- **每个阶段必须经测试员评审 ≥99 分才算完成**。没过就按报告修（tag 命名 `sN-fixM`），评审通过前绝不标“已完成”。
- **安全红线**（用户原话反复强调：“no real app_data or keys, delete nothing, keep keys out of git, keep the %TEMP% copies, back up HANDOFF before overwriting it”）：
  1. 不读、不改、不提交真实业务数据：仓库根 `app_data/`、`backend/fba_master.db`、`backend/config/sessions/`。测试、冒烟、启动 exe 一律用临时数据目录（环境变量 `FBA_APP_DATA_DIR`）；设了它或在测试环境时不做旧数据迁移（S9-step4-fix2），conftest 护栏会拦住真实库 / 会话副本。
  2. **不删除任何文件**。要清理就 `git mv` 到 `archive/`（决策 D-11）；要取消跟踪就 `git rm --cached`（本地文件保留）。
  3. **密钥永远不进 git**，也不写进任何文件、日志、文档。领星密钥曾在聊天里出现过，**不得使用**。提交前扫描：`git grep --cached -n -I -E "sk-[A-Za-z0-9]{20,}|mcp_key|app_secret"`，应无真实密钥命中。
  4. 保留 `%TEMP%\fba_s1\` 下的补丁包和日志副本，不要清理。
  5. 覆盖 `HANDOFF_交接清单.md` 前先带时间戳备份（例如复制到 `%TEMP%\fba_s1\handoff_backup\HANDOFF_YYYYMMDD_HHMMSS.md`）。
- 遇到需要用户拍板的事：**停下来问**，写进 HANDOFF 第 6 节“阻塞/待用户决定”，不要猜。用户授权“由我们判断”的，要在决策记录里写明“这是 Bot 选的参数，用户可改”。
- 外发消息、删除、购买等不可逆操作必须用户明确批准。

---

## 2. 项目位置、技术栈、架构

- **仓库**：`C:\Users\huang\Desktop\FBA_Smart_Tool_Cursor2026.7.1\FBA_Smart_Tool_Cursor`（本地 git，没有远程）。
- **完整备份**（不要动）：同级目录 `FBA_Smart_Tool_Cursor_backup_20261016`。
- **后端** `backend/`：FastAPI + uvicorn，SQLite 主库（`fba_master.db`，在数据目录），pandas/openpyxl/xlrd/PyMuPDF。代码必须兼容 **Python 3.9**（PC 的 venv 是 3.9.13）。
  - `main.py`：应用入口，挂载 `routers/*`；静态托管 `backend/dist`（前端构建产物，不进 git）。
  - `fba_tool/`：业务逻辑。重点模块：
    - `master_db.py`（产品库读写，`_row_to_dict` 是所有产品读取的出口）、`product_fields.py`（字段归属/来源锁定、申报价 `resolve_declared_price`、D-12 促销 `promo_info`/`normal_price`）
    - `shipment_parser.py`/`shipment_validator.py`（亚马逊货件 CSV/PDF 解析与校验）
    - `customs_package.py`/`customs_export.py`（报关资料 .xlsx/.xls）
    - `invoice_rules.py`/`invoice_export.py`（按货代模板导出发票：适配器 send、jiufang、deshu_t3、qiluo_t6、qiluo_t5）
    - `invoice_templates.py`（识别/解析货代发票 T1–T8，并与货件 CSV 交叉核对仓库、箱数、数量口径、重量口径）
    - `lingxing_*.py`（领星 MCP 只读同步、预览确认、定时任务）、`secret_store.py`（DPAPI）
    - `hs_code.py`（HS 格式）、`hs_config.py`（品类+HS 申报要素模板）、`hs_presets.py`（钓具 HS 参考）
    - `app_paths.py`（数据目录：`FBA_APP_DATA_DIR` 优先，否则 `<程序目录>/app_data`）、`user_config.py`（user_settings/formulas，坏 JSON 横幅）
  - `config/*.default.json`：出厂配置（用户覆盖放数据目录 `config/`）。`templates/`：报关、货代模板（`templates/forwarders/*.xlsx`）。
  - 测试：`backend/test_*.py`（约 680 条），golden 在 `backend/tests/golden/`。
- **前端** `frontend/`：React + TypeScript + Vite + Tailwind/shadcn。`src/components/*-workspace.tsx` 是各步骤页面（Step1 录入 → Step2 装箱 → Step3 导出 → Step3.5 分仓 → Step4.5 货代发票 → Step5 报关），`src/lib/api/*.ts` 是接口封装。顶栏版本文字在 `components/app-header.tsx`。
- **启动器** `run_app.py`：打包版入口；只监听 127.0.0.1，端口 8002 起顺延；环境变量 `FBA_APP_DATA_DIR`（数据目录）、`FBA_NO_BROWSER=1`（不自动开浏览器）。
- **开发启动**：`一键启动.bat` → `scripts/start_dev.ps1`（后端 8000–8099、Vite 5173–5199）。**不要**在没设临时数据目录时启动，否则会读写真实 app_data。
- 更详细的模块定位见仓库内 `FBA_Smart_Tool_代码架构定位手册.md`；用户操作说明见 `用户使用说明.md`。

---

## 3. 环境与测试命令（全部在 PowerShell，仓库根目录）

```powershell
cd C:\Users\huang\Desktop\FBA_Smart_Tool_Cursor2026.7.1\FBA_Smart_Tool_Cursor
# venv 已存在：backend\.venv（Python 3.9.13）。若需重建：
#   py -3.9 -m venv backend\.venv ; backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt -r backend\requirements-dev.lock.txt
# 注意：系统 python 是 3.14，不要用它跑测试或冒烟。

# 1) 全量测试（conftest.py 会自动把 FBA_APP_DATA_DIR 指到临时目录）
cd backend; .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider; cd ..
#    期望：≥1119 passed（v3.2 实测 1119），0 failed

# 2) 前端类型检查
cd frontend; npx tsc --noEmit -p .; cd ..      # 期望：无输出，exit 0

# 3) 冒烟（必须用 backend\.venv 的 Python；需要先打包过，backend\dist 存在）
$env:PYTHONIOENCODING="utf-8"
backend\.venv\Scripts\python.exe scripts\smoke_e2e.py --real-app-data=app_data
#    注意：参数必须写成 --real-app-data=路径（等号，不能用空格）；在仓库副本里跑时写真实目录的绝对路径
#    期望：冒烟结果 19/19；“真实 app_data 未被改动（哈希前后一致）”（只做哈希对比，不写入）

# 4) golden（已包含在全量 pytest 里；单独跑：）
cd backend; .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider test_golden_infra.py test_golden_customs.py test_s4fix_invoice_export.py test_s8fix1_invoice_adapters.py; cd ..
#    期望：失败 0；已知差异写在 tests/golden/*manifest.csv 的 expected_diff
```

- PowerShell 中文输出容易乱码：把输出重定向到文件（`*> $env:TEMP\x.txt`），再 `Get-Content -Encoding UTF8` 读。
- 原工作流：在另一台 Linux 镜像上写代码、测试（Python 3.13），用 `git format-patch` 打包到 `%TEMP%\fba_s1\<名字>\`，在 PC 上用 `apply.ps1`（`git am` → 跑 pytest → 失败自动回退 → 成功则提交并打 tag）。新 Bot 可以直接在 PC 上改，但要保留“改完必跑全套、失败就回退”的纪律。

---

## 4. 打包与启动

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_standalone.ps1 *> $env:TEMP\fba_build.txt   # 约 2–3 分钟
#   产物：dist\FBA_Smart_Tool_V3.1_便携版\ 和 dist\FBA_Smart_Tool_V3.1_便携版.zip（只覆盖同名 zip，旧版本 zip 全部保留，不许删）
git checkout -- backend/templates/forwarders/qiluo.xlsx    # 打包会改写这个模板，打包后必须还原，否则工作区不干净
git status --short                                          # 期望：空
```

- 版本号在这些地方同时改：`scripts/finish_portable_dist.py`（RELEASE_VERSION）、`scripts/build_standalone.ps1`、`packaging/FBA_Smart_Tool.spec`、`run_app.py`、`frontend/src/components/app-header.tsx`、`packaging/使用说明.txt`、`用户使用说明.md`、架构手册。改版本号要用户同意。
- **启动一次验证（临时数据目录、不开浏览器）**：

```powershell
$exe="$PWD\dist\FBA_Smart_Tool_V3.1_便携版\FBA_Smart_Tool\FBA_Smart_Tool.exe"
$td="$env:TEMP\fba_exe_check"; New-Item -ItemType Directory -Force $td | Out-Null
$env:FBA_APP_DATA_DIR=$td; $env:FBA_NO_BROWSER="1"
$p=Start-Process $exe -PassThru -WindowStyle Hidden -RedirectStandardOutput "$td\..\exe_out.txt"
Start-Sleep 5; $port=(Get-Content "$td\.server_port").Trim()
Invoke-WebRequest "http://127.0.0.1:$port/api/health" -UseBasicParsing     # 期望 200，master_db true
Stop-Process -Id $p.Id -Force
```

---

## 5. 测试文件目录（只读）

- 用户的真实样例目录：`C:\Users\huang\Desktop\亚马逊-2.Inventory-库存健康 FBA`（**只读**，不改不删）。其中 `J-US FBA 9810\J-FBA US第N批 9810\` 下有各批次的发票、货件 CSV、装箱信息、报关资料等。
- 仓库里的副本（测试/golden 用）：`backend/tests/golden/samples/`（`inputs/` 货件 CSV、`invoice_templates/` T1/T3/T4/T6/T7 原件、`invoice_legacy/` 第5/6批旧发票）、`backend/templates/`（亚马逊FBA表*.csv 等）。
- 注意：`backend/templates/亚马逊FBA表.csv` 和 `亚马逊FBA表1.csv` 是**同一票**（FBA19F4BDYRN），一起上传会触发“❌ 重复上传”（D12 起是硬错误）；`产品信息表.csv` 不是货件 CSV。

---

## 6. 领星 MCP（只读）与密钥

- 接口：`https://openmcp.lingxing.com/mcp-servers/lingxing-mcp`（`fba_tool/lingxing_mcp_client.py`）。
- **只读白名单**（`lingxing_scheduler.READ_ONLY_TOOLS`）：`get_my_sids`、`get_multi_platform_shop_list`、`erp_listing`、`get_fba_stock_list`、`query_fba_valid_list`、`query_product_performance_asin_lists`。任何写操作工具都会被拒绝。
- 流程：手动同步 → 生成预览 → 用户按字段勾选确认写入；定时同步（默认关闭，间隔可配，失败重试）按预览默认勾选自动写入（D-02），手填锁定字段跳过（申报价 listing_price 例外，D-01）；乱码 SKU、缺 FNSKU/ASIN 进“需复核”默认不勾。
- **密钥存储**：`fba_tool/secret_store.py` 用 Windows **DPAPI**（CryptProtectData，当前用户范围，熵 `FBA_Smart_Tool/lingxing`），存成 `dpapi:v1:<base64>`，写在数据目录 `config/lingxing.json`。非 Windows 没有后端时直接报错，不会退回明文。换电脑/换用户要重新填密钥。`lingxing.json` 被 `.gitignore` 排除。
- **领星 MCP 新接口（S9-step1 已适配）**：领星 MCP 只有 help / search / action 三个元工具（业务工具用 toolId，toolType 分 read / write）。**S9-step1 已适配**：客户端每次 action 前先 search 同一 toolId，只放行 toolType=read 且在 READ_ONLY_TOOLS 白名单里的工具；help 列表不全（实测 erp_listing 不在 help 里），以 search 为准。白名单 6 个旧工具名在新接口里都存在、名字不变、都是 read（见 §10 S9 对应表）。
- 测试一律 mock（见 `test_s5_lingxing_schedule.py` 的 `MockMcp`、假 Key），**绝不连真实领星、绝不使用聊天里出现过的密钥**。

---
## 7. 用户决策 D-01 至 D-18（D-14 起见 docs/用户决策记录.md）

**附录 A 是《用户决策记录》全文，原样复制，含用户原话**。要点：

| 编号 | 主题 | 一句话 |
|---|---|---|
| D-01 | 申报价口径 | 按领星实时售价 listing_price 申报（领星 > 手填 declared_value > 领星 price/landed > 旧值）；**已被 D-12 修订** |
| D-02 | 产品表来源 | 产品表以领星 MCP 数据为唯一来源；定时同步按默认勾选自动写入 |
| D-03 | 本地修改 | 产品库支持网页/Excel 手动修改，手填字段锁定 |
| D-04 | 发票范围 | 发票兼容所有模板（含琪珞等货代），S4 范围扩大 |
| D-05 | 23kg 单件箱 | 单件装、标准尺寸、23kg 只提示不拦截 |
| D-06 | 拿不准就查 | 规则拿不准先查权威公开资料，注明出处 |
| D-07 | 混装分摊 | 混装多品名的毛重/净重分摊口径（按权威资料） |
| D-08 | 数据纠错 | 样例数据可能有错，由开发方交叉核对后按正确的做 |
| D-09 | S4 四点结论 | T3=德速、T4=九方、T5=琪珞；T6“单件实重”口径；第6批第1票 6 箱；第6批第5票 MGE3 |
| D-10 | VGT2 地址 | 琪珞地址库 VGT2 用的是 UPS 转运地址，纠正为 6401 Howdy Wells Ave, Las Vegas NV 89115 |
| D-11 | 归档不删 | 重复文件 git mv 到 archive/，不删除；Step 4.5 页暂留 |
| D-12 | 促销保护 | 原话“加保护：促销低于正常价时用正常价报关并提示，然后开始修复”；5%/90 天是 Bot 选的参数，可改 |
| D-13 | 正常价字段与参数确认 | 不用 list_price / history_price 作申报正常价；D-12 两条实现参数（常规价高于售价才算有信息；售价 ≥ max×0.95 才更新历史价）Christopher 已确认；S7/S8 完成（s8-final），Christopher 2026-10-16 确认 |
| D-14 | 价格上限 | PRICE_MAX = 100000 美元（设置参数 price_max），**用户确认 2026-10-17** |
| D-15 | S9-B 提示 | 非促销价记录来源三态 self_first / confirmed / legacy；无有效常规价且无“有历史”记录时琥珀色提示「无促销前历史价，申报价可能偏低，请人工确认」，可人工确认（两 Bot 选定，用户可推翻） |
| D-16 | 常规价有效期 | 领星常规价只在采集后 90 天内有效；没有采集时间的旧值以迁移时间为起点（两 Bot 选定，用户可推翻） |
| D-17 | SKU 大小写 | 存原始写法；匹配用 sku_key（NFKC + 去空白 + casefold）；只差大小写的多条报冲突、不合并（两 Bot 选定，用户可推翻） |
| D-18 | 仓库与截图 | 仓库不对外共享（需要时另建脱敏副本）；发布 zip 不含 .git；整页截图只用示例 app_data（两 Bot 选定，用户可推翻） |

> 注意 D-09 第 2 点（T6 重量口径）在 S8-fix1 后的实际实现：**导出时不再固定单箱重**，按货代原件 × 货件 CSV 核对判定或用户选择（第6批单件重、第7批单箱重、德速第2批单箱重、德速第9批单件重）。

---

## 8. 发票模板 T1–T8 与支持状态（截至 S8-fix1）

| 模板 | 货代 | 识别/解析（导入，`invoice_templates.py`） | 按模板导出（`invoice_export.py`） |
|---|---|---|---|
| T1 九方·下单模板（新） | 九方 | ✅ 识别+解析，含 CSV 交叉核对 | 九方导出用 T8 版式（适配器 `jiufang`） |
| T2 SEND Invoice Template | SEND | ✅ | ✅ `send`（golden 5 份） |
| T3 Commercial Invoice 9810 | 德速 | ✅ | ✅ `deshu_t3`（S8 新增；S8-fix1 重量口径可判定/选择；对第9批原件逐格一致） |
| T4 COMMERCIAL INVOICE 下单模板（旧） | 九方 | ✅（S8 起只认“下单模板”表） | 无单独导出（用九方导出） |
| T5 下单模板 单行汇总 | 琪珞 | ✅（与 T7 平局时：有数据判 T5） | ✅ `qiluo_t5`（S8 新增，需仓库地址；混装尺寸提示） |
| T6 琪珞 FBA 专线导入模版 | 琪珞 | ✅（“！”表 476 条地址已导入） | ✅ `qiluo_t6`（S8 新增；对第6批 5 票、第7批原件一致） |
| T7 义乌宁波运单下单模板（空白） | 同 T5 | ✅（空白判 T7） | 同 T5 |
| T8 九方系统导出 箱单发票 | 九方 | ✅ | ✅ `jiufang`（golden 8 份） |

货代列表接口 `/api/invoice-export/forwarders` 现在精确返回 5 家：`send, jiufang, qiluo_t6, qiluo_t5, deshu`。附录 B 是 S4a《发票模板清单》全文（字段差异、待核实点）。

---

## 9. 阶段历史、分数与 tag

| 阶段 | 内容 | 评审分数 | tag |
|---|---|---|---|
| S0 | 规则确认（方案 v5–v8） | — | — |
| S1 | git 基线、golden 基建、文本录入、安全（127.0.0.1+口令）、FBA 重量尺寸规则、报关默认值 | 93 → S1-fix1 **99** 通过 | s1-baseline, s1b-golden, s1c-parse, s1d-security, s1e-fba-rules, s1f-customs-defaults, s1-fix1 |
| S2 | 产品库与领星（表结构、Listing 导入、箱规导入、申报价口径） | 81 → fix1 → 96 → fix2 → 99 通过 | s2-products, s2-fix1, s2-fix2, s2-final |
| S3 | 报关导出（.xlsx/.xls、钓具、混装分摊） | 98 → fix1 → 98 → fix2 → **99.5** 通过 | s3-customs, s3-fix1, s3-fix2, s3-final |
| S4a | 发票模板盘点 T1–T8 | 清单完成 | — |
| S4 | 发票模板映射 + 按货代导出（SEND/九方） | 91.5 → S4-fix1 99.1 通过 | s4-invoice, s4-fix1, s4-final |
| S5 | 领星 MCP 定时同步 | 97.8 → S5-fix1 99.8 通过 | s5-sync, s5-fix1, s5-final |
| S7 | 工程整理（配置统一、依赖锁定、tsc 0 错误、Step4.5 面板、冒烟脚本、使用说明）；版本 V3.0；归档 | 98.6 → S7-fix1 99.4；**Christopher 2026-10-16 确认完成**（随 s8-final） | s7-cleanup, s7-fix1, s7-archive |
| S8 | 按《深度测评报告 V3.0》（94.3 分）修 4 个中等 + 14 个轻微 + D-12 + HS；版本 V3.1 | s8-fix 复测 **93.0 未过** → S8-fix1 复测 **99.5**（过线）；交接文档评审 93 → s8-docs 修订；收尾评审 → s8-fix2 复测 **99.3** 通过 → s8-fix3 复测 **98.9** 未过 → s8-fix4 复测 **99.7** 通过 → s8-fix5 措辞 → **Christopher 2026-10-16 确认完成** | s8-fix, s8-fix1, s8-docs, s8-fix2, s8-fix3, s8-fix4, s8-fix5, s8-final |
| S9 | 目标 V3.2：领星 MCP 客户端适配新接口（step1）… | 进行中 | s9-step1, s9-step1-fix, s9-step2, s9-step2-fix, s9-step2-fix2 |

（没有 S6。）PC 仓库全部 tag（按时间）：s1-baseline、s1b-golden、s1c-parse、s1d-security、s1e-fba-rules、s1f-customs-defaults、s1-fix1、s2-products、s2-fix1、s2-fix2、s2-final、s3-customs、s3-fix1、s3-fix2、s3-final、s4-invoice、s4-fix1、s4-final、s5-sync、s5-fix1、s5-final、s7-cleanup、s7-fix1、s7-archive、s8-fix、s8-fix1、handoff-newbot、s8-docs、s8-fix2、s8-fix3、s8-fix4、s8-fix5、s8-final（同 cf9bed1）、s9-step1、s9-step1-fix、s9-step2、s9-step2-fix、s9-step2-fix2。

- `handoff-newbot`：打在提交 eb99139（加入本交接文档那次提交）上。是补丁应用脚本顺手打的，不代表阶段完成，可以忽略、不要删。
- `s8-docs`：全仓文档按代码核对 + 本文件按评审修订 + 钓鱼线 HS 说明更正 + 2 条补测。

---

## 10. 当前状态：S7/S8 已完成（s8-final）；S9 进行中（s9-step1）

### S9 进度（目标 V3.2，最新）
S9-step1（tag `s9-step1`，目标版本 V3.2，版本号暂不改）：领星 MCP 客户端适配新接口（help / search / action）。
- `backend/fba_tool/lingxing_mcp_client.py`：新增 `search(toolId)`（按 toolId 缓存）和 `_authorize`：每次 `action` 前先 search 同一 toolId，只有 toolType=='read' 且在 `READ_ONLY_TOOLS` 白名单里才放行，否则报“只允许只读调用…”；search 返回 code=102“未找到已发布工具”时报“领星 MCP 未知工具…”。`READ_ONLY_TOOLS` 移到客户端统一定义，`lingxing_scheduler` 从客户端导入；“未知工具”加入定时同步的不可恢复错误。解包兼容两层信封 {code:1, data:{code:1, msg, data:{total, list}}}（内层失败也报错），旧的一层格式照常可用；SSE、Mcp-Session-Id 沿用。
- 工具名对应（用盒子上的脚本只调 help / search 和 1 次 read 类 action(erp_listing, length=1) 实测；Key 没打印、没写进任何文件）：

| 旧工具名（白名单） | 新接口 toolId | search 结果（2026-10-16 实测） | 在 help 列表里？ |
|---|---|---|---|
| get_my_sids | get_my_sids | 存在，toolType=read | 否 |
| get_multi_platform_shop_list | get_multi_platform_shop_list | 存在，toolType=read | 否 |
| erp_listing | erp_listing | 存在，toolType=read | 否 |
| get_fba_stock_list | get_fba_stock_list | 存在，toolType=read | 否 |
| query_fba_valid_list | query_fba_valid_list | 存在，toolType=read | 否 |
| query_product_performance_asin_lists | query_product_performance_asin_lists | 存在，toolType=read | 否 |

6 个都能对上，名字不变，没有“待确认”项。help 返回 20 个工具，这 6 个都不在里面，所以客户端以 search 为准、不看 help。

- fixture（`backend/tests/fixtures/lingxing/`）：`mcp_search_schemas.json`（6 个工具的 toolId/displayName/toolType/inputSchema）、`mcp_action_erp_listing_sanitized.json`（真实两层结构，1 行，去掉店铺/ID/负责人/销量等字段，SKU/ASIN/品名换成示例值）、`mcp_search_unknown.json`（未知工具返回，去掉 traceId）。
- 测试：新增 `backend/test_s9_mcp_protocol.py`（11 条：SSE、会话 ID、search→action 顺序与缓存、write 类被拒、不在白名单被拒、未知工具报错、两层/一层信封、内层失败、help 不全不影响 search、fixture 无敏感字段）；`test_lingxing_sync.py::test_iter_pages_advances_by_page_size` 的假服务端补上 search 应答。
- PC 上没用真实 Key，没碰真实 app_data / sessions。

S9-step1-fix（tag `s9-step1-fix`；s9-step1 评审 99.0，报告 docs/评审报告/S9_step1_评审.md）：
- N14 `unwrap_lingxing_payload`：原则 code≠1 或不是 JSON 就报错，不再把失败静默当成“成功 0 行”。外层 code=0/102（无论有没有 success 键）、内层 code≠1（500 无 data、0 带 data）、content 不是 JSON、data 是字符串，都报 LingxingMcpError（带 code）；没有 code 键的旧一层格式按 success 判断。
- N12 `search()`：只有 code=102 或“未找到已发布工具”才报“未知工具”（不可恢复）；限流、非 JSON、空 SSE、HTTP 5xx 等原样抛出，定时同步可重试；任何错误都不放行 action。
- N13：search 结果缺 toolId 或与请求不一致 → 拒绝；白名单直接对照模块常量 `READ_ONLY_TOOLS`（frozenset），实例 `allowed_tools` 只能收窄；`_rpc` 发 tools/call name=action 时内部也走同一套校验（绕过 action() 也挡住）。
- N15：search 缓存 `SEARCH_CACHE_TTL_SEC = 600`（10 分钟），过期重新 search。
- 测试：新增 `backend/test_s9fix_mcp_hardening.py`（23 条，覆盖以上每种形态）。
- 脱敏：`backend/tests/fixtures/lingxing/erp_listing_sample.json` 的 msku/local_sku/local_name/fnsku/asin/parent_asin/item_name 换成示例值（DEMO-…），价格等形态不变，regular_price 仍等于售价；`backend/test_lingxing_sync.py` 的 store_id、sid 换成示例值（100000000000000001、9001/9002）；`test_s2_lingxing_adapter.py` 断言同步改。**注意：git 历史里仍有原始值，未改写历史。**
- 版本号仍 V3.1。

S9-step2（tag `s9-step2`；s9-step1-fix 复评 99.6 通过，报告 docs/评审报告/S9_step1_评审_v2.md）：
- M1 `_rpc`：新增 `_normalize_call`，method 和 tools/call 的 name 先去空格、转小写再对照白名单（ALLOWED_METHODS = initialize / notifications/initialized / tools/call；ALLOWED_META_TOOLS = help / search / action），未知的直接拒绝；params、arguments、action 的 params 必须是 dict；toolId 去空格后再校验、发送的也是规范化后的值。"Action"、带空格名字、"TOOLS/CALL"、params 为 list、toolId 带空格都有测试。
- M2 `_check_envelope`：只要有 success 键就必须严格等于布尔 True，字符串 "false"/"true"、1 等都报错。
- M3 致命错误改按异常类型判断：新增 `LingxingUnknownToolError` / `LingxingReadOnlyError` / `LingxingAuthError`（`fatal=True`）和 `is_fatal_exception`；定时任务 `is_fatal_error` 不再对服务器文本做子串匹配（去掉 `_FATAL_PATTERNS`），同步事件带 `fatal` / `error_type`。例：429 限流文本里含“未知工具”仍可重试。唯一保留的文本判断是 isError 内容以“MCP Key无效或已失效”开头（服务器这种情况不给 code），只用 startswith。
- 测试：新增 `backend/test_s9step2_protocol_m123.py`（27 条）。
- 脱敏（只改当前文件，**未改写 git 历史；git 历史里仍有真实 store_id / sid / ASIN / MSKU / 品牌，是否改写历史由用户决定，只有仓库要对外共享时才需要**）：
  - `backend/docs/领星对接问题与优化报告.md`：store_id → 100000000000000001，原真实 sid → 9001/9002，品牌 → 示例品牌（DemoBrand）。
  - `docs/评审报告/S9_step1_评审.md`：只改 store_id、sid、ASIN 三个值，并加注“敏感值已替换为示例”。
  - 测试里内联的真实值：`test_lingxing_sync.py`（ASIN、MSKU、品牌）、`test_s2_product_fields.py`（FNSKU）、`test_s5_lingxing_schedule.py` / `test_s8fix1_dec12_e2e.py`（原真实 sid、品牌）、`test_s2fix_hs_category.py`、`test_s3_customs_*.py`、`test_s3fix1/2_customs.py`（品牌）；`scripts/smoke_e2e.py`、`scripts/step5_user_test_seed.py`（品牌）；`lingxing_sync.py` 注释里的原真实 sid。品牌统一换成 DemoBrand，sid 换成 9001。
  - **没改（如实说明）**：金样数据（`backend/tests/golden/samples/inputs/*.csv`、build_customs_inputs.py、customs_inputs.json、product_master_golden.json）、默认配置（`backend/config/` 下 amazon_sku_metadata / fnsku_mapping / sku_mapping / invoice_history 的 .default.json）、模板（`亚马逊FBA表*.csv`、`产品信息表.csv`）、`product_catalog.py` / `input_template.py` 里的品牌和产品数据、`test1/`、`_sta_compare.json`、`scratch/`、`docs/方案`、`packaging/Step5报关资料_架构与工作流.txt`、`代码评审日志.md`、本文件和 HANDOFF 里引用金样快照 FNSKU 的一行，以及读这些真实文件的测试（`test_product_master_parser.py`、`test_shipment_validation.py`、`test_shipping_sheet.py`）。原因：这些是用户真实业务数据或产品行为（品牌会写进报关单），金样 2557 格要和原始单据逐格比对，改了会改变产品输出或让金样失真。是否也要脱敏请用户决定。
- 三 A 手动同步预览：`lingxing_preview.preview_price_info` 按“确认写入后”的状态（本地主数据 + 本次领星售价/常规价，近 90 天非促销价取本地记录）调用 `resolve_declared_price`，`serialize_preview` 每个 SKU 带 `price_info`：售价、regular_price、常规价是否有信息、申报将用的价格和来源（售价 / 常规价 / 近 90 天非促销价 等）。前端 `lingxing-preview-panel.tsx` 每个 SKU 行下显示这一行。D-12 / D-13 规则未改（list_price 不参与）。测试 `backend/test_s9step2_preview_price.py`（9 条）。
- **三 B（D-12 盲区提示）留到下一步，未做**。原因：首次同步时 `_track_nonpromo` 会把当时售价记成“近 90 天非促销价”，之后报关时无法区分“只有自己这一条记录”和“确实有历史正常价”；要在报关界面准确提示，需要新增一个持久化标记（例如记录非促销价是否是首次自记），涉及库表字段和 D-12 记录逻辑，范围超出本步。
- 版本号仍 V3.1。PC 上没用真实 Key，没调真实领星接口，没碰真实 app_data / sessions。

S9-step2-fix（tag `s9-step2-fix`；s9-step2 评审 98.3 未过，报告 docs/评审报告/S9_step2_评审.md）：
- A1（必须修）常规价单独变化也写入：`PRICE_FIELDS` 改为 (listing_price, regular_price)，regular_price 成为预览里的可勾选字段（标签“常规价（判断促销）”），变化时默认勾选，定时同步按默认勾选自动写入；`apply_lingxing_field_patch` 售价、常规价各自按勾选写（只勾售价不再顺带写常规价）。`price_info` 按实际会写入的价格字段模拟（含 `_track_nonpromo`），再走 `resolve_declared_price`，与写库、报关包同一套规则。
- A2：price_info 显示实际参与计算的售价 / 常规价，并标出来源 `*_origin`：remote = 本次领星返回并写入，local = 库里的旧值。领星不再返回常规价时，库里旧常规价仍参与 D-12 判断（本次不设有效期，见 §6 待决）。
- A3：价格解析统一走 `lingxing_adapter.parse_price`（支持 "1,299.00"、"$12"；abc、NaN、inf、负数、0、空值返回 None，原来 NaN/inf 会抛 InvalidOperation）；`_price_or_none` 同步改；预览里无效价格不进可写字段、不写库（apply 记 `skipped_invalid`），保留原值并提示；`resolve_declared_price` 遇到 0 / 负数 / NaN / inf 售价当作没有售价，不申报 0 或 NaN；预览接口不再 500。
- U1：预览每个 SKU 一行价格说明：价格带币种；写明“确认写入后申报将用：…（来源：…）”；后端给出各勾选组合的结果（`variants`），前端按当前勾选取对应一项，取消勾选售价或常规价时联动；文字全中文（不再出现 regular_price 字样）；促销时直接显示“促销中（比正常价 X 低 N%）”；有提示时显示 ⚠。
- M4：Key 无效不重试。信封业务码 401/403、JSON-RPC error（code 401/403 或文字含“Key无效”）、HTTP 401/403、业务码 102 且文字含“Key无效”，都归 `LingxingAuthError`；search 遇到鉴权失败优先报鉴权，不再报“未知工具”。单独的限流文字（isError 且不以领星鉴权原文开头）仍可重试。
- 测试：新增 `backend/test_s9step2fix_price_e2e.py`（49 条：D-12 七个场景 × 手动 / 定时两条路径都断言“预览价 == 报关包单价”，含常规价优先、回退近 90 天非促销价、过期、价格未变、只变常规价、售价和常规价都变、常规价降到售价；另有取消勾选、真实 run_once、A2 来源、A3 异常输入）和 `backend/test_s9step2fix_m4_auth.py`（18 条）。`test_s8fix1_dec12_e2e.py` 的手动确认用例改为按默认勾选（售价 + 常规价）确认——原来“只勾售价也顺带写常规价”的行为按 A1 / U1 改掉了。
- D1 脱敏：本文件和 HANDOFF 的 S9-step2 脱敏说明里不再写具体 sid（改为“原真实 sid”）；`docs/评审报告/S2_测试评审_v2.md` 的真实品名换成示例；测试 BOT 已脱敏的 `S9_step1_评审_v2.md` 一并提交（开发方复扫 0 处，加注“敏感值已替换为示例”）。新规矩：提交测试 BOT 评审报告前先扫真实值（真实 store_id、原真实 sid、原样本 ASIN / MSKU / 品名、品牌），发现就换成示例值并加注；扫描脚本只输出“文件:行号 + 类型”，真实值只在内存里。修完全仓复扫：除 §S9-step2 列明保留的几类（金样、默认配置、模板、产品目录、test1、_sta_compare.json、docs/方案、packaging、代码评审日志、scratch、读真实文件的 3 个测试、金样快照 FNSKU 说明行）外 0 处。git 历史仍含真实值，未改写，是否改写由用户决定。
- UI 截图：临时 FBA_APP_DATA_DIR + FBA_NO_BROWSER=1，mock 领星（示例 SKU、假 Key）造一次待确认预览，开发版前端（vite dev）+ 后端（uvicorn），Edge 无头截图，裁成只含预览面板：`%TEMP%\fba_s1\ui_shots\s9step2fix_preview.png`。
- S9-B（D-12 盲区提示）本次仍不做，测试 BOT 的方案意见和需要用户决定的问题见 §6 待决。
- 版本号仍 V3.1；D-01–D-13 未改。PC 上没用真实 Key，没调真实领星接口，没碰真实 app_data / sessions。

S9-step2-fix2（tag `s9-step2-fix2`；s9-step2-fix 复评 98.4 未过，报告 docs/评审报告/S9_step2_评审_v2.md，提交前已扫真实值 0 处）：
- N1（必须修）欧式价格写法不再被误读：`lingxing_adapter.parse_price_reason` / `parse_price` 是预览、定时同步、Excel/CSV 导入三条路径共用的唯一解析入口。逗号只接受标准千分位 `^\d{1,3}(,\d{3})+(\.\d+)?$`（可带 `$` / `US$` / `USD` 前缀，先做 NFKC 全角转半角）；"12,5"、"1.299,00"、"$1,2" 等其它逗号写法和点逗混用一律判无效，提示“逗号写法不规范（疑似欧式写法…），不猜测”，不写库。
- N2（必须修）超大数不再崩：解析时捕获 InvalidOperation / OverflowError / ArithmeticError 等；新增 `PRICE_MAX = 100000`（**Bot 自定参数，待用户确认，见 §6**），超过即无效；申报价校验 `_valid_price` 同样用这个上限。单行无效只跳过这一行并提示，同批其它行照常：定时同步单行出错（含 listing_to_product 抛异常）记差异 `row_skipped` / `price_invalid`（带原值），不让整次同步失败或重试；Excel 导入预览返回 200 并列出“第 N 行价格“原值”无效：原因，这一行已跳过”，确认写入遇到无效价格返回 422（detail.errors 带行号和原值），其它意外错误也返回 422“文件内容无法解析，请检查价格、数量等数字格式”，不再 500、不暴露内部类名。测试覆盖 1e30、40 个 9、1e20。
- N3：四舍五入到分后为 0 的值（"1e-3"、"0.004"）判无效；默认不接受科学计数法；Excel 导入同样拦截；提示里带原值。
- N5：HTTP / 信封 403 但文字是限流（rate limit、请求过于频繁、too many requests、限流）时按限流处理，可重试；401 一律鉴权失败。
- N6：JSON-RPC 鉴权失败判定与注释、isError 规则一致：只有 code 为 401/403（且不是限流文字），或文字以「MCP Key无效或已失效」开头，才归 `LingxingAuthError`；只含“Key无效”字样的其它文字不再算鉴权失败。已加测试。
- UI（`lingxing-preview-panel.tsx`）：(a) 用词统一——“领星常规价”只指 regular_price 字段，“正常价”只指 D-12 实际用的参照价（领星常规价或近 90 天非促销价），促销提示统一写“比正常价 X（依据）低 N%”，面板顶部一句话说明两者区别；(b) “N/8 字段”加展开箭头和“点击展开 / 收起”提示，可同时展开多个 SKU；(c) 每个价格片段不换行（white-space: nowrap），只在片段之间折行；(e) 促销期申报价高于售价时，申报行琥珀色底色并写“高于售价，按正常价申报（D-12）”；(f) 去掉面板内部滚动条，跟随页面滚动；(g) 降幅在 4.5%–5.5% 时先向下取整到两位小数，取整后 ≤5% 但实际 >5% 时显示“>5%”，其余一位小数（向下取整），不会出现实际 >5% 却显示“低 5.0%”。
- 文档脱敏（只改文档和测试内联值，不动金样和产品数据）：本文件和 HANDOFF 里金样快照 FNSKU 一行换成 X00DEMO001 / X00DEMO002；`docs/方案/FBA_Smart_Tool_优化方案.md`、`docs/方案/测试文件分析与规则清单.md`、`docs/方案/待确认问题_初版答案.md`、`代码评审日志.md` 里的品牌名换成 DemoBrand / DemoFishBrand（钓具品牌），`代码评审日志.md` 里一个原样本 MSKU 换成 DEMO-MSKU-A；`test_s2fix_hs_category.py`、`test_s2fix_mcp_lock.py` 内联的钓具品牌名同样换成 DemoFishBrand。仍未改：金样、默认配置、模板、产品目录、test1、_sta_compare.json、packaging、scratch 和读真实文件的 3 个测试（原因见 S9-step2）。git 历史仍含真实值，是否改写由用户决定。
- 测试：新增 `backend/test_s9step2fix2_price_parse.py`（68 条：合法 / 非法写法表、无效原因、map_listing_row、_valid_price、定时同步对 12,5 / 1.299,00 / 1e30 / 40 个 9 / 1e20 / 1e-3 / 0.004 只跳过该行且不重试、单行异常只跳该行、手动预览显示原值且不可勾选、CSV 导入预览 200 + 确认 422 带行号原值、意外错误 422 不含类名、千分位正常、降幅文字边界、price_info 标志）和 `backend/test_s9step2fix2_m4_ratelimit.py`（18 条）；`test_s9step2_preview_price.py`、`test_s9step2fix_price_e2e.py` 的标签断言按新用词更新。全量 918 passed。
- UI 截图在提交后用提交的代码生成（临时 FBA_APP_DATA_DIR + mock 领星示例数据 + 假 Key，只截预览面板）：`%TEMP%\fba_s1\ui_shots\s9step2fix2_preview.png`、窄屏 `s9step2fix2_narrow.png`。
- 版本号仍 V3.1；D-01–D-13 未改。PC 上没用真实 Key，没调真实领星接口，没碰真实 app_data / sessions。

S9-step3（tag `s9-step3`；s9-step2-fix2 复评 99.1 通过，报告 docs/评审报告/S9_step2_评审_v3.md 随本次提交，提交前已扫真实值 0 处）。评审轻微项：
- #1 Excel/CSV 导入确认写入：只跳过价格无效的行，合法行照常写入；响应里 `skipped`（行号、字段、原始值、原因）和 `skipped_rows` 列出被跳过的行。整份文件没有一行可写时才返回 422（“没有可写入的行，整个文件未写入：…”，detail.errors 带行号和原值）。
- #2 价格舍入：`parse_price` 改用 ROUND_HALF_UP，和报关（`customs_package.money_half_up`）、发票（`invoice_rules.round2`）一致："12.005"→12.01，"0.005"→0.01，"0.004" 仍判无效（四舍五入到分后为 0）。Excel 数字单元格直接按数值判断，不再误报“科学计数法”。
- #3 重复提示：同一个坏值（字段 + 原值 + 原因相同）在预览警告和同步差异里只出现一次。
- #4 鉴权判定：信封、HTTP、JSON-RPC（含 isError）三条通道统一用 `lingxing_mcp_client.is_auth_failure(code, msg)`。规则按顺序：以「MCP Key无效或已失效」开头 → 鉴权失败（优先于限流词）；含 禁用 / 封禁 / disabled / banned → 账号不可用，归鉴权类、不重试；401 → 鉴权失败；403 且不含具体限流短语 → 鉴权失败；业务码 102 且含“Key无效” → 鉴权失败；其余（含 429、普通限流）可重试。限流词去掉宽泛的“频繁”，只认具体短语：rate limit / too many requests / throttl / 请求过于频繁 / 请求太频繁 / 访问太频繁 / 访问过于频繁 / 调用过于频繁 / 调用太频繁 / 操作过于频繁 / 限流。删掉无用的 AUTH_CODES。
- #5 UI（`lingxing-preview-panel.tsx`）：(h) 去掉“（D-12）”，写“高于售价：促销期按正常价申报”，来源写“正常价 · 领星常规价 / 正常价 · 近 90 天非促销价”，不再括号套括号；(i) 领星常规价高于售价但差距不到 5% 时，加一句“售价只比领星常规价低 N%，未超过 5% 促销阈值，不算促销”，顶部说明同步改为“售价比正常价低 5% 以上才算促销，按正常价申报；低不到 5% 不算促销，按售价申报”；(j) 降幅一律一位小数（向下取），“低”后加空格；实际 >5% 但向下取到 5.0 时显示“低约 5.0%（已超过 5% 阈值）”；(k) 面板 420px 宽不横向溢出，右侧标签和长 SKU 可折行。
- #6 价格上限可配置：沿用现有设置机制，参数 `price_max`（美元，出厂 100000）。改的位置：网页“设置 → 参数”里的“价格上限（美元，超过视为无效价格）”，或 `app_data/config/user_settings.json` 的 `parameters.price_max`；出厂值在 `backend/config/user_settings.default.json`。填非数字、≤0 时退回 100000。**数值待用户确认（见 HANDOFF §6）**。
- SKU 大小写统一（业务项，详见下一节“SKU 大小写统一”）。
- 测试：新增 `backend/test_s9step3_review_fixes.py`（54 条：部分写入 + 全坏 422、HALF_UP 与报关/发票一致、去重、鉴权三通道一致与调度不重试、UI 文案、price_max 配置与回退）和 `backend/test_s9step3_sku_case.py`（19 条：大小写混写、全角、首尾空白、ß、只差大小写冲突、旧库重复不合并、写入落到原有行、删除只删匹配的一条、列表 API 冲突提示、DELETE 409、报关冲突警告、领星同步、fnsku、主数据标志、Excel 编辑重复）；`test_s9step2fix2_price_parse.py`、`test_s9step2_preview_price.py`、`test_s9step2fix_price_e2e.py` 按新文案 / 新导入行为更新。
- 版本号仍 V3.1；D-01–D-13 未改。PC 上没用真实 Key，没调真实领星接口，没碰真实 app_data / sessions。

#### SKU 大小写统一（S9-step3）
- **结论**：存储保留原始写法（显示、导出也用原始写法）；匹配一律走 `backend/fba_tool/sku_keys.py` 的 `sku_key`（NFKC 全角转半角 + 去首尾空白 + casefold）。原样相同的优先；没有原样相同、规范键只命中一条就当作同一个 SKU（写到库里原来那一行，不新建）；命中多条只差大小写 / 全角半角的 → 报冲突（`SkuCaseConflict`），不静默任选、不写入、不自动合并。
- **亚马逊官方依据**：Buy with Prime 官方开发文档《Best practices for catalogs》：“Amazon SKU is a product identifier from your Seller Central or Vendor Central catalog… Both SKU and Amazon SKU values are case-sensitive.” https://documents.buywithprime.amazon.com/bwp-api/docs/best-practices-for-catalogs 。Seller Central 帮助页需要登录，没找到公开页面写明。第三方：Feedvisor（https://feedvisor.com/university/sku/ ）等也说区分大小写；但 BQool（https://support.bqool.com/hc/en-us/articles/360005008594 ）说它自己的系统不区分大小写。所以：亚马逊那边 "ABC" 和 "abc" 可以是两个不同的 SKU；本工具不替用户合并，同一店铺里只差大小写的两个 SKU 一律提示人工确认。
- **改前不一致的地方**（rg 全仓排查）：`product_master.sku` 主键按二进制比较；`get_product_by_sku` / `get_products_by_skus` / `delete_product_by_sku` 用 `COLLATE NOCASE`（只管 ASCII、不管全角，多条时 fetchone 任取一条，删除会一次删掉所有大小写变体）；`upsert_product` 用 `ON CONFLICT(sku)`（二进制）→ 只差大小写会新建重复行（S8_测试评审_v2.md 第 93 行已指出）；`set_product_fields` / `mark_field_sources` / `get_field_sources` 用 `WHERE sku=?` 二进制 → 只差大小写时静默什么都没写；`get_products_by_skus` 以库里写法为键，调用方用输入写法取不到（代码评审日志.md 第 170 行 P2）；`fnsku_resolve` 区分大小写；发票 / 报关的 map 用 `.upper()`（不管全角）；领星同步 / 预览、`product_edit` 用 `.lower()`；`shipment_cross_check` 用去空白 + upper。
- **改了哪里**：`master_db`（连接注册 SQL 函数 `sku_key`；新增 `resolve_stored_sku`、`list_sku_case_conflicts`、`sku_conflicts_for`；读取冲突时返回 None 并记日志；upsert / 删除先匹配到原有那一行）；`product_fields`（写字段、记来源先匹配原有行）；`lingxing_sync` / `lingxing_preview`（领星本批内只差大小写的多个 MSKU、或本地库里已有冲突 → 差异 `sku_case_conflict` + 预览放到“待人工确认”、默认不勾；确认写入遇冲突跳过）；`lingxing_scheduler`（自动写入遇冲突记差异、继续下一条）；`customs_package`（报关包冲突警告 `sku_case_conflict`，重量表按统一规则取）；`invoice_table` / `invoice_etl` / `invoice_automation` / `invoice_workflow_fill`、`fnsku_resolve`、`product_edit`、`shipment_cross_check` 改用统一函数；产品库列表 API 返回 `sku_case_conflicts`，网页产品库顶部琥珀色横幅提示；DELETE 遇冲突返回 409。
- **旧数据**：库里已有只差大小写的多条记录**不自动合并**，只在产品库横幅、领星同步差异、预览“待人工确认”、报关包警告里提示，由用户改名或删除多余的一条。
- **golden 不受影响**：13 例 2557 格，通过 2533、已知差异 24、失败 0（与改前相同）。已知差异里“104CM vs 104cm”来自旧产品目录 `product_catalog`（仍按 upper 键，未接入本次改动，不影响金样）。
- **保持原样（已核对）**：`fba_compliance` 的 sku_map（同一来源数据内部对照）、`worker_packing_export`、`product_catalog` 旧目录、`lookup_by_fnsku`（按 FNSKU 查，不是 SKU）。

S9-step4（决策 D-14 至 D-18 见 docs/用户决策记录.md；D-01–D-13 未改）：
- D-14：价格上限 100000 美元，**用户确认 2026-10-17**（改的位置同 S9-step3 #6）。
- S9-B 提示（D-15）：新列 `last_nonpromo_origin`（self_first / confirmed / legacy）。`_track_nonpromo` 记非促销价时：当时没有任何参照 → self_first，有参照 → confirmed；升级前的记录和旧版 exe 写的记录是 legacy（列默认值）。没有有效领星常规价、90 天内也没有来源不是 self_first 的记录时，预览和同步差异（`price_history_missing`）显示琥珀色「无促销前历史价，申报价可能偏低，请人工确认」；只提示，不改申报价，不建议 list_price。预览里可人工确认正常价（默认是将要申报的价，可改，`POST /api/master-data/sku/{sku}/confirm-normal-price`）：parse_price + 价格上限校验 → 写成 confirmed，记审计日志 `app_data/logs/price_confirm_audit.log` → 提示消失；新品要先写入产品库。价格不变的后续同步不会把 self_first 变成 confirmed；促销超过 90 天、记录滚出窗口后提示会回来。
- 领星常规价采集时间（D-16）：核对结果——采集时间早已有：`product_fields.NEW_COLUMNS` 的 `regular_price_at`，`set_product_fields` 里 `sets["regular_price_at"] = _now()`；但 `normal_price()` 以前没对常规价套 90 天窗口。现在常规价只在采集后 90 天内有效，超期回退近 90 天非促销价；`_track_nonpromo` 同样只用窗口内的常规价。没有采集时间的旧值，迁移时补成迁移时间。预览“本地旧值”旁显示采集日期，超期写「采集超过 90 天，不作为正常价」。
- 数据库迁移：`ALTER TABLE product_master ADD COLUMN last_nonpromo_origin TEXT DEFAULT 'legacy'`（只在列不存在时加）+ 只补空的 `regular_price_at`；重复执行结果不变；PRAGMA user_version 不变（仍 3）。核对：① 测试 `test_migration_old_schema_upgrade`（把临时库改成旧结构再升级、跑两次、模拟旧版 exe 的 INSERT/UPDATE/SELECT *）；② 用 s9-step3 的旧代码（git archive 到临时目录）建示例库 → 新代码升级两次 → 旧代码再打开读写：旧记录 origin=legacy、旧常规价补了采集时间、新记录 self_first、旧代码读写和申报价正常。真实 `backend/fba_master.db`、真实 app_data 没碰。
- 同步差异：新增 `frontend/src/lib/diff-kinds.ts`（差异中文名 + 琥珀色种类：price_history_missing / sku_case_conflict / price_invalid），产品库页和定时同步记录两处同用。
- 测试：新增 `backend/test_s9step4_history_hint.py`（23 条：三态、预览与差异、self_first 仍参与 D-12、legacy、滚出窗口、人工确认 API（默认价、改价、12,5 / 0 / 200000 / 空 / 1e3 → 422、404、409、价格上限可配置）、审计日志、确认后提示消失、常规价 89 / 91 天、预览采集日期与超期、迁移）。
- 截图归档：含真实 SKU 的 3 张（`_raw_fix2_wide.png`、`_raw_fix2_narrow.png`、`s9step2fix_full.png`）从 `%TEMP%\fba_s1\ui_shots\` **移动**到 `%TEMP%\fba_s1\archive\screenshots_real\`（没删）。移动前核对：`git log --all` 按文件名 0 条、当前未跟踪；仓库所有 dist zip（含 V3.1）里都没有这 3 个文件。移动后 3 个文件、大小和 SHA-256 与移动前一致，原位置已无。
- 发现并处理：开发模式下 `ensure_app_data_layout` 会从 backend/ 旧路径把 `fba_master.db`、`config/sessions` 复制进新的 app_data（这就是以前整页截图带出真实 SKU 的原因）。S9-step3 截图时两个临时目录因此带了真实库副本，已移到 `%TEMP%\fba_s1\archive\ui_tmp_with_real_copy\`（没删，建议用户确认后自行删除）；截图脚本改为不迁移旧路径，产品信息表用示例。以前的 `ui_appdata_002937`、`ui_appdata_013939` 两个临时目录同理可能带有副本，未动。
- UI 截图（提交后用提交的代码；临时 app_data，产品信息表为示例、不迁移 backend/ 旧路径；mock 领星示例数据 + 假 Key；只保留面板）：S9-step3 `%TEMP%\fba_s1\ui_shots\s9step3_preview.png`、`s9step3_420.png`（420px）、`s9step3_conflict_banner.png`（产品库大小写冲突横幅）；S9-step4 `s9step4_preview.png`、`s9step4_420.png`（含琥珀色 S9-B 提示和“确认为正常价”）。整页原图只含示例数据，在 `ui_shots\sample_only\`。420px 截图发现“本地旧值 · 日期 采集”整段不换行会溢出，已在 s9-step4 之后的提交里把价格和来源拆成两段（tag `s9-step4-fix1`）。
- 版本号仍 V3.1；D-01–D-13 未改。PC 上没用真实 Key，没调真实领星接口，没碰真实 app_data / sessions / backend/fba_master.db。

#### 仓库对外共享与历史里的真实值（S9-step4，D-18）
- **本仓库不对外共享**。需要给外部看时，另建一个脱敏副本仓库（只放脱敏后的当前文件，不带历史），原仓库和历史不改写。
- 发布用的便携版 zip 不含 `.git`：`dist\` 和 `backend\dist\` 下全部 zip（V1.1–V3.1 等 14 个，以及打包内部的 base_library.zip）逐个核对，`.git` 条目 0。
- 整页截图一律用临时 app_data，并且产品信息表也换成示例、不从 backend/ 旧路径迁移；只保留面板截图。
- git 历史里引入或删除过真实值的提交（`git log --all -S`，扫描值与 desens_scan 相同的 26 个；只列提交号和值的类型，不写值）：

| 提交 | 日期 | 值的类型 |
|---|---|---|
| 368b5ba、38dc1c5、3d2cbda、d651ecd、726cdd0、f18bb24、644883b、7e7d845、042923d | 2026-10-16 | 品牌 |
| c9e6993、e550794 | 2026-10-16 | sid、品牌 |
| 0242853、70c541a | 2026-10-16 | FNSKU、ID、品牌 |
| bb7397e、3bcf223、eb99139 | 2026-10-16 | FNSKU、ID |
| 314d2c5 | 2026-10-16 | ASIN、FNSKU、ID、sid、store_id、品牌 |
| b249fb3 | 2026-10-16 | 品名、品牌 |
| 8404f4b | 2026-10-16 | ASIN、FNSKU、ID、MSKU、sid、store_id、品名、品牌 |
| f1acde3 | 2026-10-16 | ASIN、FNSKU、ID、MSKU、品名、品牌 |
| 5ba9d06、69d0d21 | 2026-10-16 | ASIN、FNSKU、ID、MSKU、品牌 |
| 7b00da1 | 2026-10-16 | ASIN、FNSKU、ID、MSKU、sid、store_id、品名、品牌 |
| 0c5e0df | 2026-10-17 | ASIN、ID、sid、store_id、品名、品牌 |
| 9793488 | 2026-10-17 | FNSKU、ID、品牌 |

### S9-step4-fix2 — tag `s9-step4-fix2`；开发 / 测试环境不再做旧数据迁移
- 问题（测试 Bot 认定，必须修，至少中等）：`backend/fba_tool/app_paths.py` 的 `_migrate_legacy_data()` 由 `ensure_app_data_layout()` 无条件调用（调用方：`main.create_app()`、`run_app.py`、`conftest.py` 会话 fixture、`scripts/smoke_e2e.py`、`exporter_profiles` / `forwarder_registry`）。开发模式下来源是仓库根和 `backend/`，会把真实 `backend/fba_master.db`（缺失时）、`backend/config/sessions/` 全部文件（逐个补缺）、`backend/templates/`、`backend/config/` 下的旧用户配置（当前仓库里没有）复制进当前 app_data，**设了 FBA_APP_DATA_DIR 的临时目录也照复制**。sessions 里是装箱 / 发票任务的工作数据，按键名看没有领星凭据；领星密钥在 `app_data/config/lingxing.json`（只存密文），不在迁移名单里。
- 修法：新增 `legacy_migration_decision()`，只有允许时才调 `_migrate_legacy_data()`：
  1. 设了 `FBA_APP_DATA_DIR` → 一律不迁移；2. 测试环境（pytest，或 `FBA_NO_BROWSER`）→ 一律不迁移；以上两条显式开关也压不过；
  3. `FBA_ALLOW_LEGACY_MIGRATION=1` → 迁移（开发模式手动升级旧数据用）；
  4. 打包版 exe（frozen）→ 照旧迁移：老用户把新版解压到旧版目录时，exe 旁的 `fba_master.db`、`config/sessions/`、`config/*.json`、`templates/` 搬进 `<exe 目录>/app_data/`，已有的不覆盖。这是正式版的升级路径，保持不变；`FBA_ALLOW_LEGACY_MIGRATION=0` 可关掉。冻结模式只看 exe 目录，从来不看仓库 `backend/`；
  5. 开发模式默认不迁移。
- conftest 护栏（`backend/realdata_guard.py`，只用 stat，不读真实文件内容）：会话初始化后、每个测试结束后（全局临时 app_data + 该测试的 tmp_path）、会话结束时，检查临时目录里的 `fba_master.db` 和 `sessions/` 下的文件：与真实来源（`backend/fba_master.db`、`backend/config/sessions/`、仓库根 `app_data/` 的库和会话）同名同大小同修改时间，或者修改时间早于本次测试开始，就判失败。
- 新测试 `test_s9step4fix2_legacy_guard.py`（16 个）：设了 FBA_APP_DATA_DIR 时不迁移（开关=1 也不迁移）；决策表 6 种；FBA_NO_BROWSER；开发模式默认不复制；模拟打包版旧目录升级：库、会话、用户配置搬进 app_data，二次启动不覆盖；打包版设临时目录不迁移；开关=0；护栏能认出 copy2 副本和旧文件。
- 修复前留下的副本（只 stat，未读、未动、未删）：清单 `%TEMP%\fba_s1\副本清单_20261017.md`，153 个目录，由用户决定怎么处理。修复后全套检查新建的临时目录里没有副本。
- PC 实测：pytest 1030 passed；e2e 先跑 40；倒序 82 个文件 1030；golden 2557 格 0 失败；冒烟 19/19；tsc 0。

### S9-step4-fix3 — tag `s9-step4-fix3`；按复测报告 `docs/评审报告/S9_step3_4_评审.md`（96.9 未通过）修
- 护栏改为按内容比对（`backend/realdata_guard.py` 重写）：会话开始时对真实来源（`backend/fba_master.db`、`backend/config/sessions/**`、仓库根 `config/sessions/**`、仓库根 `app_data/` 的库和会话）算 SHA-256，只在内存里，不输出、不落盘；扫描临时 app_data 和每个测试 tmp_path 下全部文件，先按大小粗筛再算哈希；SQLite 文件按文件头认，再比 `product_master` 每行 (sku, updated_at) 指纹（测试自己建的库行是运行时写的，不误报）。9 种复制方式各一个测试（copy2 同名、copy2 改名进 sessions、copy2 库改名、copy2 放到 config 下、copyfile（不保留 mtime）同名库、copyfile 同名会话、copyfile 改名放进 sessions/history、copy2 会话放到 sessions 以外、分块流式复制并改名改目录），另有“复制后被 init_master_db 改写”的测试；测试自己建的库、同大小不同内容的文件不误报。输出只有临时目录内的相对路径和原因。smoke 加一项按内容比对（20 项）。
- 小项：`FBA_NO_BROWSER` 不再挡迁移（打包版 exe 照旧迁移）；挡迁移只看 `FBA_APP_DATA_DIR` 和 pytest；开发模式默认仍不迁移。
- SKU 不再用 upper() 当键：`invoice_automation.py`、`invoice_table.py`、`invoice_workflow_fill.py`、`customs_package.py`、`product_catalog.py`、`shipment_parser.py`、`master_local_excel.py` 改用 `sku_keys`（存原写法，匹配先精确、再唯一规范化匹配）。同一票里只差大小写的 SKU 不合并、不互相覆盖，发票结果带冲突警告；本地 Excel 同步遇到大小写冲突整批不写、返回 409；PATCH 冲突 409、找不到 404；产品信息表灌库遇冲突跳过该行。golden 未受影响（0 失败）。
- S9-B 提前消失：升 confirmed 只认两种参照——本次同步有效的领星常规价，或 90 天窗口内 origin 为 confirmed / legacy 的非促销记录；self_first 不作为参照。只有 self_first 时新记录仍为 self_first、提示保留，直到出现真参照或人工确认。申报价算法不变（D-12、D-13）。D-15 下加修订（2026-10-17 两 Bot 修订，用户可推翻），原句保留；D-01..D-14 未改。旧测试 `test_later_sync_with_reference_confirms` 按修订后的 D-15 改为先放 legacy 参照再升级，另加只有 self_first 时保持提示的测试。
- 90 天窗口边界：含等于 90 天，按分钟测 ±1、±5 分钟；采集时间为空视为新鲜。审计日志截断（输入 40 字、备注 200 字）有测试。全坏行 422 列出行号（商品表、箱规表、批量编辑）。
- 前端：「无变化」组里有 S9-B 提示时默认展开，组标题显示「⚠ N 个需人工确认正常价」；人工确认成功后清掉之前的错误提示。
- 产品信息表（D-2026-10-17-19，用户授权两 Bot 选定，用户可推翻）：真实 `backend/templates/产品信息表.csv`（内部真实产品数据）`git mv` 到 `archive/private_data/产品信息表.csv`（不删、不改历史、仍跟踪）；新增 `backend/templates/产品信息表_示例.csv`（表头 + 2 行 DEMO）；打包 spec 改为逐个列模板并排除真实产品信息表；出厂模板补进 app_data 时也跳过；自动查找产品信息表时跳过「示例」文件。没有真实表时：启动灌库跳过、运行时只读 SQLite，程序照常运行。
- 新测试 `backend/test_s9step4fix3.py`（52 个）、`backend/test_s9step4fix3_catalog.py`（7 个）。
- PC 实测：pytest 1090 passed（正序 104 s，fix2 时 1030 / 107 s，护栏未明显拖慢）；e2e 先跑 40；倒序 84 个文件 1090；随机顺序（跨文件打乱用例，种子 20261017）1090；golden 13 个用例 2557 格（通过 2533、已知差异 24）0 失败，与 fix2 相同；冒烟 20/20；tsc 0。未打包，版本号仍 V3.1。

  共 25 个提交（含脱敏时删掉真实值的提交）。s9-step3（db66207）、s9-step4 不在其中。是否改写历史由用户决定（本次未改）。

### S9-step5（S9-final 收尾）— tag `s9-step5`；按复测报告 `docs/评审报告/S9_fix3_评审.md`（99.5 通过）的小项 + 用户 14:15 ET 指示（模板和出厂配置去掉真实数据）
- N5 导入大小写冲突：商品表 / 箱规表导入时，库里有多条只差大小写的 SKU、导入行又对不上原样写法 → 预览里直接列为错误（带行号，`conflict_rows`），不进差异；确认写入时只要有冲突整个文件不写（422，带行号）。写入改为一个事务（`master_db.batch_transaction()`：块内 `_connect()` 共用一个连接，正常结束一次提交，中途异常整体回滚）。
- N6 人工确认正常价：成功提示用独立 toast id（`confirm-normal-price-ok-<sku>`），不会被清错误提示的 dismiss 吞掉。
- N7 护栏补测：仓库根 `app_data/` 的库和会话算真实来源；文件内容 / mtime 变了会重查；会话结束扫描（全局临时 app_data + 本次 tmp_path）发现副本让整次测试失败。「正好 90 天」改为固定当前时间（`product_fields._utcnow`），不再留 2 秒余量。
- N8 决策记录：D-19 标注改为「用户 2026-10-17 授权两 Bot 选定，授权由开发方 Bot 转述，用户可推翻」；D-15 修订说明与代码一致（参照为「有效的领星常规价（90 天内采集）——本次同步给的或库里已有的都算」）；D-15 原文和 D-01–D-14 未改。新增 D-20 记录本次打包内容规则。
- 模板和出厂配置去真实数据（D-20）：打包改为白名单 `packaging/release_manifest.py`（spec 只用它）。纯格式模板用原件；报关资料模板、琪珞 T6、德速 T3 和 5 个出厂配置用 `packaging/release_templates/` 下的版本，由 `packaging/build_release_templates.py` 从原件生成（不含真实值，要替换的值按位置 / 格式现场学出来，只输出计数）。原件全部留在 `backend/` 给测试和 golden 用。SKU / FNSKU / 亚马逊元数据映射、出口商档案出厂为空；发货录入样表示例行、前端占位符改 DEMO；品牌改参数 `default_brand`（默认空）。**行为变化**：没有保存过出口商档案的用户，导出报关资料前要先在设置里添加出口商。
- 新测试：`backend/test_s9step5.py`（N5–N7）、`backend/test_s9step5_release.py`（白名单、包内容扫描、源码 / 文档扫描、产品图已去掉、配置为空或脱敏、生成器可复现、release 报关模板能导出、工厂表兜底、老用户升级不混入示例、新用户从空开始）；`test_s9step4fix3_catalog.py` 的 spec 用例改为检查白名单。
- PC 实测：pytest 1115 passed（正序 108 s）；e2e 先跑 40；倒序 86 个文件 1115；随机顺序（种子 20261017）1115；golden 13 个用例 2557 格（通过 2533、已知差异 24）0 失败；冒烟 20/20；tsc 0。版本号仍 V3.1（下一步 V3.2）。

### S9 收尾：V3.2 — tag `v3.2`（同时算 s9-final）
- **用户决定在此停止，S10 Figma 改版已取消。** S9 到此结束，整个项目停止开发；如以后要继续，从 tag `v3.2` 开始。
- 过程：S9-fix3 复测 99.5 分通过（`docs/评审报告/S9_fix3_评审.md`）→ S9-step5（tag `s9-step5`，复测小项 N5–N8 + 安装包去真实数据 D-20）→ 本次升 V3.2 并打包。
- 版本号统一改 V3.2：前端顶栏、`/api/health` 新增 `version` 字段（`backend/fba_tool/app_version.py`）、spec、`run_app.py`、`scripts/finish_portable_dist.py`、`scripts/build_standalone.ps1`、`packaging/使用说明.txt`（新增「V3.2 主要更新」）、`用户使用说明.md`（新增「V3.2 新增」）、架构手册、`backend/docs/一键打包指南.txt`、根目录 `使用说明.txt`。新测试 `backend/test_v32_version.py` 核对各处一致。评审报告和更新记录里的历史 V3.1 不改。
- 打包：从 tag `v3.2` 的干净检出（`%TEMP%` 下单独 git clone，不用工作目录）打包，产物 `dist\FBA_Smart_Tool_V3.2_便携版.zip`；旧 zip 全部保留。zip 大小、SHA-256 和解包自检结果写在交付报告里（打包在提交之后，写不进同一个提交）。打包后照例 `git checkout -- backend/templates/forwarders/qiluo.xlsx`。
- 留给用户决定（都没动）：`%TEMP%\fba_review_s9s4fix3\edge_prof\` 可能有测试员浏览器的 Microsoft 登录信息，建议用户自己删；`%TEMP%\fba_s1\副本清单_20261017.md` 里的 153 个旧临时目录；`archive/private_data/产品信息表.csv` 和 `backend/tests/fixtures/product-info/` 下的内部产品表仍被 git 跟踪（不打包）；`backend/_sta_compare.json` 含真实值（不打包）；git 历史里含真实值的提交（D-18，未改写）。
- PC 实测（v3.2 提交前）：pytest 1119 passed（正序 109 s）；e2e 先跑 40；倒序 1119；随机顺序（种子 20261017）1119；golden 13 个用例 2557 格（通过 2533、已知差异 24）0 失败；冒烟 20/20；tsc 0。

### 10.0 S8 收尾修复
1. **S8-fix2（S8 收尾评审 docs/评审报告/S8_收尾评审.md）：N1 `product_fields` 新增 `_informative_regular`：regular_price ≤ 当前售价视为“无信息”，`normal_price` 回退到近 90 天非促销价；`_track_nonpromo` 判断非促销时用同一规则，常规价无信息就和上次记录的非促销价比，促销价不再覆盖它（16/16 → 12/12 现在按 16 报并提示 promo_price_not_used，last_nonpromo 仍为 16）；新增 `backend/test_s8fix2_dec12_real_sample.py`（真实样本形态单元 + e2e 共 6 条）。N2 MCP 三元工具已在文档与 docstring 标注，客户端改造留 S9。N3 测试基线统一 681。N4 HANDOFF 申报价口径改准。N5 invoice_export 头注释改为 5 个适配器。D-01 至 D-12 未改，版本号仍 V3.1。**
2. **S8-fix3（S8 收尾评审 v2 99.3 通过后的 3 条，报告 docs/评审报告/S8_收尾评审_v2.md）：N6 当时把申报正常价也改成取较大值，**违反 D-12 原文，已在 s8-fix4 按方案 A 改正**（见下条）；`backend/test_s8fix3_dec12_max_ref.py` 新增于此。N7 `backend/conftest.py` 加 session 级 autouse 建表（ensure_app_data_layout + init_master_db），修复 e2e 测试排在 test_s8_fix.py 之前时 no such table；产品行为未改；两文件倒序、全量 70 个文件倒序都全过。N8 本文件 §0 更新、fix2/fix3 说明移到 §10.0。版本号仍 V3.1，未打 s8-final。**
3. **S8-fix4（S8 收尾评审 v3 98.9 未过，报告 docs/评审报告/S8_收尾评审_v3.md）：N9 D-12 口径（方案 A）：取值顺序来自用户的决策 D-12（决策记录原文，未改）——申报用的正常价先用常规价 regular_price，没有时才用近 90 天非促销价；售价比正常价低 5% 以上才算促销。另有两条是 **Bot 选定的参数，Christopher 2026-10-16 已确认（D-13）**：① regular_price 高于售价才算有信息（≤ 售价视为没给）；② max(有效常规价, 近 90 天非促销价) 只用来决定是否覆盖历史非促销价，本次售价 ≥ max×0.95 才更新，否则保留历史值。 `normal_price` 恢复常规价优先，`_track_nonpromo` 保留 max 判断。测试 `test_s8fix3_dec12_max_ref.py` 按 D-12 改正并扩充为 8 条：历史 16、售价 12、常规价 12.5 → 按 12 报、不提示、历史 16 保留；先 25 后 20/20.5 → 按 20 报、不提示；先 25 后 18/20 → 按 20 报并提示。N10 先 commit + tag，再重打 V3.1 并启动 exe 验证。版本号仍 V3.1，未打 s8-final。**

### 10.1 S8-fix1 改了什么（针对附录 C 的 S8 复测报告）
1. **N1 严重（D-12 端到端不生效）**：`master_db._row_to_dict` 补读 regular_price / regular_price_at / last_nonpromo_price / last_nonpromo_at，并原样带出以后新增的列。审计：所有产品读取（get_product_by_sku、list_products、按 SKU 批量、全量 map、lookup_by_fnsku）都经过 `_row_to_dict`，没有其他模块直接 SELECT 产品字段。新增 `backend/test_s8fix1_dec12_e2e.py`（mock 领星定时同步 → 写库 → 读库 → 申报价/来源 → 报关包 `promo_price_not_used` → 发票 price_rows）：15.99/19.99 报 19.99；18.98/20 报 20；正好 5% 不算；无常规价 16→12 报 16（来源 lingxing_recent_nonpromo）；超 90 天失效；定时自动写入路径；网页手改 regular_price 生效。去掉修复时 9 条里 7 条失败。
2. **N2 中等（发票重量口径）**：德速 T3 / 琪珞 T6 不再写死单箱重。优先级：面板选择（单箱重/单件重）> 上传货代这票原件、按货件 CSV 的 Σ单箱实重核对判定（`decide_weight_basis`，复用琪珞模板解析的 reconcile）> 货代配置 `invoice_export.weight_basis`；都没有就**留空**并给 `weight_basis_undecided` 提示（含两种口径的示例值）。单件重 = 单箱重 ÷ 该箱件数（混装箱按整箱件数，只写首行）。前端 Step 4.5 加了下拉和上传。新增 `backend/test_s8fix1_invoice_adapters.py`：德速第9批逐格一致（T21=1.7025）；琪珞 T6 第6批 5 票判为单件重、件数/重量一致；第7批判为单箱重、A/F/M/N/O/P 一致；琪珞 T5 按 CSV 汇总核对。
3. **N3**：pyc 取消跟踪（`git rm --cached`，本地文件保留），`.gitignore` 加 `__pycache__/`、`*.py[cod]`。
4. **N4**：6 条弱测试改为行为测试；`test_s4fix_invoice_export` 货代集合改回精确 `==`。
5. **决策记录**：D-12 引用原话、注明参数由 Bot 选可改；D-01 加“已被 D-12 修订”；钓鱼线 HS 说明更正（见 10.3）。
6. 实测（PC）：pytest **681 passed**（基线）；tsc 0；V3.1 重打 206,740,396 字节（11:51 ET）；冒烟 19/19；exe 临时目录启动 /api/health 200、货代 5 家。

### 10.2 未完成 / 待办（完整列表）
- S8 收尾评审 v2：s8-fix2 复测 **99.3** 通过（报告 `docs/评审报告/S8_收尾评审_v2.md`），扣分 N6–N8 已在 s8-fix3 修完；s8-fix3 复测 98.9 未过（`docs/评审报告/S8_收尾评审_v3.md`），N9–N10 已在 s8-fix4 修完，s8-fix4 复测 99.7 通过，s8-fix5 改措辞；**Christopher 2026-10-16 确认 S7/S8 完成，tag `s8-final`**。
- 手动同步的预览只按售价等字段比差异：**常规价单独变化（售价不变）不会出现在预览里**，要等售价变化并确认时才随之写入；定时同步自动写入不受影响。是否要把 regular_price 也列为预览字段，需用户决定（未改）。
- D-12 盲区：首次同步就在促销、且领星没给有效 regular_price（实测都等于售价，即目前总是如此）时无法识别促销，按实时价报且不提示（已在使用说明写明）。可考虑界面提示，需用户决定。
- 实测 regular_price 等于售价：仓库真实样本 `backend/tests/fixtures/lingxing/erp_listing_sample.json` 每行 regular_price 都等于 listing_price，不能用来识别促销。S8-fix2 起 regular_price ≤ 售价视为“无信息”，D-12 实际依靠近 90 天非促销价（last_nonpromo_price），且促销价不会覆盖它。
- ~~待决：是否改用 list_price / history_price 作为正常价~~ 已定（D-13，Christopher 2026-10-16 确认）：**不用**。list_price 是卖家自填、常虚高；history_price 要么空、要么等于 list_price。
- 领星 MCP 只有 help / search / action 三个元工具（业务工具用 toolId，toolType 分 read / write）。**S9-step1 已适配**：客户端每次 action 前先 search 同一 toolId，只放行 toolType=read 且在 READ_ONLY_TOOLS 白名单里的工具；help 列表不全（实测 erp_listing 不在 help 里），以 search 为准。白名单 6 个旧工具名在新接口里都存在、名字不变、都是 read（见 §10 S9 对应表）。
- `last_nonpromo_at` 不在 API 可写字段（设计如此），91 天过期只能在逻辑/数据库层测。
- 琪珞 T5 没有带货件 CSV 的原件，只能结构核对。
- 第6批 T6 原件长宽高（35×35×42）和货件 CSV（60×45×36）不一致，导出取 CSV，未问货代。
- 钓鱼线 HS 不预设（见 10.3）；钓具 HS 预设只做参考，不自动写库（保持“钓具不预置、等报关行确认”原则）。
- `docs/S7_重复文件清单_待用户确认.md` 第 4 条两份工作流文档建议将来合并（需用户确认）。
- Excel 样表导入 `load_from_excel` 旧路径的静默填 0 问题，S1-fix1 已改为报错；若发现残留再修。
- Python 3.9 兼容：PC venv 是 3.9，新代码不能用 3.10+ 语法（`match`、`X | Y` 类型注解需 `from __future__ import annotations`）。

### 10.3 钓具 HS 参考（S8，已核对）
- 中国税则（合肥海关 12360《钓具商品种类及通关税号》与 2026 中国税则一致）与美国 USITC HTS 逐条核对：
  - 钓鱼竿 9507100090（竹/藤等植物材料 9507100010）｜US 9507.10.00.40
  - 钓鱼钩 9507200000｜US 9507.20.40（带线）/ 9507.20.80（其他）
  - 钓线轮 9507300000｜US 9507.30.20（≤$2.70）/ .40（$2.70–$8.45）/ .60（>$8.45）
  - 拟饵 9507900000｜US 9507.90.70
- **钓鱼线不预设一个编码**：美国 HTS **9507.90.20.00**「Fishing line put up and packaged for retail sale」。CBP **HQ 954309**（1994）和 **HQ 956007**（1994，撤销 NY 884900）认定：切成长度、绕在线轴上、装进盒子或吸塑零售包装并明确标为钓鱼线的尼龙单丝归 **9507.90.20**；只绕在线轴上、没有零售包装和鱼线标识的不算“制成钓鱼线”，按材质归 5404（≤1mm 合成单丝）/ 3916（>1mm）/ 5607（编织线）。较早的 NY 882320（1993）曾把成卷鱼线归 5404/3916/5607，后被 HQ 954309 的标准收紧。（s8-docs 已对照裁定原文改正：之前误把 HQ 954309 当成归 5404 的例子。）中国：零售包装成品归 9507900000，第 95 章注释排除“切成一定长度但未制成钓鱼线”的。需按实物逐个确认。
- 接口：`GET /api/master-data/hs-presets?category=fishing`（只读）。

---

## 11. 已知坑

1. **qiluo.xlsx**：每次 `build_standalone.ps1` 后 `backend/templates/forwarders/qiluo.xlsx` 会被改写，必须 `git checkout -- backend/templates/forwarders/qiluo.xlsx`。
2. **重复 CSV**：`backend/templates/亚马逊FBA表.csv` 与 `亚马逊FBA表1.csv` 是同一票；测试只用 `亚马逊FBA表[1-9].csv`。
3. **不稳定测试**：曾经 `test_forwarder_export_idempotent_with_subtotals` 比 xlsx 字节长度（zip 时间戳）偶发失败，S8 已改逐格比较；以后写 xlsx 测试**一律比单元格值**，不要比字节。
4. **冒烟要用 `backend\.venv\Scripts\python.exe`**；系统 Python 3.14 起不来后端（报 /api/health 超时）。冒烟还需要先打包（`backend\dist` 存在）。
5. **HANDOFF 备份习惯**：覆盖 `HANDOFF_交接清单.md` 前先带时间戳备份；原先有两份（仓库一份 + 镜像一份）要一致，新 Bot 只需维护仓库这份。
6. PowerShell 输出中文乱码 → 重定向到文件再用 UTF-8 读。
7. `git am` 会删除补丁里“删除”的文件；取消跟踪 pyc 时先备份本地文件再恢复（S8-fix1 已这样做，备份在 `%TEMP%\fba_s1\s8fix1\pyc_backup`）。
8. 打包 zip 只覆盖同名版本，**旧 zip 一个都不许删**（dist 下有 V1.1–V3.1 多个）。
9. 启动 exe/开发服务器一定带临时 `FBA_APP_DATA_DIR` 和 `FBA_NO_BROWSER=1`。
10. CRLF：仓库有 `.gitattributes`（`* text=auto`），看历史 diff 用 `git diff --ignore-cr-at-eol`。

---

## 12. 下一步：逐条清单（含验收标准）

1. **熟悉与自检**（不改代码）
   - `git log --oneline -5`、`git tag -l "s8*"`：HEAD 应包含 s8-fix1 及之后的交接文档提交；`git status --short` 为空。
   - 跑第 3 节 1)–4)：验收 = ≥918 passed（s9-step2-fix2 实测 918，0 failed）、tsc 无输出、冒烟 19/19、golden 失败 0。
2. **建立评审流程**（见第 13 节）：开一个独立“测试员”会话/Bot，把本文件 + 最新代码给它，按第 13 节模板出报告。
3. **复测 s8-docs**（S8-fix1 已 99.5 过线）：测试员复核文档修订 + 回归；D-12 端到端（经数据库，`backend/test_s8fix1_dec12_e2e.py`）必须覆盖这四个场景：
   ① 领星售价 15.99、常规价 19.99（低 20%）→ 申报 19.99，来源 lingxing_regular，报关包有 `promo_price_not_used` 提示；
   ② 售价 18.98、常规价 20（低 5.1%）→ 申报 20 并提示（正好低 5% 不算促销）；
   ③ 没有常规价，先同步 16、再同步 12（90 天内）→ 申报 16，来源 lingxing_recent_nonpromo；
   ④ 定时同步自动写入路径（trigger=scheduled）同样带上常规价并生效。
   另加：手动同步 → 预览 → 确认（s8-docs 新增）、超过 90 天失效、网页手改 regular_price。验收 = 总分 ≥99。
4. **若 <99**：按报告逐条修，tag `s8-fix2`（以此类推）；每条改动配行为测试（必须经真实读写路径，不能只喂 dict）；跑全套 + tsc + 冒烟 + golden；需要时重打 V3.1（覆盖 V3.1 zip，旧 zip 保留）并临时目录启动一次；更新 HANDOFF（先备份）；向用户汇报 tag、提交、测试数、逐项改动。
5. **≥99 后**：请用户确认 S8（以及 S7）完成，再在 HANDOFF 标 ✅ 并打收尾 tag（如 `s8-final`）。没有用户确认不标完成。
6. **后续需求**：听用户安排；新需求先写方案和验收标准给用户确认，再分阶段做，每阶段走评审。

---

## 13. 评审流程（新 Bot 需自己搭建）

- **角色分离**：开发 Bot 不给自己打分。另开一个“FBA 测试员”会话（或另一个 Bot），只读、不改代码。
- **测试员规则**（原测试员一直这样做）：在 `%TEMP%` 下复制一份仓库副本检出待测 tag；每个探针用独立临时 `FBA_APP_DATA_DIR`；领星一律 mock + 假 Key；前后对真实 app_data 做 SHA256/大小/mtime 快照对比，必须 0 差异；不删除用户文件。
- **评分**：满分 100，及格线 **≥99**。按缺陷严重度扣分（严重约 −5、中等约 −1、轻微 −0.1～−0.5、测试有效性不足/仓库卫生/文档不规范也扣分）；逐项（D1…/N1…）给分和状态。
- **报告模板**（参照附录 C）：一、结论（总分、不及格原因）；各项得分表；二、新发现缺陷（位置、后果、复现步骤、修复建议）；三、规则/决策复核；四、未完成部分（如实写“未测”，不编造）；五、测试质量（弱断言清单）；六、回归与交付物（pytest、tsc、冒烟、golden、包大小/时间、包内敏感物扫描、exe 启动）；七、复现探针位置；八、给开发方的修复清单（按优先级）。
- 报告文件放仓库 `docs/评审报告/`（已有 S1–S8 全部报告，命名 `S<阶段>_测试评审[_v<n>].md`），在 HANDOFF 写上路径和分数。

---

# 附录
附录 A：《用户决策记录》全文（原样）
附录 B：《发票模板清单》（S4a）全文（原样）
附录 C：《S8 复测评审报告》（93.0 分）全文（原样）——S8-fix1 就是针对它修的
附录 D：交接时的 `HANDOFF_交接清单.md` 全文（含各阶段明细、阻塞/待办、更新记录）
附录 E：《深度测评报告 V3.0》（94.3 分）全文——S8 的修复依据

> 附录说明：附录原文里还留着的 `/workspace/...`、“盒子”路径是旧环境（原 Bot 的盒子）的，新 Bot 看不到、也不用管；对应文件已放进仓库 `docs/`（见第 14 节）。

---

# 附录 A：用户决策记录（全文）

## 用户决策记录

记录 Christopher 在对话里给出的决定（原话），各文档、代码、测试引用本文件作为出处。

### D-2026-10-16-01：申报价口径与 Listing 来源

> **已被 D-2026-10-16-12 修订**（2026-10-16 11:04 美东）：领星实时售价处于促销（低于正常价）时改按正常价申报并提示；其余口径不变。见下文 D-12。

- 时间：2026-10-16 06:04（美东时间，UTC-4）
- 来源：与 New Bot 的主对话（用户消息）
- 用户原话：
  > “1.就是按照实时价格报关 2.领星实时售价优先级第一，手工填优先级第二 3.你用MCP能拉取到吗？”
- 书面确认（同一决定）：2026-10-16 06:27（美东时间，UTC-4），Christopher 在 FBA测试员处书面确认，原话：
  > “是，领星价优先、MCP 为主”
- 第 3 条的答复（已给出）：能。Listing 以领星 MCP（erp_listing）拉取为主，Excel/CSV 文件导入作为备用。
- 落地口径：
  1. 申报价按亚马逊实时售价报关。
  2. 申报价取值顺序：领星 `listing_price`（实时售价）> 手填 `declared_value` > 领星 `price` / `landed_price`（兜底）> 旧 `declared_value`（legacy，警告）。领星有值时手填价不覆盖申报价，也不锁定售价；手填价只在领星没有 `listing_price` 时采用。手填价存在但没被采用、且与采用价不相等时，导出一律提示（`manual_price_not_used`；s2-final 起相等不提示）。没有任何价格时阻断导出。
  3. Listing 数据以 MCP 拉取为主（预览确认后写入，手填的非价格字段仍锁定）；文件导入为备用通道。
- 取代：Q4（v6，选 B“手填优先，没填回落售价并警告”）中“手填优先”的部分；方案 §3.2 中“首期以文件导入为准、MCP 放 S5”的说法（S5 只剩定时自动同步）。
- 代码落地：tag `s2-fix1`（优先级、MCP 为主）、`s2-fix2`（未采用手填价一律提示、文档和 golden 同步）。

### D-2026-10-16-02：产品表以 MCP 数据为唯一来源

- 时间：2026-10-16 07:14（美东时间，UTC-4）
- 来源：与 New Bot 的主对话（用户消息）
- 用户原话：
  > “就是要从MCP，你根据数据来做表，以后用MCP拉取更新”
- 落地口径：
  1. 产品表以领星 MCP（erp_listing）拉取的真实数据为唯一来源建表；后续靠 MCP 定期拉取更新（S5 定时同步）。
  2. 领星 Listing 导出文件的列名核对不再做（原方案 “真实字段名要拿用户导出的样本核对【待用户提供导出样本】” 撤销）。
  3. 文件导入保留为备用通道，不再列为待办。
- 补充 D-2026-10-16-01（申报价口径不变）。

### D-2026-10-16-03：产品库支持本地/网页手动修改

- 时间：2026-10-16 07:15（美东时间，UTC-4）
- 来源：与 New Bot 的主对话（用户消息）
- 用户原话：
  > “支持本地化更改，或者手动在网页中修改”
- 落地口径：
  1. 产品库字段可在网页直接编辑并保存到本地库。
  2. 手工改过的值来源记 manual 并锁定，之后 MCP 拉取不覆盖。
  3. 例外：申报价仍按 D-2026-10-16-01，领星 listing_price 优先（listing_price / 币种 / 取价字段不因手改而锁定）。
- 补充（同为 2026-10-16 07:15 美东，与 New Bot 的主对话（用户消息））原话：
  > “也可以通过导出表格，在本地批量化修改”
  4. 产品库可导出 Excel，本地批量修改后导回；导回先预览改动字段，确认后才写入；改过的字段记 manual 并锁定；申报价规则不变（同第 3 条例外）。
  5. 网页编辑与 Excel 导出/导回放在同一步实现（S3 第 0 步“产品库本地编辑”，tag s3-customs 内）。

### D-2026-10-16-04：发票兼容更多模板（S4 范围扩大）

- 时间：2026-10-16 07:16（美东时间，UTC-4）
- 来源：与 New Bot 的主对话（用户消息）
- 用户原话：
  > “发票能兼容更多的模板，我给你的文件夹里面，应该有更多的模板”
- 落地口径：
  1. S4 范围从“SEND + 九方”扩大为：盘点测试文件夹里的全部发票模板（含琪珞等各家货代），做成可配置的模板映射，支持自动识别或手动选择模板。
  2. 先把模板清单（文件名、货代、关键字段差异）写到 docs/发票模板清单.md，按 S4a 执行，S3 做完后开始。
  3. 取代方案 Q6“琪珞不再投入”中关于琪珞发票的部分。

### D-2026-10-16-05：单件装、标准尺寸、23kg 的箱子只提示、不拦截

- 结论：单件装且箱重 > 22.68 kg 的箱子直接算大件，**只提示、不拦截**：> 22.68 kg 提示贴 Team Lift，> 45.36 kg 提示贴 Mechanical Lift（方案 v8 §3.4）。
- 背景：2026-10-16 07:13（美东时间，UTC-4），与 New Bot 的主对话（用户消息）里用户问“你觉得怎么处理好”，New Bot 建议只提示（超过 22.68kg 贴 Team Lift，超过 45.36kg 贴 Mechanical Lift），用户当时没有提出异议。
- 确认：2026-10-16 08:10（美东时间，UTC-4），Christopher 在 FBA测试员处书面确认，原话：
  > “同意，只提示不拦截”
- 落地：fba_compliance.classify_box_weight 单件大件分支；测试 test_fba_rules_s1e.py、test_s3_customs_fishing.py::test_single_item_standard_23kg_only_notice_v8。

### D-2026-10-16-06：拿不准的规则先查权威资料

- 时间：2026-10-16 08:11（美东时间，UTC-4）
- 来源：与 New Bot 的主对话（用户消息）
- 用户原话：
  > “不确定的东西，你就搜索权威资料”
- 落地口径：
  1. 拿不准的规则先查权威资料再定，例如海关总署报关单填制规范、亚马逊 Seller Central 官方文档。
  2. 在文档里注明查到的出处（链接或文件名、条款）。
  3. 只有用户自己的业务数据（例如哪家货代、具体某一票的数据）才列出来请用户确认。

### D-2026-10-16-07：混装多品名的毛重/净重分摊（按 D-06 查权威资料）

- 时间：2026-10-16（美东时间，UTC-4），S3-fix2；【改 s3-final】08:35 按 S3 测试评审 v3 把第二十四条、第三十六条的转述改成和原文一致。
- 查到的规定：
  1. 海关总署公告 2019 年第 18 号《中华人民共和国海关进出口货物报关单填制规范》（附件规范）：件数（第二十四条）、毛重（第二十五条）、净重（第二十六条）是报关单**表头**栏目。商品行（第三十三至四十三条）没有毛重/净重栏目；第三十六条“数量及单位”分三行填报：法定第一计量单位及数量、法定第二计量单位及数量（无法定第二计量单位的为空）、成交计量单位及数量。第三十六条（四）只列了五种特殊情形（例如“使用不可分割包装材料和包装容器的货物，按货物的净重填报”），不是普遍规则。https://www.gov.cn/zhengce/zhengceku/2019-11/04/content_5448488.htm （该页只有公告正文，规范附件条文据 S3 测试评审 v3 对全文转载的核对）
  2. 海关总署公告 2024 年第 30 号（2024-04-10 起）修改第 25 条毛重、第 26 条净重：毛重 = 货物及包装材料重量，净重 = 毛重扣除外包装、即货物实际重量；单位千克，不足 1 千克的精确到小数点后 2 位。http://www.mofcom.gov.cn/zcfb/zgdwjjmywg/art/2024/art_3852cc22860442398ced2db7b5d112d7.html ；http://beijing.customs.gov.cn/manzhouli_customs/2024-10/22/article_2026060523434556513.html
  3. 第二十四条件数原文：“填报进出口货物运输包装的件数（按运输包装计）……不得填报为零，裸装货物填报为‘1’。”（原文只写裸装，没有“散装”。）上海海关解读同此：http://shanghai.customs.gov.cn/shanghai_customs/2026-08/27/article_2026082802531311784.html
- 结论（如实写）：**规范只要求表头填件数、毛重、净重（不足 1 kg 保留 2 位小数），没有规定一票混装多品名时装箱单逐行毛重/净重怎么分摊，分摊为实现方案。**
- 实现方案：箱数全部记第一行（其余行 0，合计 = 件数）；毛重、净重按件数比例用最大余数法分到 0.01，各行不为负、合计 = 表头；分到 0 的行出 zero_weight_line 提示，不拦截。多票合并时每票先算自己的行重量，再按品名 + HS 相加。
- 不需要用户确认（不是用户业务数据）；如果货代/报关行另有要求，再按其要求调整。

### D-2026-10-16-08：数据里可能有错，由开发方交叉核对后按正确的做

- 时间：2026-10-16 08:37（美东时间，UTC-4）
- 来源：与 New Bot 的主对话（用户消息）
- 用户原话：
  > “你自己评估，我给你了很多数据，里面可能有错的，所以你严谨的分析完，按照正确的去做”
- 落地口径：S4 的 4 个待确认点（T3/T4/T5 货代归属、琪珞“单件实重”含义、第 6 批第 1 票箱数、第 6 批第 5 票仓库）不再等用户。用货件 CSV、报关单、货代运费表、九方数据、文件名、地址库以及数量/重量能否对上来交叉核对，逐条写明证据、结论、可信度；证据确实互相矛盾的，做成可配置项，默认值取证据更多的一方。核对结果见 D-2026-10-16-09。

### D-2026-10-16-09：S4 四个待确认点的交叉核对结论（按 D-08 自行判断）

- 时间：2026-10-16（美东时间，UTC-4），S4。
- 核对用的数据（都是用户测试目录的只读副本，放在 PC %TEMP%\fba_s1\s4src，样例另存 golden）：
  亚马逊货件 CSV（第3/4/6/7/9批 装箱明细）、运费表 `01-J-宠物庭院-FBA运费-入库配置费测算.xlsx` 的「FBA运费-记录」、历史报关单（JUS5HB171 / JUS6HB30 / JUS7HB115）、各批发票文件名、第4批九方入仓单、报关单填制规范第二十四条。

#### 1. T3 / T4 / T5 是哪家货代
- 证据：
  - 运费表按 FBA 号逐票记了货代：第2批 FBA19CG4R0LP/CGD62SD/CGRW2Z4/CGFJPVN/CG7KKSP（第22–26行）、第9批 FBA19GQXZW0N 等（第52–56行）= **德速**；第4批 FBA19F46QLMY/F46KLD1/F4BDYRN/F48J3TQ/F49MKQW（第32–36行）= **九方**；第3批 FBA19DGT9N5J 等（第27–31行）、第5批 FBA19FS81Y33 等（第37–41行）= **琪珞**。这些 FBA 号和 T3/T4/T5 样例文件里的 FBA 号一一对上。
  - 渠道一致：T3 渠道“美西极速达 包税/快船准时达”= 运费表德速行渠道；T5 走货渠道“O-合德/以星统配卡派”= 运费表琪珞行“合德以星卡派”；T4 渠道名称列表与九方 T1 相同，运费表九方行备注有九方 LCL 单号，第4批目录有九方“LCL2605RX78 青岛(黄岛)仓入仓单”。
- 结论：**T3 = 德速，T4 = 九方（旧版下单模板），T5 = 琪珞（旧版单行汇总模板；T6 是琪珞新版）**。可信度：高（运费表逐票记录 + 渠道 + FBA 号三方一致）。
- 更正：盘点清单原来推断 T5“琪珞旧版”正确；T3、T4 原来写“待确认”，现已确定。

#### 2. 琪珞模板（T6）“单件实重”的含义（S4-fix1 按 D-08 重写，2026-10-16，取代原第 2 点）
- 原第 2 点的问题：原结论“默认按单箱重读、对不上时自动换口径”在证据互相矛盾时仍然给了默认值，而且自动纠正不经确认。评审（docs/评审报告/S4_测试评审.md）扣分。本次把测试目录里**全部**琪珞样例重新逐个核对，不再问用户。
- 核对范围：PC 测试目录（只读，复制到 %TEMP%\fba_s1\s4fix\qiluo）里文件名或路径含“琪珞 / 第3·5·6·7·8批 / 发票”的 28 个 xlsx，按内容去重后：
  - T6 结构（有“发票”表和“单件实重”列）的只有 15 份：第6批 5 票；第7批 5 票；第9批目录“发票琪珞作废”5 份（是第7批 5 票的副本，箱号列被改成了“FBA19GVFX5SCU000001-9”这种写法，且 5 份都抄了第7批第1票的 FBA 箱号）。
  - 其余 13 份（第5批 PetCarMat ×5（另 1 份重复）、Petstair ×6、义乌宁波空白模板 ×1）是 T5 结构或其它模板，没有“单件实重”列，不参与本点。
- 逐票对照（货件 CSV Σ单箱重是“真值”；下表“对上”= 和 CSV 相差 ≤2%）：

  | 批次 | 票（FBA） | 单件实重列 | 每箱件数 | 箱号区间 | CSV 箱数 / 单箱重 / Σ | 按单箱重读 | 按单件重读 | 结论 |
  |---|---|---|---|---|---|---|---|---|
  | 第7批 | FBA19GVFX5SC | 6.81/4.97/5.29/6.82 | 4 | 1–29 | 29 箱 / 同左 / 168.23 kg | 168.23 ✔ | 672.92 ✘ | 单箱重 |
  | 第7批 | FBA19GVDVGS5 | 同上 | 4 | 1–23 | 23 箱 / 132.60 kg | 132.60 ✔ | 530.40 ✘ | 单箱重 |
  | 第7批 | FBA19GVFCZ70 | 同上 | 4 | 1–18 | 18 箱 / 104.61 kg | 104.61 ✔ | 418.44 ✘ | 单箱重 |
  | 第7批 | FBA19GVD3PNH | 同上 | 4 | 1–19 | 19 箱 / 109.58 kg | 109.58 ✔ | 438.32 ✘ | 单箱重 |
  | 第7批 | FBA19GVF02NV | 同上 | 4 | 1–26 | 26 箱 / 146.28 kg | 146.28 ✔ | 585.12 ✘ | 单箱重 |
  | 第9批作废副本 ×5 | 同第7批 | 同第7批 | 4 | 同第7批 | 同第7批 | 全部 ✔ | ✘ | 单箱重（只是副本，不算独立证据） |
  | 第6批 | FBA19GDLZ88C / GDN35JP / GDPP6M8 / GDL9K3X / GDJR25Y | 4 | 5 | 1–30（整批箱号） | 每票 6 箱 / 20.0 kg / 120 kg | 按 6 箱：24 ✘ | 按 6 箱：120 ✔ | 单件重 |

  - 第6批有一个陷阱：如果把“1–30”当成 30 箱，按单箱重读 4×30=120 也能凑上 120 kg。但 CSV、预报件数、运费表都是每票 6 箱（第3点），30 箱不成立；所以按 CSV 箱数只剩“单件重”能对上。程序里这种“两种读法数值都能凑上”的情况一律不自动采用（见下）。
  - 单品重：第6批 4 kg/件 × 5 件 = 20 kg = CSV 单箱重（44.09 lb）；第7批 6.81 kg 若是单件重，一箱 4 件就是 27.24 kg，和 CSV 15.01 lb（6.81 kg）矛盾。两批互相独立地指向不同含义。
  - 报关单：JUS6HB30 表头 30 箱 / 600 kg = 5 票 × 6 箱 × 20 kg（与“单件重”读法一致）；JUS7HB115 毛重 639.05 kg，而 CSV 115 箱 Σ = 661.27 kg、按单箱重读也是 661.30 kg——报关单比两者都小 3.4%，说明报关毛重另有来源，只能证明“不是单件重”（单件重读法是 2645 kg），不能精确核对。
  - 运费表「FBA运费-记录」第42–51行：第6批每票第17列 121–123（≈ CSV 120 kg），第7批 238/188/148/156/208，比 CSV 实重大约 40%，像按体积算的计费重；能佐证第6批每票约 120 kg，对第7批不能区分两种读法。
- 结论：
  - 同一个琪珞模板，同一列“单件实重”，第7批按**单箱重**填、第6批按**单件商品重**填——两批证据都很强且互相独立，所以“这一列是什么意思”**没有统一答案**。可信度：两批各自的判断**高**（第7批 5 票逐箱精确相等；第6批 CSV/预报件数/报关单/运费表四方一致）；“以后的琪珞文件会按哪种填”**低**（样本只有 2 批，各占一半）。
  - 因此程序**不默认任何一种含义**：T6 的 weight_meaning 配置为 null（csv_decides）。没有货件 CSV 时不出单箱重，提示“weight_meaning_undecided”，票状态“未核对”；有 CSV 时，只有唯一一种读法能和 CSV Σ单箱重对上才采用（记在 decisions 里，预览可见）；多种读法都能对上且结果不同 → 不采用，列出全部选项让用户选；都对不上 → 提示人工核对。用户也可以在配置或 overrides 里手动指定。
- 同类问题：T3 第9批“单箱重量”也填成了单件重（1.7025 × 4 = 6.81 = CSV 单箱重）。T3 有配置口径（per_box），与 CSV 对不上时现在只**提出建议**改为 per_unit，用户在预览确认（POST /api/invoice-templates/parse 带 accept）后才生效。T3 第2批一行写多个 SKU，“每箱数量”填的是该行合计（55 = 运费表数量），按“一个格子多个 SKU 时数量只能是合计”处理并提示。
- 实现与测试：`backend/fba_tool/invoice_templates.py`（_decide / reconcile_with_csv / apply_corrections）；`backend/test_s4fix_reconcile.py`（第6批 5 票各自由 CSV 判为单件重、第7批判为单箱重、多口径不采用、T6 配置无默认值）。核对脚本 `/workspace/s4/d09p2.py`。

#### 3. 第6批第1票：6 箱还是 1-30
- 证据：发票“预报件数”= 6；货件 CSV 箱子数量 = 6、商品 30；运费表该票数量 30；报关单 JUS6HB30 全批 30 箱 / 150 件（5 票 × 6 箱）。货件 CSV 的箱子名称是 P1-B1 … P1-B30，是**整批** 30 箱的编号，5 票发票都照抄了“1-30”。
- 结论：**6 箱**。“1-30”是整批箱号，不是本票箱数。代码：箱号区间超过预报件数时以预报件数为准（box_count_source=forecast_if_conflict，可配置），并给 box_range_exceeds_forecast 提示。可信度：高。golden 保持 6 箱。

#### 4. 第6批第5票：ACY2 还是 MGE3
- 证据：FBA19GDJR25Y 的货件 CSV 货件名称“…PETBARRIERS -MGE3”、配送地址 Jefferson, GA；运费表第46行 MGE3；报关单备注仓库编码含 MGE3；文件名 MGE3。只有发票 E3 和收件人地址块写 ACY2 / Burlington NJ，和第4票（FBA19GDL9K3X，ACY2）完全一样，是复制第4票时没改。
- 结论：**MGE3**。代码：表内仓库和文件名仓库不一致时默认取文件名（warehouse_prefer=filename，可配置为 sheet），给 warehouse_conflict 提示。有货件 CSV 时（S4-fix1 起）用 CSV 的“配送地址”（Jefferson, GA）对 FBA 仓库地址库得到 MGE3，不用货件名称；和发票不一致时只提建议，确认后才改。可信度：高。golden 保持 MGE3。

#### 另外更正
- 盘点清单 §3 第5点说“T1 九方下单模板没有申报单价列”——不对，T1 第21列就是“申报单价*”（第10批第1票 38.99 等），代码直接读这一列。
- 运费表本身也有错：第7批 FBA19GVFX5SC 计划名写 RFD2、仓库代码列写 VGT2（CSV 和发票都是 VGT2），说明运费表的计划名称不能单独当证据。

### D-2026-10-16-10：琪珞地址库 VGT2 地址纠正（按 D-06 查公开资料）
- 时间：2026-10-16 09:25 美东，用户指示：“琦珞地址库里 VGT2 的地址是‘March ARB’，疑似写错。按 D-06 查公开资料核实。如果确实是错的，就在我们的仓库表里纠正，并注明出处。”
- 核实：Amazon Seller Central 官方公告《Use alternate UPS shipping address for VGT2 fulfillment center in Nevada》（https://sellercentral.amazon.com/seller-forums/discussions/t/b7539e16a4375457927b09d8d6de92b1）写明 VGT2 实际地址（除 UPS 外所有发货）= Amazon.com Services Inc., 6401 Howdy Wells Avenue, Las Vegas, NV 89115；“20701 Krameria Avenue, March Air Reserve Base, CA 92518”是**仅限 UPS 小包**的转运地址。旁证：warehouse.ninja、seabaycargo.com 都是 6401 (E) Howdy Wells Ave, Las Vegas, NV 89115；琪珞表自己的 VGT2-1 行也是这个地址。
- 结论：琪珞表 VGT2 行用的是 UPS 转运地址，作为海运卡派/九方派送地址是错的。可信度：高（亚马逊官方公告）。
- 处理：`backend/config/fba_warehouse_corrections.json` 记录纠错（原值、原因、出处、核实日期），导入琪珞「！」表和读取仓库表时覆盖；不改琪珞原表，不改真实 app_data。

### D-2026-10-16-11：重复文件归档不删除；Step 4.5 发票页暂留待深度评测
- 时间：2026-10-16 10:50 美东，用户批准：重复/过时文件**归档，不删除**。在 PC 仓库用 `git mv` 移到仓库根 `archive/`；`docs/S7_重复文件清单_待用户确认.md` 第 4 条（两份工作流文档）不动，原位保留；任何文件都不删。
- 前提：移动前先确认没有代码、打包 spec、测试或文档引用要移的文件；有引用的不移。归档后不重新打包（测试员正在评测 V3.0 包）。
- Step 4.5 货代发票导出页**保留**，等 FBA测试员深度评测结论后再定去留。
- 执行：tag `s7-archive`；实际移动和未移动的原因记在清单文档文末和 `archive/README.md`。

### D-2026-10-16-12：促销期按正常价申报（修订 D-01）
- 时间：2026-10-16 11:04 美东
- 来源：与 New Bot 的主对话（用户消息）
- 用户原话（Christopher，2026-10-16 11:04 ET 在选项卡片上的逐字回复）：“加保护：促销低于正常价时用正常价报关并提示，然后开始修复”
- 用户同时授权：“正常价”怎么定由我们按现有数据判断，写清阈值和逻辑，配测试。
- **以下阈值和取值顺序是 New Bot 按上面授权自行选定的实现参数，不是 Christopher 本人确认的；他随时可以改**（改 `backend/fba_tool/product_fields.py` 的两个常量即可）：
  - 促销判定阈值 `PROMO_THRESHOLD = 0.05`：实时价 < 正常价 ×（1 − 5%）才算促销；正好低 5% 或更少、以及涨价，仍按实时价报。
  - 非促销价有效期 `NONPROMO_WINDOW_DAYS = 90`：“最近非促销价”只在 90 天内有效。
- 正常价取值（按顺序）：
  1. 领星 Listing 接口的常规价 `regular_price`（同步时与 listing_price 一起写入产品库，来源 `lingxing_regular`）；
  2. 没有常规价时，用近 90 天内最近一次“非促销”实时价 `last_nonpromo_price`（每次同步时，实时价不比正常价低 5% 以上就记一次；来源 `lingxing_recent_nonpromo`）；
  3. 两者都没有：无法判断促销，照 D-01 按实时价报（首次同步就在促销中、又没有常规价时，这是盲区，不提示）。
- 不用划线价 list_price（亚马逊 List Price 多是虚高的建议零售价，实测 38.97 vs 售价 15.99，用它会严重高报）。
- 提示：报关包价格核对给 `promo_price_not_used`（写明实时价和实际申报价），发票价格行和产品库报关提示多一列“促销售价”。手填申报价、旧申报价规则不变（D-01 其余顺序不变）。
- S8-fix1 更正（2026-10-16）：S8 版本里产品库读取（master_db `_row_to_dict`）漏读 regular_price 等 4 列，促销保护在真实链路上不生效；已修复，并补“mock 领星同步 → 写库 → 读库 → 申报价 → 提示”端到端测试 `backend/test_s8fix1_dec12_e2e.py`（15.99/19.99、18.98/20、无常规价 16→12、定时同步路径、手改常规价）。单元测试在 `backend/test_s8_fix.py`（test_dec12_*）。


---

# 附录 B：发票模板清单（全文）

## 发票模板清单（S4a，D-2026-10-16-04）

- 依据：用户决定 D-2026-10-16-04（2026-10-16 07:16 美东，原话：“发票能兼容更多的模板，我给你的文件夹里面，应该有更多的模板”），见 `docs/用户决策记录.md`。
- 盘点范围：用户测试目录 `C:\Users\huang\Desktop\亚马逊-2.Inventory-库存健康 FBA`（只读，用 `%TEMP%\fba_s1\s4a\fp.py` 读表头指纹，没有改动任何文件）。文件名或路径含“发票 / invoice / 箱单 / 下单”的 Excel，排除报关资料和亚马逊 Manifest 模板。
- 结果：**67 个文件，归为 8 套模板**（T1–T8）。货代归属凡是没在文件里写明的，都标了“推断”，需要用户确认。
- 盘点时间：2026-10-16（美东）。

### 1. 总表

| 模板 | 货代（依据） | 文件数 | 批次 / 文件 | 工作表 | 表头行 | 状态 |
|---|---|---|---|---|---|---|
| T1 九方·下单模板（新） | 九方（表内有“是否九方进口商”“交货方式=九方提货”） | 6 | 第10批 第1–5票；`第10批\发票\海运下单模板.xlsx`（空白模板） | 下单 / 参考模板 / 渠道名称列表 / 仓库代码及地址 | 第15行 | 现有代码未支持 |
| T2 SEND Invoice Template | SEND（A1“SEND箱单发票模板”） | 5 | 第13批 FBA19P4N6MM2 / P4NX8HH / P4P3PZC / P4P4CL2 / P4P4MBQ | Invoice Template（表名里有不换行空格） | 第14行（英文说明行第13行） | 已支持（invoice golden 5 份） |
| T3 Commercial Invoice（9810 单证报关版） | 德速（【S4 已核对】运费表第22–26、52–56行，D-09） | 10 | 第2批 第一～五票；第9批 第1–5票 | 发票填写模板 / 填写示例 / 渠道 / 仓库 / 起运地 / 渠道能力 / 特殊产品 / 保险类型 | 第20行 | 现有代码未支持 |
| T4 COMMERCIAL INVOICE 下单模板（旧） | 九方（【S4 已核对】运费表第32–36行 + 九方入仓单，D-09） | 5 | 第4批 第一～五票（WoodenPetstair） | 下单模板 / 参考填写说明 / 渠道名称列表 / 亚马逊仓库代码地址 | 第19行 | 现有代码未支持 |
| T5 “下单模板 黄底信息必填”（单行汇总） | 琪珞（【S4 已核对】运费表第27–31、37–41行，D-09） | 17 | 第3批 第一～五票；第5批 第一～五票；第8批（第5批第二票副本）；老目录第3批 第一～五票；老目录第四批 7箱 | Sheet1 / 渠道 | 第9行（收货人第6–7行） | 第5批只在 golden 输入里用到；导入未支持 |
| T6 琪珞 FBA专线导入模版 | 琪珞（第9批目录名“发票琪珞作废”；“！”表 476 条仓库地址，S2 已导入 fba_warehouse） | 15 | 第6批 第1–5票；第7批 第1–5票；第9批“发票琪珞作废”5 份（第7批副本） | 发票 / 填写示例 / ！ / Sheet1（渠道） | 第13行 | 现有代码只读“！”表；发票部分未支持 |
| T7 义乌、宁波运单下单模板（空白） | 同 T5（表结构相同，空白） | 1 | 老目录 `J-FBA US-第3批\义乌、宁波运单下单模板(1).xlsx` | Sheet1 / 渠道 | 第9行 | 是 T5 的空白版，不单独适配 |
| T8 九方系统导出 箱单发票 | 九方（文件名 LCL 订单号、“九方系统订单号”） | 8 | 测试集九方系统 LCL2607GZ0PA / 26099BD6A / 2609PU1DA / 2609TNKDA / 2610DHTZA / 2610QGXTA / 2610S97BA / 2610UKEKA | Invoice / Packing list | Invoice 第24行；Packing list 第5行 | 已支持（invoice golden 8 份） |

其他：第11、12、14、15批没有发票 Excel（第14批只有 SEND 箱单 CSV，第15批走九方系统 T8）；`ManifestFileUpload_Template…` 是亚马逊装箱上传模板，不是发票，不列入。

### 2. 关键字段差异

| 字段 | T1 九方下单 | T2 SEND | T3 Commercial Invoice | T4 旧下单 | T5 单行汇总 | T6 琪珞 | T8 九方导出 |
|---|---|---|---|---|---|---|---|
| FBA 号 | 唛头列（C） | 表头区“FBA Shipment ID”行 | 参考号 B2 + 明细 Shipment ID 列 | 明细 Shipment ID 列 | B3（FBA单号） | B3（FBA）+ 明细 FBAID 列 | 明细 *Shipment ID 列 |
| 仓库代码 | B3 | 不在表内（取货件 CSV） | 目的仓库代码 B6 | B12 | B7（收货人信息）；第6批第5票 E3 误抄，见 §3 | E3 仓库代码（可能带后缀，如 VGT2-1） | “FBA CODE:” 行 |
| 箱号写法 | `1-2`、`5-33`（区间） | `1-13`（区间） | `1-10`（区间） | `1~3`（波浪号）+ 总箱数列 | 无箱号，只有“件数” | `1,2,3,…`（逗号枚举）；第6批写 `1-30` 与 6 箱不符，见 §3 | 每箱一行（Carton=1） |
| 数量含义 | 总数量（区间合计） | 产品个数（区间合计） | 每箱数量 | 总数量 | 个数（整票合计，多品名用逗号分隔） | 单箱内数量（要 × 箱数） | *Unit 个数（行合计） |
| 申报价字段 | 无单价列（只有带电等），需从产品库取 | R 亚马逊销售原价（Q 列为“德国按售价30%”说明列） | 申报单价（另有投保单价 RMB） | 申报单价（另有采购单价 RMB） | 单个货值 | 申报单价（USD） | *Unit Price + *Total Value |
| 重量 | 货箱重量 = **区间合计** | 单箱重量（× 区间箱数） | 单箱重量 | 有（列位同 T3 之后） | 总实重（整票） | “单件实重”——第7批数值像单箱重，第6批像单件重，见 §3 | Packing list 单箱毛重 G.W |
| 尺寸 | 长/宽/高 三列 | `长*宽*高` 一个格子 | 单箱长/宽/高 | 有 | 单件长/宽/高 | 长/宽/高 | L/W/H |
| HS | 清关编码 | 目的港 HS（M） | 海关编码 | 清关编码 | 海关编码（逗号分隔） | 海关编码（第6批写货代 HS 9403200000，和报关单 6307909000 不同） | H.S. Code |
| 单位 / 每套个数 | 单位、每套个数 | 单位（O）、每套个数（Q） | 单位、每套个数 | 单位、每套个数 | 无 | 无 | 单位、每套个数 |
| 多 SKU | 每行一个 SKU | 每行一个 SKU | 每行一个 SKU | 每行一个 SKU | 一行写多个，用逗号分隔 | 每行一个品名 | 每行一个 SKU |
| 报关信息 | 是否报关 | 无 | 报关监管方式 9810、订单号（如 JUS2MX33） | 是否报关 | 是否单独报关 | 报关类型（合并/不需报关） | 无 |

### 3. 需要用户确认 / 核实的点（不阻塞 S4 开工）

> 【S4 更新 2026-10-16】按 D-2026-10-16-08（用户让开发方自行交叉核对）全部已定，结论和证据见 `docs/用户决策记录.md` D-2026-10-16-09：1) T3=德速、T4=九方、T5=琪珞；2) T6“单件实重”= 单箱重，第6批填成了单件重（由货件 CSV 自动纠正）；3) 第6批第1票 6 箱，“1-30”是整批箱号；4) 第6批第5票 MGE3。第5点写错了：T1 有“申报单价*”列（第21列），直接读取。实现见 `backend/fba_tool/invoice_templates.py`。

1. **货代归属**：T3（第2、9批）、T4（第4批）、T5（第3、5批和老目录）在文件里没写货代名，表里是按渠道表推断的，请确认分别是哪家。
2. **T6“单件实重”**：第7批每箱 4 件填 6.81，和第10批 T1 的单箱重 6.81 一样，看起来是**单箱重**；第6批每箱 5 件填 4，看起来是**单件重**。同一列两种含义，需要确认，确认后才能定换算规则。现在报关 golden（JUS6HB30）按“单件重 × 单箱数量”处理，净重和毛重本来就列为已知差异，不影响比对结果。
3. **T6 箱号**：第6批第1票预报 6 箱，箱序号写的是 `1-30`。
4. **T5 第6批第5票**：发票 E3 写 ACY2，文件名和报关单都是 MGE3。golden 按文件名取 MGE3。
5. **T1 价格**：九方下单模板没有申报单价列，S4 生成时按 D-2026-10-16-01 从产品库取领星售价。

### 4. S4 实现建议（可配置的模板映射）

- 新建 `invoice_template_map.json`（或数据库表），每套模板一条配置：识别规则（表名集合 + 关键表头 + 特征格，比如 A1 “SEND箱单发票模板”、“是否九方进口商”、“！”表）、表头行、列名映射（统一成 FBA / 仓库 / 箱号区间 / 数量 / 数量含义 / 单价 / 重量 / 重量含义 / 尺寸 / HS / 单位）、箱号解析器（`-` / `~` / 逗号）、数量和重量口径（单箱 / 区间合计 / 整票合计 / 单件 × 每箱数量）。
- 自动识别：按识别规则打分，得分唯一最高时自动选，否则让用户在界面上手选；手选结果记在票（shipment_ticket.forwarder）上。
- golden：每套模板至少放 1 份到 `tests/golden/samples/invoice*`。T2、T8 已经在 golden 里；T5 的第5批和 T6 的第6批已作为报关 golden 的输入（`invoice_legacy/`）；T1、T3、T4 在 S4 补。


---

# 附录 C：S8 复测评审报告（全文）

## S8 复测评审报告（tag s8-fix = 325af12，代码提交 b7bcc6e）

- 测试人：FBA 测试执行（Grok Bot）；日期：2026-10-16（美东）
- 对照基线：docs/评审报告/深度测评报告_V3.0.md（V3.0，94.3 分）
- 环境：用户电脑 %TEMP%\fba_s1_verify 副本（检出 s8-fix），backend\.venv Python；每个探针用独立临时 FBA_APP_DATA_DIR（%TEMP%\fba_s8_ad_*）；领星一律 mock + 假 Key `lxFAKE-TESTONLY-000`
- 规则执行：只读、不改代码；原仓库 HEAD 325af12，`git status` 0 改动；真实 app_data 前后快照 54 个文件（含 backend\fba_master.db），SHA256、大小、mtime 都对比过，**0 差异**；没有删除任何用户文件（只清理了我自己建的临时目录，以及冒烟时临时复制进副本的 backend\dist）

### 一、结论

| 项目 | 结果 |
|---|---|
| **总分** | **93.0 / 100（不及格，及格线 ≥99）** |
| 不及格的主要原因 | **D-12 促销按正常价申报在真实数据链路上完全不生效（严重，新缺陷 N1）**：正常价写进了数据库，但读产品时被丢弃，申报价仍按促销价走。30 条新单测只喂 dict，没发现这个问题 |
| 其余 | D1/D2/D3/D5–D15、A/B/C 基本全部修复；660 passed、tsc 0、冒烟 19/19、S4 金标准 0 失败、V3.1 包干净可启动 |

#### 各 D 项得分（每项满分 100）

| 项 | 得分 | 状态 | 简述 |
|---|---|---|---|
| D1 尾数/超发 | 100 | 通过 | 尾数池不再回退自动排箱；assign_tail 能拒绝超量、不在清单的 SKU、越界箱号和 0 或负数；amazon/internal 导出都会拦截超发 |
| D2 仓库判定 | 100 | 通过 | 以 CSV 为准；文件名与 CSV 冲突时警告（X-Routing-Warnings 头）；test1 五票顺序和小计不回归 |
| D3 发票模板识别 | 100 | 通过 | 35 个样本全部识别正确（T1–T8）；T5/T7 按有没有数据自动区分，并给出说明 |
| D4 琦珞/德速发票导出 | 85 | 部分通过 | 能注册、能选、未知货代报“不支持该货代”。**重量口径与原件对不上**（见 N2）；三个适配器没有内容测试或金标准；模板端到端导出被我的数据准备卡住，标为未测（见第四节） |
| D5 字段校验 | 100 | 通过 | 数字字段填非数字返回 400，原值不被覆盖；HS 只接受 8 或 10 位，可带点、空格分隔 |
| D6 未知 SKU | 100 | 通过 | 404；加 ?create=true 才能新建 |
| D7 PDF 输入 | 100 | 通过 | 坏文件、非 PDF、坏 base64、尺寸超出 10–600 mm 或非数字，都返回 400 和中文说明 |
| D8 / B 配置横幅 | 100 | 通过 | 删掉坏的 formulas.json 或 user_settings.json 后，不重启横幅就消失 |
| D9 启动 | 100 | 通过 | FBA_NO_BROWSER 生效；.server_port 写在数据目录下；只绑 127.0.0.1:8002 |
| D10 领星待复核 | 100 | 通过 | 乱码、缺 FNSKU、缺 ASIN 的条目进 needs_review 分组且默认不勾选；定时任务不会自动写入这些条目 |
| D11 导入重复 SKU | 100 | 通过 | 重复行被拒，HS 也会校验（上轮 pD 的现象就是这个预期行为） |
| D12 重复上传 | 100 | 通过 | 同一 CSV 或 PDF 传两次，ok=False，报“❌ 重复上传” |
| D13 | 100 | 通过（未单独写探针） | 本轮没有为 D13 单独写探针；它所在模块未被本次改动触及，全量测试和冒烟都通过 |
| D14 未知货代 | 100 | 通过 | 422，提示“不支持该货代…可选：send、jiufang、qiluo_t6、qiluo_t5、deshu” |
| D15 空导出 | 100 | 通过 | 400，“数据为空：请先生成货代表预览” |
| A（P1）仓库与 CSV 冲突 | 100 | 通过 | 冲突时给出 warehouse_csv_conflict 警告 |
| B（P2） | 100 | 通过 | 同 D8 |
| C（P3）不稳定测试 | 100 | 通过 | test_forwarder_export 改成逐格比较；全量跑了两次都稳定 |
| **D-12 促销按正常价** | **40** | **失败** | 逻辑函数本身正确，但端到端不生效，见 N1 |
| HS 预置 | 98 | 通过 | 编码与公开来源一致；不预置鱼线的理由部分说过头（见第三节） |

总分算法与上轮相同（缺陷按严重度扣分）：N1 严重 −5，N2 中等 −1，测试有效性不足 −0.5，pyc 文件进了仓库 −0.3，D-12 决策记录不规范 −0.2。100 − 7.0 = **93.0**。

### 二、新发现的缺陷

#### N1【严重】D-12 端到端无效：正常价写进了库，但读产品时被丢掉
- 位置：`backend/fba_tool/master_db.py:661-711` 的 `_row_to_dict` 只返回固定字段，**不含 regular_price、regular_price_at、last_nonpromo_price、last_nonpromo_at**。`get_product_by_sku`（:552）和列表接口都经过它。
- 后果：
  1. `resolve_declared_price`（product_fields.py:242）和 `promo_info`（:224）拿到的 master 永远没有正常价，所以促销时仍按领星实时（促销）价申报，也没有提示。`invoice_rules.price_rows`（:210）、报关包同样受影响。
  2. `_track_nonpromo`（:179）里 `existing` 读不到 last_nonpromo_price，“近 90 天非促销价”这个兜底也失效。
  3. 网页手改 regular_price：PATCH 返回 200、库里有值，但不参与申报。
- 复现（探针 pH，临时数据目录，mock 领星）：
  1. mock 返回 P-20OFF：price 15.99、regular_price 19.99，同步并确认两次；
  2. 直接查 SQLite：`product_master.regular_price = 19.99`；
  3. `get_product_by_sku('P-20OFF')` 里 regular_price = None；`resolve_declared_price` 返回 (15.99, 'lingxing')，**期望 (19.99, 'lingxing_regular')**；
  4. 同样失败的还有：P-5.1（18.98 / 20，期望报 20）、P-NP（无常规价 16→12，期望用近期价 16）、定时自动写入的 P-AUTO（15 / 20，期望报 20）。
- 为什么 660 条测试没发现：test_dec12_* 直接把 dict 传给 resolve_declared_price，从没经过数据库读写这一步。
- 修复建议：在 `_row_to_dict` 里加上这 4 列；补一条“mock 同步 → 读库 → 报关/发票价格”的端到端测试。

#### N2【中等】德速 T3 和琦珞 T6 的重量列只按一种口径写
- 代码：`invoice_export.py:240` 德速 T 列 = r.weight（单箱重，而且每个箱号段都写，和注释“混装箱只在首行写”不一致）；`:269` 琦珞 T6 M 列 = 单箱重（引 D-09）。
- 原件对比：

| 原件 | 填的值 | 口径 |
|---|---|---|
| 琦珞 T6 第7批 VGT2 | M14 = 6.81（4 件/箱） | 单箱重，和代码一致 ✅ |
| 德速 T3 第2批 | T21 = 13.25（55 件/箱） | 单箱重，和代码一致 ✅ |
| 德速 T3 第9批 FBA19GQXZW0N | T21–T26 = 1.7025 / 1.2425 / 1.3225 / 1.705…（4 件/箱） | **单件重**；代码会写成约 6.81，**差 4 倍** ❌ |
| 琦珞 T6 第6批（S4-fix1 结论） | per_unit | 和代码不一致 ❌ |

- 结论：货代原件本身口径不统一，代码固定写单箱重，也不提示，第9批这类票会被写错。建议由用户或货代确认口径，或在导出时提示“重量口径”并允许切换。
- 另外：qiluo_t5、qiluo_t6、deshu 三个适配器都**没有输出内容的测试或金标准**（test_d4 只检查注册）。

#### N3【轻微】编译产物进了仓库
b7bcc6e 提交了 `__pycache__/run_app.cpython-313.pyc`、`-39.pyc`、`scripts/__pycache__/step5_user_test_seed.cpython-39.pyc`。建议删除并写进 .gitignore。

#### N4【轻微】新测试里有不少弱断言
详见第五节。

### 三、D-12 规则复核、决策来源、HS 预置

#### 3.1 规则（只测逻辑函数，脱离数据库）
5% 阈值的边界都对：
- 正好 5%（19.00 / 20）不算促销；
- 18.99 / 20、18.98 / 20 算促销；
- 19.02 / 20（4.9%）不算；
- 涨价按实时价；
- 无正常价按实时价；
- 非促销价 91 天后过期；
- 划线价 list_price 不参与。

| 场景 | 结果 |
|---|---|
| 手填申报价（锁定）在促销中 | 仍按 D-01 走领星实时价链路，手填价不覆盖领星价，与 D-01 一致 |
| 首次同步就在促销中、又没有常规价 | 没有任何参照，只能按促销价报，也不提示。这是设计的天然盲区，建议在界面上说明 |

**端到端全部失效（N1）。**

另外，91 天过期在 API 层没法测：last_nonpromo_at 不在可写字段里，返回“不允许写入的字段”。逻辑层由单测 test_dec12_recent_nonpromo_fallback_and_expiry 覆盖。

#### 3.2 决策来源（如实）
`docs/用户决策记录.md` 第 161 行 D-2026-10-16-12：
- 原则（促销按正常价申报并提示）记为“用户指示”，11:04 美东；
- 阈值 5%、90 天、不用 list_price 这些细节，用的是“由我们按现有数据判断”的授权，**是 New Bot 定的，不是 Christopher 本人确认的**；条目里没有引用 D-08；
- 文件头说要记“原话”，但这条没有逐字原话，D-01 有；
- 标题写“修订 D-01”，但 D-01 那一节没有加反向引用。

#### 3.3 与 D-01 的关系
D-01 是“按领星实时售价申报”，D-12 改成“促销时按正常价”。两者有冲突，但 D-12 明确写了修订 D-01，代码注释也写了“修订 D-01”，所以不算矛盾；只是 D-01 原文没有同步更新。

#### 3.4 HS 预置核对

| 品名 | 预置 CN 码 | CN 公开来源 | 预置 US 码 | USITC HTS（实时查询） |
|---|---|---|---|---|
| 鱼竿 | 9507100090 | 其他钓鱼竿 ✅ | 9507.10.00.40 | Fishing rods ✅ |
| 鱼钩 | 9507200000 | 钓鱼钩 ✅ | 9507.20.40.00 / .80.00 | Snelled / Other ✅ |
| 渔轮 | 9507300000 | 钓线轮 ✅ | 9507.30.20 / .40 / .60 | 按单价 ≤$2.70 / ≤$8.45 / >$8.45 ✅ |
| 拟饵 | 9507900000 | 其他用品 ✅ | 9507.90.70.00 | Artificial baits and flies ✅ |

不预置鱼线：
- 保守做法可以接受；
- 但理由说过头了。USITC 现行税则明确有 **9507.90.20.00 “Fishing line put up and packaged for retail sale”**；国内多份通关指南也把钓鱼线归 9507900000；
- 第 95 章注释排除的只是“已剪成一定长度、但未制成钓线”的单丝；
- 所以零售包装成卷的鱼线归 9507.90.20 的情况相当常见，开发方引用的 5404 / 5607 / 3916 只适用于非零售包装或特定规格；
- 建议把理由改为“归类取决于是否零售包装和规格，需逐个确认”，而不是暗示一般不归 9507。

### 四、D4 原件比对（未完成部分）
- 已完成：
  - 表头结构比对：德速“发票填写模板”第 20 行表头、第 21 行起是数据；琦珞 T6“发票”第 13 行表头、第 14 行起是数据。都和代码的起始行一致；
  - 重量口径比对（见 N2）。
- **未测：三个适配器用原件 CSV 的端到端导出逐格比对。**
  - 原因：发票必填字段（英文品名、品牌、单位、用途）是从产品的发票扩展信息里取的，我用 PATCH 种的字段没被 invoice_fields 读到，导出返回 409。
  - 这是我的数据准备方式不对，不是产品缺陷。按“不编造”原则标为未测。
  - 琦珞 T5 第五批原件没有对应 CSV，也只能做结构核对。

### 五、测试质量

#### 5.1 改过的旧测试
- test_box_label_mapping 和 test_shipment_validation 改成用 `亚马逊FBA表[1-9].csv`：合理（重复上传现在会报错）；
- test_s4fix_reconcile 改 T5/T7：符合新行为；
- test_forwarder_export 改成逐格比较：变严了；
- test_e2e：合理；
- **test_s4fix_invoice_export 把货代集合从 `==` 放宽为 `>=`：略弱**。新增货代不会让测试失败，删掉货代仍会。可以接受，但建议显式列出 5 个。

#### 5.2 30 条新测试
有效的：D-12 单元边界、D2、D5、D6、D7、D10、D12。

弱的有 6 条：

| 测试 | 问题 |
|---|---|
| test_d1_tail_pool_no_auto_fallback | 检查源码文本 |
| test_d3 | 只断言 JSON 里有“下单模板”，恒为真 |
| test_d4 | 只检查注册 |
| test_d8 | grep 源码里的 “.default.json” |
| test_dec12_price_rows_warn | 只 grep |
| test_d15 | 接受 400/404/405/422 |

最关键的缺口：没有一条 D-12 测试经过数据库，所以 N1 漏掉了。

### 六、回归与交付物

| 项 | 结果 |
|---|---|
| 全量 pytest | **660 passed**（71.97 s），与开发方一致 |
| tsc --noEmit | 0 报错（exit 0） |
| 冒烟 smoke_e2e.py | **19/19 通过**。前端用 V3.1 包里的 _internal\dist，结束后已移除；真实 app_data 哈希前后一致（53 个文件） |
| S4 金标准 | 13 个用例、2557 格：通过 2533，已知差异 24，**失败 0** |
| V3.1 便携包 | 206,737,080 字节，zip 11:27 ET，exe 11:26:38 ET，都晚于代码提交 b7bcc6e（11:25 ET）✅ |
| 包内敏感物 | 3910 个文件，没有 .db、.env、密钥或 lingxing 配置；搜索 JSON/TXT 中的 mcp_key、app_secret、api_key、access_token 也没有命中。命中的 cacert.pem 和 fastapi/security/api_key.py 是库文件 ✅ |
| exe 启动 | FBA_APP_DATA_DIR=临时目录，FBA_NO_BROWSER=1：只监听 127.0.0.1:8002；/api/health 返回 ok、master_db true；首页 200；hs-presets 200；forwarders 返回 5 个。数据库和 .server_port 都写在临时目录。测完已结束进程 ✅ |

### 七、复现用探针
- 探针在 %TEMP%\fba_deep：
  - pG.py：D1–D15、A/B、D10、D-12 逻辑；
  - pH.py：D1 尾数、D-12 端到端；
  - pI.py：D4 原件比对。
- 结果存在 s8res_pG.json、s8res_pH.json。
- pG 里有一处 D1 和第6批 5 个样本标成 FAIL，是我写的期望值错了：
  - 自动排箱已经把 2 件尾数放进混装箱，尾数池为空是正确的；
  - 第6批的原件是 T6；
  - pH 已用正确场景重测，结果通过。

### 八、给开发方的修复清单（按优先级）
1. N1：`_row_to_dict` 加上 regular_price、regular_price_at、last_nonpromo_price、last_nonpromo_at，并补“同步 → 读库 → 申报价/提示”的端到端测试；
2. N2：确认德速、琦珞重量口径（第9批是单件重），导出时提示或可切换；给三个新适配器补输出内容的金标准；
3. 删除仓库里的 .pyc，更新 .gitignore；
4. 把弱测试改成行为断言；
5. 决策记录：补 D-12 细节由谁确认，以及 D-01 的反向引用；调整鱼线说明。


---

# 附录 D：HANDOFF_交接清单.md（交接时全文）

## HANDOFF 交接清单（FBA Smart Tool 优化）

> **接手的 bot 只看这份清单就能继续。** 每完成一项立即更新本文件（状态、负责人、时间、tag）。（s8-docs：新 Bot 只维护仓库根目录这一份，不再和任何盒子副本同步。）
> 最后更新：见文末“更新记录”。

### 1. 总目标
在现有 FBA 发货助手（FastAPI + React + SQLite）上新增三件事，并先把基础打牢：
1. 领星产品库及定期同步（MCP 暂不接入，先用领星 Excel/CSV 手动导入，接口留好）；
2. 发票按规则导出（首期 SEND + 九方）；
3. 报关单自动导出（.xlsx 和 .xls 都要）。
分阶段：S1 基础（git、golden、录入、安全、箱规规则、报关默认值）→ S2 产品库/领星/箱规导入 → S3 报关规则引擎 → S4a 模板核对 → S4 发票 → S5 MCP → S7 收尾。

### 2. 方案文件位置（已提交到仓库 docs/方案/，规则以前两份为准）
- `docs/方案/FBA_Smart_Tool_优化方案.md`（v8）：分模块方案、验收、黄金样例、工时、风险、评审对照 §8。
- `docs/方案/测试文件分析与规则清单.md`（v8）：样例反推的规则、证据坐标、待确认事项 §7.1。
- `docs/方案/待确认问题_初版答案.md`：各决定的依据和链接。
- 历史版本（`*_v5备份.md` 等）没有放进仓库，以 v8 为准。

### 3. 注意事项（必读）
- **项目路径**：`C:\Users\huang\Desktop\FBA_Smart_Tool_Cursor2026.7.1\FBA_Smart_Tool_Cursor`。每条命令都会弹批准卡，尽量把多步合并成一个脚本。
- **完整备份**：同级目录 `FBA_Smart_Tool_Cursor_backup_20261016`（排除 node_modules，2026-10-16 05:00 ET，49037 个文件 6.3GB）。不要动它。
- **不动真实数据**：`app_data/`（用户业务数据）、`backend/fba_master.db`、`backend/config/sessions/` 不读改、不提交。测试一律用临时目录。
- **密钥不进 git**：`.gitignore` 已排除 `app_data/`、`*.db`、`lingxing.json`、`*.key`、`.env`。提交前跑：`git grep --cached -n -I -E "sk-[A-Za-z0-9]{20,}"`，应为 0 条。领星密钥在聊天里出现过，**不得使用、不得写入任何文件**。
- **用户测试目录只读**：`C:\Users\huang\Desktop\亚马逊-2.Inventory-库存健康 FBA`。golden 样例用的是副本（`backend/tests/golden/samples/`）。
- **跑测试**：`cd backend; .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`（Python 3.9.13，约 2 分钟）。代码必须兼容 Python 3.9。基线：167 passed, 1 skipped。
- **（已作废）盒子镜像工作流**：原 Bot 在自己的 Linux 盒子里改代码再打补丁到电脑。新 Bot **只在用户电脑上工作**：直接在仓库里改、用 `backend\.venv` 跑全套、提交、打 tag，不需要任何盒子或补丁。
- **启动端口**：一键启动 `一键启动.bat` → `scripts/start_dev.ps1`：后端 uvicorn `127.0.0.1`，端口自动选 8000–8099（写入 `.dev/ports.json`）；前端 Vite 5173–5199。打包版 `run_app.py`：`127.0.0.1`，8002 起（8002–8011、18002–18019）。
- **前端**：后端托管的是 `backend/dist`（构建产物，不在 git 里）。S1 不改前端源码，避免需要重新构建。
- **遇到需要用户决定的事就停下**，写进第 6 节“阻塞/待用户决定”，不要猜。

### 4. 任务清单

#### S0 规则确认 — ✅ 已完成（v5–v8）
- [x] 12 个阻塞问题 + E1/E2 已定；E3 改为箱规批量导入（S2）。负责人：Grok Bot，2026-10-16。

#### S1 基础（方案 3.1、3.4、3.6、3.7、3.8）
| # | 任务 | 涉及文件 | 验收方法 | 状态 | 负责人/时间 | tag |
|---|---|---|---|---|---|---|
| S1a | 本地 git 初始化，.gitignore 排除 app_data/数据库/密钥/node_modules/构建产物，提交基线 | `.gitignore` | `git status` 干净；暂存区无 app_data/.db/lingxing.json；密钥扫描 0 条 | ✅ | Grok Bot 2026-10-16 05:0x | `s1-baseline` |
| S1b | golden 回归基建：manifest、产品库快照、比对工具、样例副本 | `backend/tests/golden/*`、`backend/test_golden_infra.py` | `pytest test_golden_infra.py` 全过；全套通过 | ✅ | Grok Bot 2026-10-16 05:1x | `s1b-golden` |
| S1c | 文本录入修复：识别表头、FNSKU 列、Tab/逗号/空格分隔、解析失败报错（不再静默填 0） | `backend/fba_tool/data_processing.py`、`backend/routers/step1.py`、`backend/test_parse_text.py` | 新增用例全过；全套通过 | ✅ | Grok Bot 2026-10-16 05:2x ET | `s1c-parse` |
| S1d | 安全：默认只监听 127.0.0.1；可选访问口令（非 GET 需口令） | `backend/main.py`、`backend/security.py`（新）、`backend/test_security.py` | 401/200 用例；`netstat` 看到 127.0.0.1 | ✅ | Grok Bot 2026-10-16 ET | `s1d-security` |
| S1e | 重量/尺寸规则统一：kg/cm 基准、精确系数、> 比较、22.5 预警/22.68 阻断、63.5 阻断、单件箱例外（Team/Mechanical Lift）；单件 > 22.68kg 直接算大件；大件分段用精确系数 | `backend/fba_tool/fba_compliance.py`、`backend/fba_tool/placement_fee.py`、`backend/test_fba_compliance_v7.py` | 方案 §5-7 临界值用例全过；全套通过 | ✅ | Grok Bot 2026-10-16 ET | `s1e-fba-rules` |
| S1f | 报关默认值：征免性质 101、海路运输、宁波北仑、委托书当年 12-31、单位取产品库、净重 = 毛重 − 0.2×箱数、Decimal HALF_UP | `backend/fba_tool/customs_package.py`、`backend/test_customs_defaults.py` | 新增用例全过；全套通过 | ✅ | Grok Bot 2026-10-16 ET | `s1f-customs-defaults` |

#### S1-fix1 验收修复（S1 测试评审 93 分，报告 docs/评审报告/S1_测试评审.md）— ✅ 已完成，tag `s1-fix1`
| # | 任务 | 涉及文件 | 验收方法 | 状态 |
|---|---|---|---|---|
| D1 | 仓库代码不再从工作流程 UUID 误识别（BF26）：按 货件名称 → 文件名 → 表头上方元数据行 取值，跳过工作流程行并去掉 UUID；`parse_csv_shipment(..., file_name=)`，校验器和 routing 已传文件名 | `fba_tool/shipment_parser.py`、`fba_tool/shipment_validator.py`、`routers/routing.py`、`test_fix_d1_warehouse.py` | test1 五票 = ONT8/AVP1/MDW2/LAX9/TOL3；不传文件名时为 UNKN，绝不为 BF26 | ✅ |
| D2 | 合并报关箱数按（票序号, 箱号）去重 | `fba_tool/customs_package.py`、`test_fix_d2_merge.py` | test1 五票合并：件数 145、毛重 840.9、净重 811.9；备注含 5 个仓库 | ✅ |
| D3 | Excel 样表导入与文本录入共用 `_validate_cells`，非法值按 Excel 行号报错；`load_from_excel_detailed` 返回 (df, fnsku, errors, warnings)，旧 `load_from_excel` 有错时抛 ValueError；`/api/parse_excel` 有错返回 422 | `fba_tool/data_processing.py`、`routers/step1.py`、`test_fix_d3_excel.py` | abc/-5/小数件数/缺发货总数报错；**单箱装量、箱规留空只提示“将从产品库补齐”不报错**（第 3 批真实样表就是留空，由 apply_master_to_input_rows 补）；19 份真实样表 0 错误 | ✅ |
| D4 | CSV 按 UTF-8-SIG → UTF-8 → GBK 严格解码，都失败报“编码无法识别”；发票模块读同一 CSV 的两处也改用 `decode_csv_bytes` | `fba_tool/shipment_parser.py`、`fba_tool/invoice_table.py`、`fba_tool/invoice_automation.py`、`test_fix_d4_encoding.py` | GBK 能导入；乱码报编码错误 | ✅ |
| 附1 | 逗号分隔又含千分位（`1,000`）时，错误信息补充原因；值碰巧合法时加提示 | `fba_tool/data_processing.py`、`test_parse_text.py` | 提示含“千分位”“Tab” | ✅ |
| 附2 | 登录：GET /api/auth/login 不带参数显示口令页（表单 POST）；POST 支持 JSON 和表单；docstring 提醒 URL 方式口令可能进日志 | `backend/security.py`、`test_security.py` | 表单 POST 303 + cookie；页面不含口令 | ✅ |
| 附3 | `.gitattributes`（`* text=auto`，样例数据/二进制 `-text`）+ 一次性 `git add --renormalize .` | `.gitattributes` | 之后编辑不再因 CRLF/LF 产生整文件 diff；看历史 diff 用 `git diff --ignore-cr-at-eol` | ✅ |

#### S2 产品库与领星（方案 3.2）— ✅ 已完成（S2 tag `s2-products`；验收 81 分后补齐，tag `s2-fix1`）
| # | 任务 | 涉及文件 | 验收方法 | 状态 | tag |
|---|---|---|---|---|---|
| 1 | 表结构和字段归属：product_master 扩展（listing_price/_currency/_at/_basis、declare_unit、carton_gross_weight、local_name、category、field_source_json），新表 hs_declare_template、fba_warehouse、customs_rule_profile、forwarder_template、shipment_ticket；user_version=3 | `fba_tool/product_fields.py`、`fba_tool/master_schema.py` | 老库迁移不丢数据；`test_s2_product_fields.py`、`test_s2fix_hs_category.py` | ✅ | s2-products / s2-fix1 |
| 2 | HS/品类配置（含钓具阻断）：宠物 6307909000/7326909000 预置，钓具不预置；钓具缺配置标“缺报关配置”、列表可筛（`?customs_status=missing`、界面按钮）、报关导出阻断 | `fba_tool/hs_config.py`、`customs_package.py`、`customs_export.py` | `test_s2fix_hs_category.py` | ✅ | s2-fix1 |
| 3 | 初始导入：产品信息表（`/api/master-data/upload/product-info`，用例写临时库）、FBA 仓库地址库（琪珞「！」表，`/api/master-data/import/warehouses/preview|apply`，界面“导入仓库地址库”） | `fba_tool/warehouse_db.py`、`routers/master_data.py` | `test_s2fix_warehouse_rules.py`（471 条，重复 HLI2 提示） | ✅ | s2-fix1 |
| 4 | 领星适配层 + `get_listing_price(sku)`；Listing 以 MCP erp_listing 为主（预览确认，手填字段锁定、来源记 lingxing）；local_name 同步；币种 ISO（"$"→USD） | `lingxing_adapter.py`、`lingxing_preview.py`、`lingxing_sync.py` | `test_s2_lingxing_adapter.py`、`test_s2fix_mcp_lock.py`、`test_s2fix_lingxing_map.py` | ✅ | s2-products / s2-fix1 |
| 5 | 领星 Excel/CSV 手动导入（备用通道；预览差异、幂等） | `product_import.py` | `test_s2_listing_import.py` | ✅ | s2-products |
| 6 | 票级数据导入器：腾讯表格、运费测算表「FBA运费-记录」、九方单箱数据 → shipment_ticket（`/api/tickets/import/preview|apply`、`GET /api/tickets`，界面“导入票级数据”） | `fba_tool/ticket_import.py`、`config/ticket_import_map.json`、`routers/tickets.py` | `test_s2fix_ticket_import.py`：第 14 批 5 票毛重 = T3:T7 | ✅ | s2-fix1 |
| 7 | 箱规批量导入（E3）：模板、预览、逐行报错、领星优先 | `product_import.py`、`templates/箱规导入模板.xlsx` | `test_s2_carton_import.py` | ✅ | s2-products |
| 8 | 密钥加密：Windows DPAPI（`mcp_key_enc`），老明文读一次迁移后删除；无 DPAPI 拒绝明文保存 | `fba_tool/secret_store.py`、`lingxing_sync.py` | `test_s2fix_secret_store.py`（Windows 上含真实 DPAPI 往返） | ✅ | s2-fix1 |
| 9 | 申报价：领星 listing_price > 手填 > price/landed_price > 旧值；旧值/大幅降价警告；手填未采用一律提示（s2-fix2）；无价格阻断导出(422)；预览显示每个 SKU 来源 | `product_fields.py`、`customs_package.py`、`customs_export.py`、`step5-workspace.tsx` | `test_s2fix_declared_price.py`、`test_s2_product_fields.py` | ✅ | s2-fix1 / s2-fix2 |
| 10 | 仓库白名单：去掉 TOL2/DAY1，CVG3 在 KY，并入 fba_warehouse 表的亚马逊格式代码 | `warehouse_codes.py` | `test_s2fix_warehouse_rules.py` | ✅ | s2-fix1 |

#### S3 报关导出（方案 3.6）— ✅ 已完成，tag `s3-customs`

| # | 内容 | 状态 | commit |
|---|---|---|---|
| 0 | 产品库本地编辑：网页改任意字段记 manual 锁定；导出 Excel → 本地批量改 → 导回预览确认（D-2026-10-16-03） | ✅ | S3-0 |
| 1 | 规则引擎：净重规则统一到 customs_rule_profile（不再读 user_settings）；金额/重量 Decimal HALF_UP；按票装配 build_customs_from_tickets（毛重=Σ单箱重、单箱重超 2 位小数阻断、多 HS 多行各用模板） | ✅ | S3-1 |
| 2 | 单元格：出口日期 H3、申报日期 L3（K3 标签，L3:N3 合并）默认留空，规则开关 fill_export_declare_date 打开时取 etd；其余日期写序列号带 yyyy-mm-dd；运费 K12 永远留空；委托书签署日期改写 H16（原来误写 H24 勾选格）；合同 B10 写订单备注；清模板残留 0 | ✅ | S3-2 |
| 3 | 订单号建议 JUS{批次}{代码}{箱数}{后缀}；单独/合并（1 个 FBA 单独、多个合并、可手改）；文件名 `{订单号}[-{FBA}]-{单独|合并}报关-9810-报关资料.{xlsx|xls}`；一致性校验（件数整数、毛重≥净重、数量/件数对账、备注订单号=合同号、订单号不和别的票重复）进导出阻断；修混装箱合并行箱数/毛重重复计 | ✅ | S3-3 |
| 4 | .xls 导出：xlwt 按 7 张表重建（合并、列宽、行高、字体、边框、日期格式）；接口 export_format=xlsx/xls；前端可选格式和单独/合并；requirements 加 xlwt==1.3.0、打包 hiddenimports 加 xlwt | ✅ | S3-4 |
| 5 | 报关 golden 回归：38 份（A 14 / B 24），.xlsx 和 .xls 各导一次逐字段比对，失败 0；输入 customs_inputs.json 由 build_customs_inputs.py 从发票/样例生成；补宠物台阶 3921199090 模板 | ✅ | S3-5 |
| 6 | 钓具：已配置能导出、缺要素阻断、宠物+钓具 2 行各用各的要素；单件装标准尺寸 23kg 箱只提示（> 22.68kg Team Lift、> 45.36kg Mechanical Lift）不拦截，依据 D-2026-10-16-05（用户 2026-10-16 08:10 ET 书面确认“同意，只提示不拦截”） | ✅ | S3-6 |

#### S3-fix1（S3 测试评审 98 分，报告 docs/评审报告/S3_测试评审.md）— ✅ 已完成，tag `s3-fix1`
| # | 内容 | 状态 |
|---|---|---|
| 1 | 导出前校验加“毛重 > 0”“净重 > 0”（件数 > 0 时）；golden B 级没有重量，用测试专用豁免（`_test_exempt_codes`，正式导出不传），并加用例证明不豁免会被拦 | ✅ |
| 2 | 票上同时有单箱重和货代毛重且不一致时给 forwarder_gross_mismatch 提示（v5 Q2：毛重仍按 Σ单箱重） | ✅ |
| 3 | golden expected_diff：JUS14DD28（差 4 kg）、JUS11DD25W（约 10 kg）写明是九方样例自身前后不一致 | ✅ |
| 4 | 方案 §6.1 E1 行、§6.2 申报价风险改成 D-2026-10-16-01 口径 | ✅ |
| 5 | 混装多品名、行上没给箱数时的分摊规则（【改 s3-fix2】见 D-2026-10-16-07）：箱数全部记第一行（其余 0）；毛重、净重按件数比例用**最大余数法**分到 0.01（不会出现负数），各行合计 = 总件数/总毛重/总净重；分到 0 的行出 zero_weight_line 提示。依据（【改 s3-final】转述按原文）：规范只要求报关单表头填件数（第二十四条：按运输包装计，不得为零，裸装货物填“1”）、毛重/净重（第二十五、二十六条，kg，不足 1 kg 精确到 2 位小数）；商品行（第三十三至四十三条）没有毛重/净重栏目；第三十六条“数量及单位”分三行填报：法定第一计量单位及数量、法定第二计量单位及数量（无法定第二计量单位的为空）、成交计量单位及数量。第三十六条（四）只列了五种特殊情形（例如“使用不可分割包装材料和包装容器的货物，按货物的净重填报”），不是普遍规则；**规范未规定装箱单逐行毛/净重怎么分摊，分摊为实现方案**。出处：海关总署公告 2019 年第 18 号 https://www.gov.cn/zhengce/zhengceku/2019-11/04/content_5448488.htm ；2024 年第 30 号（改第 25、26 条）http://www.mofcom.gov.cn/zcfb/zgdwjjmywg/art/2024/art_3852cc22860442398ced2db7b5d112d7.html ；件数填法 http://shanghai.customs.gov.cn/shanghai_customs/2026-08/27/article_2026082802531311784.html | ✅ |
| 6 | 决策记录 D-2026-10-16-05（单件 23kg 只提示，08:10 ET 书面确认）、D-2026-10-16-06（拿不准的规则先查权威资料并注明出处，只有用户业务数据才请用户确认） | ✅ |

#### S3-fix2（S3-fix1 复测 98 分，报告 docs/评审报告/S3_测试评审_v2.md）— ✅ tag s3-fix2
| # | 内容 | 状态 |
|---|---|---|
| 1 | 混装票 + 单品名票同名合并时净重漏算单品名票：改成每票先算行净重、再按品名相加（例 4.8 + 17.4 = 22.2），test_s3fix2_customs.py | ✅ |
| 2 | 分摊改最大余数法，不再出现负数尾差；0 重量行出 zero_weight_line 提示（不拦截，表头合计仍正确）；用例 4 品名各 1 件、净重 0.02 → 0.01/0.01/0/0 | ✅ |
| 3 | 查权威出处写进第 90 行和 D-2026-10-16-07：规范只规定表头件数/毛重/净重，分摊为实现方案 | ✅ |
| 4 | customs_rule_profile 加 forwarder_gross_tolerance_kg（默认 0.5 kg，可改，不能为负），旧库 ALTER 补列；差值 > 容差才出 forwarder_gross_mismatch | ✅ |

#### S4a 发票模板盘点（D-2026-10-16-04：全部发票模板，含琪珞等货代）— ✅ 清单已完成：docs/发票模板清单.md
- 测试目录共 67 个发票类文件，归为 8 套模板：T1 九方下单（第10批）、T2 SEND（第13批，已支持）、T3 Commercial Invoice 9810（第2/9批）、T4 旧 COMMERCIAL INVOICE 下单（第4批）、T5 单行汇总下单（第3/5批、老目录）、T6 琪珞 FBA专线导入（第6/7批）、T7 = T5 空白版、T8 九方系统导出（已支持）。
- 【S4 已定】原 4 个待确认点按 D-2026-10-16-08 自行交叉核对，结论见 D-2026-10-16-09 和下方 S4 节。

#### S3-final — ✅ tag s3-final：D-07 与第 90 行按公告原文改准（第二十四条只写“裸装货物填报为‘1’”；第三十六条按三行计量单位填报，（四）只是五种特殊情形）

#### S4 发票模板映射 + 按货代模板导出（D-2026-10-16-04 / -08 / -09）— ✅ 已完成（S4 91.5 → S4-fix1 复测 99.1 分通过，报告 docs/评审报告/S4_测试评审_v2.md；收尾 tag s4-final）
- 解析：`backend/fba_tool/invoice_templates.py`；映射配置 `backend/config/invoice_template_map.json`（8 套模板 T1–T8；用户配置目录放同名文件可按模板 id 覆盖字段；配置文件 JSON 写坏时报“配置文件格式错误：第 N 行”，接口 422）。接口 `routers/invoice_templates.py`：GET /api/invoice-templates、POST /api/invoice-templates/detect、POST /api/invoice-templates/parse（template_id 手选、overrides 覆盖口径、csv_files 附货件 CSV、accept=用户确认的修正 id 列表）。
- 自动识别：按工作表名 + 关键表头打分，**唯一**满分才自动选。T7（空白）与 T5 结构相同、永远同分 → 不自动选，提示手选（S4-fix1 第 5 点）。
- 口径：qty_meaning、weight_meaning、warehouse_prefer、box_count_source 可配置。T6“单件实重”**不设默认**（weight_meaning=null，由 CSV 判定），依据 D-2026-10-16-09 第 2 点（S4-fix1 重写：第7批是单箱重、第6批是单件重）。
- 和货件 CSV 核对（reconcile_with_csv，S4-fix1 改）：只**提建议**（proposals：仓库 / 箱数 / 数量口径 / 重量口径），用户在预览确认（apply_corrections / accept）后才生效；多种口径都能对上且结果不同 → 不采用，列出全部选项；模板没设口径且只有一种能对上 → 由 CSV 判定并记入 decisions。仓库取 CSV“配送地址”（城市+州）对 FBA 仓库地址库，不取货件名称；地址库对不上 → warehouse_unverified。没附 CSV 的票 verify_status=“未核对”，有待确认项为“待确认”，都对上为“已核对”。T8 九方 Packing list 是实测单箱重，只比对不换算。
- **导出（S4-fix1 新增，方案 §3.5）**：规则 `backend/fba_tool/invoice_rules.py`（U 号排序后合并连续箱号区间；混装箱每 SKU 一行、箱重只记一次；申报价 resolve_declared_price（D-01）+ price_checks 警告/拦截；采购价照抄 CNY；币种 USD；文本数字写数值；钓鱼 SKU 缺报关配置拦截并列缺项，其它 SKU 缺发票必填字段也拦截；九方单箱数据实测值读取，外箱号对不上拦截，用户确认的更正才用）。适配器 `backend/fba_tool/invoice_export.py`：SEND（工作表名 `Invoice\xa0Template`，第 15 行起区间行）、九方（Invoice 按 SKU 汇总 + 合计行；Packing list 每箱一行 + CBM + 合计；派送地址取 fba_warehouse）。模板 `templates/forwarders/send.xlsx`、`jiufang.xlsx`（由 `scripts/build_invoice_export_templates.py` 从原始样例清空数据生成），在 `config/forwarders.default.json` 用 export_adapter 登记。接口 `routers/invoice_export.py`：GET /api/invoice-export/forwarders、POST /api/invoice-export/preview、POST /api/invoice-export/export（拦截返回 409 + blocking 清单）。只读产品库和仓库地址库，不写库。
- 产品库发票字段：英文/中文品名、品牌、型号、中文材质/用途走原有列；单位、每套个数、采购价、英文材质/用途、目的港 HS 放 extra_data.invoice。
- golden（S4-fix1 改为**以货代原始样例文件为期望值**）：`tests/golden/compare_invoice_export.py` 逐格比对 SEND 5 票（表头 + 每区间行 A–T）、九方 8 票（Invoice 表头/每 SKU 行 A–V/合计行 + Packing list 表头/每箱行 A–N/合计行；九方行顺序无法从输入推出，Invoice 按 SKU、Packing list 按箱号对齐）。结果：2557 格，通过 2533，已知差异 24（SEND 尺寸列 44.96 vs CSV 45；九方邮编 +4、城市大小写；CLT2 公司名），失败 0；已知差异写在 `tests/golden/invoice_manifest.csv` expected_diff。输入：`invoice_export_inputs.json`（Reference ID 8 票取自运费表、5 票取自样例；九方 5 票实测值取自九方“单箱数据”原件；GZ0PA/9BD6A/TNKDA 三票找不到单箱数据，实测值只能从样例 Packing list 抄，这 3 票 L/W/H/G.W 不算独立核验）、`product_master_golden.json`（补了发票字段并逐条注明来源）。QGXTA 九方单箱数据原件第 6 箱外箱号写成 12，程序拦截，golden 输入里按证据确认更正。补齐了第 11、14 批 3 份货件 CSV。
- 解析侧独立核对：13 份原始样例用 T2/T8 解析，数量逐 FNSKU = 货件 CSV、箱数 = CSV、SEND 单箱重 = CSV 该 U 号箱重量、九方单箱重 = 单箱数据原件。原先自生成的 `invoice_templates_expected.json` 已删除。
- 测试：`test_s4_invoice_templates.py`、`test_s4fix_invoice_export.py`（golden、规则、test1 五票导出冒烟、API）、`test_s4fix_reconcile.py`（建议确认后生效、多口径不采用、仓库取配送地址、未核对、T5/T7 同分、坏 JSON、S1–S3 回归、真实 app_data 不变）。
- S4-final 收尾（复测 v2 的 3 条意见）：① SEND 尺寸列不再用通配符 `B*`：已知差异逐格登记（每票 B15、B16），比对时做正向核验——导出值必须等于样例值逐边四舍五入到整厘米，且等于 CSV 尺寸，否则失败（compare_invoice_export.py 已不支持通配符）；② 待分配货件（没有 FBA 箱号）导出九方发票时返回 box_mark_missing 警告（预览 warnings、导出响应头 X-Invoice-Warnings），提示箱唛为空；③ 琪珞地址库 VGT2 写的是亚马逊公告里“仅限 UPS 小包”的转运地址（20701 Krameria Ave, March Air Reserve Base, CA），按 D-06 查 Amazon Seller Central 官方公告核实后，在 `config/fba_warehouse_corrections.json` 纠正为实际地址 6401 Howdy Wells Avenue, Las Vegas, NV 89115（出处写在文件里）；导入琪珞表和读仓库表时都按纠错覆盖，原表不改。第 7 批 VGT2 票现在能由 CSV 配送地址核对通过。
- 已知：T8 LCL2609PU1DA 九方实测 169.89 kg vs CSV 173.5 kg（差 2.1%），只提示；T3 第9批表头“总件数”填了 104（商品数），以箱号区间 26 箱为准并提示；SEND 混装箱的填法没有样例，按“每 SKU 一行、箱重只写第一行”处理。

#### S5 领星 MCP 定时同步 — ✅ 已完成（s5-sync 97.8 → S5-fix1 复测 99.8 通过；tag s5-final）
- 新模块 `backend/fba_tool/lingxing_scheduler.py`（v8 §3.2 第 2 条逐条对应）：
  - asyncio 后台任务（main.py startup 启动、shutdown 停止；`FBA_DISABLE_SCHEDULER=1` 不启动），**不引入 APScheduler**（有测试断言 requirements 里没有）。
  - **默认关闭**；频率可配 `interval_minutes`（15–10080 分钟），存在 app_data/config/lingxing.json 的 `auto_sync` 段，和密钥同一文件。
  - **防重入**：与手动“一键拉取”共用一把锁 `SYNC_LOCK`；上一轮没结束时本轮记一条 status=skipped 的运行记录。
  - 结果记到 `lingxing_sync_run`（新增列 trigger=manual/scheduled/retry、attempt，老库自动 ALTER 迁移）和 `lingxing_sync_diff`（kind：applied 已写入 / locked 手填锁定 / needs_review 待人工确认 / retry 失败重试 / error …）。
  - **失败重试 + 日志**：`max_retries`（默认 3）次，第 n 次重试前等 n×`retry_delay_seconds`（默认 60s）；每次尝试单独一条运行记录；日志写 app_data/logs/lingxing_sync.log（轮转 1MB×3），密钥只写掩码；全部失败后界面“立即同步/重试”按钮走同一路径（trigger=retry）。没配密钥直接失败不重试。
  - **D-02 产品库以 MCP 为唯一来源**：定时同步拉到的 Listing 按预览默认勾选直接写入（复用 S2 的 `apply_lingxing_field_patch`）；**手填字段保持锁定**（记 locked 差异）；**申报价例外**：listing_price 不受手填锁定，申报价按 D-01（领星 listing_price > 手填 declared_value > …），手填 declared_value 保留不删。SKU 对不上、报关敏感字段（英文品名/品牌本地已有值）不自动写，记 needs_review，留在预览里人工确认（auto_applied 状态仍可确认）。
  - **只读**：`ReadOnlyClient` 只放行 get_my_sids、get_multi_platform_shop_list、erp_listing、get_fba_stock_list、query_fba_valid_list、query_product_performance_asin_lists，其它 toolId 抛错。
  - **密钥走 DPAPI**：沿用 S2-fix 的 `secret_store`（mcp_key_enc 密文，文件里无明文）；Windows 上有真实 DPAPI 往返测试。
- 接口（routers/lingxing.py）：GET/PUT `/api/lingxing/schedule`（PUT 参数越界 422）、POST `/api/lingxing/schedule/run-now`（同步中 409）、GET `/api/lingxing/runs`（带各类差异条数）、GET `/api/lingxing/runs/{id}`（差异明细，不存在 404）、GET `/api/lingxing/sync-log`。
- 界面：主数据页领星卡片新增 `LingxingSchedulePanel`（frontend/src/components/lingxing-schedule-panel.tsx）：启用开关、间隔、重试次数、下次/上次结果、立即同步/重试、同步记录表（点开看每条差异）、日志。tsc 检查新文件 0 错误（仓库原有 17 个类型错误在其它文件，未动）；前端未重新打包。
- 测试 `backend/test_s5_lingxing_schedule.py`（15 条，全 mock，不连领星）：默认关闭/频率校验、无 APScheduler、D-02 写入 + 手填锁定 + 申报价 D-01 例外、第二次 0 写入、只读白名单、失败 2 次后第 3 次成功（等待 7/14 秒、每次一条记录、日志无明文密钥）、全失败后手动重试、无密钥不重试、锁防重入（skipped）、手动与定时共用锁、asyncio 循环到点才跑/关闭不跑、配置文件只有密文、API 全流程、真实 app_data 不变。未调用真实 MCP。
- S5-fix1（评审 97.8 的 3 条缺陷 + 1 条测试）：
  - S5-1 改间隔立即生效：`save_schedule` 每次保存都按 `compute_next_run` 重算下次时间（关掉则清空），PUT 接口返回的 status 和面板马上显示新值。
  - S5-2 上次成功时间持久化：取数据库 `lingxing_sync_run` 里成功状态（auto_applied/auto_applied_partial/preview_pending/partial/confirmed）的最大 finished_at（`get_last_lingxing_sync_success_at`），手动拉取成功也算；启动时下次 = 上次成功 + 间隔；从没成功过或已过期 → 启动后 60 秒补跑一次（CATCH_UP_DELAY_SECONDS）。成功后下次 = 上次成功 + 间隔；失败后 = 现在 + 间隔（不在失败后反复补跑）。面板显示“上次成功”。
  - S5-3 不可恢复错误不重试：白名单拒绝（ReadOnlyClient.violation）、缺密钥、鉴权失败（HTTP 401/403、unauthorized/forbidden/invalid key 等）只跑一次，记 fatal 差异，返回 fatal=true，锁在 finally 里立即释放；网络超时、HTTP 5xx 仍重试。
  - 共用锁改为真实并发测试：手动一键拉取（API 流式，mock 卡住）进行中时定时同步记 skipped；定时同步进行中时手动拉取和立即重试都返回 409；结束后锁已释放。
  - 测试 test_s5_lingxing_schedule.py 增至 23 条（盒子 22 通过 + 1 条真实 DPAPI 只在 Windows 跑）（含 3 种不可恢复错误参数化、启动补跑的 asyncio 用例、间隔改动 API 用例）。
- 已知局限：定时同步只在程序开着时跑（v8 定的进程内 asyncio 方案，没有系统级计划任务）。

#### S7 工程整理 — ⏳ 待评审（s7-cleanup 98.6 未过 99 → S7-fix1 已交付 tag s7-fix1，待复测；评审通过前不算完成）
- v8 §3.8 S7 验收逐条：
  1. **统一 app_data/ + config/*.default.json**：backend/config 里 7 个会复制给用户的出厂配置改名为 `*.default.json`（user_settings、formulas、sku_mapping、fnsku_mapping、amazon_sku_metadata、invoice_mapping、invoice_history）；`resolve_config_read` 先读 app_data/config/<名>.json，没有就读 `<名>.default.json`；写一律到 app_data/config。规则配置（invoice_template_map、lingxing_field_map、ticket_import_map、fba_warehouse_corrections）保持原名（只读出厂、可同名覆盖）。打包 spec 同步排除 invoice_history.default.json。**重复模板/数据库一个都没删**：清单和建议在 `docs/S7_重复文件清单_待用户确认.md`，等用户同意并备份后再删。
  2. **归档 Streamlit 入口**：app.py、launcher.py、4 个只给它用的 *_ui/perf_cache 模块、旧 spec 和 bat 用 git mv 移到 `backend/legacy_streamlit/`（附 README）；requirements 去掉 streamlit。README 更新（依赖、配置、冒烟、使用说明）。
  3. **依赖锁定**：`backend/requirements.lock.txt`（运行时 47 个包，== 锁死）+ `requirements-dev.lock.txt`（pytest/httpx/pyinstaller 等），由 PC 上跑通全套测试的 venv（Python 3.9.13）pip freeze 生成；requirements.txt 补上漏掉的 loguru。
- 前端：修掉原有 17 个 tsc 错误（step5 LinesTable 类型、throttle 类型、use-customs 类型断言、File System Access API 类型声明 `src/types/file-system-access.d.ts`、vite.config 的 Plugin 类型与 `router` 选项——vite 7 的 http-proxy-3 不支持 router，原来就不生效，已删除并改正日志文字：后端换端口需重启前端 dev）；`tsc --noEmit` 0 错误。新增 Step 4.5「按货代模板导出发票（SEND / 九方）」面板（forwarder-invoice-export-panel.tsx）：上传货件 CSV → 预览（区间、提示、拦截原因）→ 下载。前端完整打包见下方 PC 记录。
- 领星鉴权错误文字已实测：用假 Key 对真实领星 MCP（openmcp.lingxing.com）只读调用——initialize 不校验 Key；第一次 tools/call（get_my_sids）返回“MCP Key无效或已失效，请检查x-mcp-key配置；如无法确认，请在MCP服务管理页重新生成Key后更新客户端配置”。匹配条件改为按这段原文（“Key无效或已失效”“x-mcp-key配置”），保留 HTTP 401/403 兜底，去掉猜测的英文关键词；新增用例按真实行为模拟（initialize 成功、tools/call 报错）只跑一次不重试。未用真实 Key，未调用任何写接口。
- 端到端启动冒烟 `scripts/smoke_e2e.py`：真起 uvicorn 进程、临时 app_data、临时口令，18 项：启动、前端页、401、产品库（导入仓库地址库、VGT2 纠正、产品列表、定时同步默认关→开启算下次时间→无密钥不重试）、发票（模板识别、SEND 预览 148 件、SEND/九方导出）、报关（xlsx/xls）、日志无 Traceback、真实 app_data 哈希不变。盒子 18/18。
- 用户使用说明：根目录 `用户使用说明.md`（启动与数据、产品库、发票、报关、常见问题）。
- 测试 `backend/test_s7_cleanup.py`（6 条）：出厂配置命名、读回退/写入 app_data、首次运行复制、Streamlit 已归档且无引用、lock 覆盖全部依赖且 == 锁死、冒烟脚本和说明存在。
- PC 实测（2026-10-16 约 10:05 ET）：补丁打好后全套 621 passed；`frontend` 下 `tsc --noEmit` 0 错误；`scripts/build_standalone.ps1` 完整打包成功（npm build → 同步 backend/dist → 资源校验 → PyInstaller），产物 `dist/FBA_Smart_Tool_V2.0_便携版.zip`（195.8 MB）；打包第 0 步会重新生成 backend/templates/forwarders/qiluo.xlsx，已 git checkout 还原，工作区干净；`scripts/smoke_e2e.py` 18/18（含已打包前端页面），真实 app_data 53 个文件哈希不变。打包后的 exe 没有启动（它会往便携目录写端口文件并自动打开浏览器），只验证了构建脚本自带的资源校验。lock 文件没有在全新虚拟环境里重装验证。
- 未做：货代发票模板识别（T1–T8 parse/核对）仍只有后端接口，没有前端页面（使用说明里已写明）。

##### S7-fix1（S7 评审 98.6 分）— ⏳ 待评审，tag `s7-fix1`；产品版本号改为 **V3.0**
1. **九方同城多仓（−0.5）**：`routers/invoice_export.py` 新增 `resolve_export_warehouse`，顺序：面板指定 > 配送地址唯一对应 > CSV 仓库代码在同城候选里 > 地址查不到但 CSV 代码在仓库库里 > SEND 不需要 > 否则 422 返回 `warehouse_candidates`。预览返回 `warehouse_source`。面板加「仓库代码」输入框 + 候选下拉（422 时出现）。第 7 批 FBA19GVFX5SC（LAS VEGAS，同城 VGT2/LAS7/IVSE…）现在自动取 VGT2。
2. **`docs/S7_重复文件清单_待用户确认.md` 第 4 条更正**：两份工作流文档不同（8.5 KB 精简版 vs 20 KB V1.2 详细版），改为两份都保留、建议以后合并，不删任何一份。
3. **坏 JSON 用户配置不再静默**：`user_config._read_json` 对 user_settings.json / formulas.json 解析失败、读不了、顶层不是对象时写 warning 日志并记入 `config_errors()`；新接口 `GET /api/config/errors`（每次重读，改好即消失），settings/formulas 接口带 `X-Config-Warning` 头；界面顶部黄色横幅 `config-error-banner.tsx`。仍用出厂值兜底，程序可用。
4. **外箱号更正入口**：409 拦截项 `measured_box_mismatch` 出现时面板显示「确认外箱号更正」，每个多出的箱号选对应货件第几箱 → 以 `box_id_fix` 提交重新预览；`read_jiufang_box_data` 现在也接受完整 FBA 箱号作 key。预览上方写明已按哪些更正导出。
5. **架构手册**：入口改为 `run_app.py` + `backend/main.py`，打包改为 `scripts/build_standalone.ps1` + `packaging/FBA_Smart_Tool.spec`；旧 app.py / build_v1.8.bat / FBAWizard*.spec 标为已归档到 `backend/legacy_streamlit/`。
- 其他：`用户使用说明.md` 出厂配置路径写为 `FBA_Smart_Tool\_internal\config\`，补仓库选择和外箱号更正用法；冒烟脚本收紧——`backend/dist/index.html` 不存在时前端页面检查判失败；真实 app_data 可用 `--real-app-data=路径` 或 `FBA_REAL_APP_DATA_DIR` 指定，目录不存在或为空判失败。
- **版本号 V3.0**（用户决定）：`finish_portable_dist.py` RELEASE_VERSION、`build_standalone.ps1` 输出、spec、`run_app.py`、顶栏「U盘便携版 V3.0」、`packaging/使用说明.txt`、用户使用说明、架构手册。新包 `dist/FBA_Smart_Tool_V3.0_便携版.zip`；旧的 `dist/FBA_Smart_Tool_V2.0_便携版.zip` 保留不删（打包脚本只覆盖同名 zip）。`给下一次AI_V2.0交接说明.md` 是历史文档，没改。
- 测试 `backend/test_s7fix1.py`（8 条）。盒子：全套 627 passed、2 skipped；tsc 0 错误；冒烟在盒子上 18/19（盒子没有 backend/dist，前端页面检查按新规则判失败，符合预期）。PC 结果见下条。
- PC 实测（2026-10-16 约 10:36 ET，补丁提交 48107b8）：全套 629 passed（第一次跑时 `test_forwarder_export_idempotent_with_subtotals` 偶发失败，原因是两次生成的 xlsx 字节长度差 1（zip 时间戳），和本次改动无关，补丁脚本自动回退后重跑全部通过；这条测试本身还不稳定，留作待办）；frontend `tsc --noEmit` 0 错误；从 s7-fix1 代码用 `scripts/build_standalone.ps1` 重新打包成功，产物 `dist/FBA_Smart_Tool_V3.0_便携版.zip`（195.8 MB，10:34 ET），打包后的前端里有「V3.0」；旧 `FBA_Smart_Tool_V2.0_便携版.zip` 仍在；qiluo.xlsx 已 git checkout 还原，工作区干净；收紧后的冒烟 19/19（前端页面来自已打包的 backend/dist，真实 app_data 指向 PC 仓库根，53 个文件哈希不变）。exe 没有启动。

##### S7-archive（D-2026-10-16-11：重复文件归档不删除）— tag `s7-archive`；S7 仍 ⏳ 待评审（S7-fix1 复测 99.4 分已过线，报告 docs/评审报告/S7_测试评审_v2.md；Step 4.5 深度评测进行中，用户未宣布 S7 完成）
- 用 `git mv` 移到仓库根 `archive/`，**没有删除任何文件**：`frontend/_export_test/test_amazon.xlsx`、`frontend/_export_test/test_internal.xlsx` → `archive/frontend_export_test/`（另加 `archive/README.md` 记录原路径）。
- 移动前逐个全仓搜索引用（代码、打包 spec/脚本、测试、文档），有引用的都没移：第 3 条（`packaging/使用说明.txt` 打包时用、根目录 `使用说明.txt` 是备用来源、`使用说明.md` 在代码评审日志里被提到）、第 5 条的 `scratch/`（代码评审日志引用为证据）、第 6 条（e2e 测试按通配读取、随 templates 打包）、第 7 条（已是归档目录）。第 1 条的 `backend/fba_master.db` 不受 git 管理，没碰。第 4 条按用户要求不动。逐条原因见 `docs/S7_重复文件清单_待用户确认.md` 文末。
- Step 4.5 货代发票导出页保留，等 FBA测试员深度评测。**没有重新打包**（测试员正在评测 V3.0 包），所以 V3.0 包里不含这次归档，对包内容没有影响（归档的文件本来就不进包）。
- 待办（S7 评审 v2 `docs/评审报告/S7_测试评审_v2.md` 的 3 个轻微项，本轮**不修**）：
  - [x] A（S8 已修）（−0.3）九方仓库与 CSV 仓库代码冲突时不提示：手选仓库和 CSV 代码不一致，或配送地址唯一对应的仓库和 CSV 代码不同时，应加 warning（如 `warehouse_csv_conflict`）并在预览显示。
  - [x] B（S8 已修）（−0.2）坏 JSON 横幅：按说明删掉坏的 formulas.json/user_settings.json 后刷新页面仍报错，要重启才消失。原因：`CONFIG_ERRORS` 只在重新解析同名文件时清除，文件不存在时走不到那一步。
  - [x] C（S8 已修）（−0.1）`test_forwarder_export_idempotent_with_subtotals` 不稳定：比较的是 xlsx 字节长度，跨秒时 `docProps/core.xml` 时间戳不同（测试员 300 轮里 5 次），应改成比较单元格值。
  - 另记（测试员标“不扣分”）：启动横幅“数据目录”显示的是包内 app_data，实际数据写在 `FBA_APP_DATA_DIR`；`.server_port` 也写在包内 app_data（run_app.py L75）。

#### S8 深度测评 V3.0 修复（报告 docs/评审报告/深度测评报告_V3.0.md，94.3 分）— ⏳ 待评审（s8-fix 复测 93.0 未过 → S8-fix1 已交付 tag `s8-fix1`，待复测）；版本号 **V3.1**
- 中等缺陷：D1 尾数分配必须在尾数池内（后端 400 + 前端上限；尾数池不再退回“自动尾数”；箱单超计划禁止导出）；D2 分仓 CSV 仓库代码优先、文件名兜底、冲突警告（响应头 X-Routing-Warnings + 预览黄色提示）；D3 Step 4.5 新增 T1–T8 发票模板识别面板，T5/T7 平局按有无数据判定，T4 只认“下单模板”表；D4 新增琪珞 T6/T5、德速 T3 导出适配器与模板（scripts/generate_invoice_export_templates.py 从 golden 生成）。
- 轻微项：P1(A) warehouse_csv_conflict；D5/D6 HS 编码 8/10 位校验（全角转半角，非 ASCII 数字拒绝）、数值字段拒绝非数字、PATCH 未知 SKU 404；D7 标签尺寸 10–600mm、坏 PDF/坏 base64 返回 400；P2/D8(B) 坏 JSON 横幅删文件后刷新即消失；D9 run_app 认 FBA_APP_DATA_DIR、FBA_NO_BROWSER；D10 领星新品乱码/缺 FNSKU/ASIN 进“需复核”默认不勾；D11 批量修改重复 SKU 行全部报错不写；D12 同一货件 CSV 重复上传为硬错误；D13 e2e 用完整 Merchant SKU 并补 Step1→4.5 流程测试；D14 未知货代先报“不支持该货代”；D15 分仓空导出 400；P3(C) 货代导出幂等测试改单元格比较。
- 新决策 D-12（修订 D-01）：促销期按正常价申报并提示，正常价=领星常规价，否则近 90 天最近非促销价；阈值低 5% 以上；不用划线价。记录在 docs/用户决策记录.md。
- HS 钓具参考：fba_tool/hs_presets.py + GET /api/master-data/hs-presets（只读，不自动写库，保持 Q13/E4）。竿 9507100090 / 钩 9507200000 / 轮 9507300000 / 拟饵 9507900000，中国税则（合肥海关 12360）与 USITC HTS 逐条核对；钓鱼线不预设（中国成品归 9507900000，美国零售包装并标明鱼线的归 9507.90.20（CBP HQ 954309 / HQ 956007），只绕线轴的按材质归 5404 / 3916 / 5607；NY 882320 是早期归 5404 的例子）。
- 为配合 D12 改的旧测试：test_box_label_mapping、test_shipment_validation 只传 亚马逊FBA表1–5（templates 里“亚马逊FBA表.csv”与“表1.csv”是同一票）；test_s4fix_invoice_export 货代列表改为包含新增 3 家。
- 盒子实测：pytest 658 passed / 2 skipped；tsc 0 错误；冒烟 18/19（唯一失败是盒子没有打包前端 backend/dist，PC 打包后再跑）。
- PC 实测（2026-10-16 约 11:30 ET，补丁提交 b7bcc6e）：pytest 660 passed（补丁脚本两步都跑，第一步 630、第二步 660）；frontend tsc 0 错误；`scripts/build_standalone.ps1` 打包成功，`dist/FBA_Smart_Tool_V3.1_便携版.zip`（197.2 MB，11:27 ET），前端包里有「V3.1」；旧 V2.0 / V3.0 等 zip 都在；qiluo.xlsx 已 git checkout 还原，工作区干净；冒烟 19/19（真实 app_data 53 个文件哈希不变；冒烟要用 backend\.venv 的 Python）。exe 用临时 FBA_APP_DATA_DIR（%TEMP%\fba_s1\s8fix\exe_appdata）+ FBA_NO_BROWSER=1 启动一次：2 秒内 /api/health 200，横幅显示 V3.1 和临时数据目录，没有打开浏览器，`.server_port` 写在临时目录；检查后已停止。

##### S8-fix1（S8 复测 93.0 分，报告 docs/评审报告/S8_测试评审.md）— ⏳ 待评审，tag `s8-fix1`；版本号仍 V3.1（V3.1 zip 覆盖重打）
- N1 严重：`master_db._row_to_dict` 补读 regular_price / regular_price_at / last_nonpromo_price / last_nonpromo_at，并原样带出以后新增的列。审计：产品库所有读取（get_product_by_sku、list_products、按 SKU 批量、全量 map、lookup_by_fnsku）都经过 `_row_to_dict`，其他模块没有直接 SELECT product_master 取产品字段的地方。新增端到端测试 `test_s8fix1_dec12_e2e.py`（mock 领星定时同步 → 库 → 读库 → 申报价/来源 → 报关包 promo_price_not_used、发票 price_rows）：15.99/19.99、18.98/20、正好 5% 不算、无常规价 16→12、90 天过期、定时自动写入路径、网页手改常规价。去掉修复后 9 条里 7 条失败，证明能抓到这个问题。
- N2 中等：德速 T3 / 琪珞 T6 重量列不再写死单箱重。口径优先级：面板选择 > 上传货代这票原件、按货件 CSV 核对判定（`decide_weight_basis`，复用琪珞模板解析的 reconcile）> 货代配置；都没有时留空并提示 `weight_basis_undecided`（给出单箱重/单件重示例）。前端 Step 4.5 加“重量口径”下拉和“货代给的这票发票”上传。新增 `test_s8fix1_invoice_adapters.py` 对原件逐格比对：德速第9批 C/N/T/U/V/W 6 行全对（T21 = 1.7025 单件重）；琪珞 T6 第6批 5 票按 CSV 判为单件重，每箱件数/单件重对原件（原件长宽高 35×35×42 与 CSV 60×45×36 不符、箱号写整批 1-30，不比）；琪珞 T6 第7批判为单箱重，A/F/M/N/O/P 全对；琪珞 T5 按 CSV 汇总核对。
- N3：.pyc 取消跟踪（git rm --cached，不删本地文件），.gitignore 加 `__pycache__/`、`*.py[cod]`。PC 上另有 `__pycache__/run_app.cpython-39.pyc` 被跟踪，同样处理。
- N4：6 条弱测试改成行为测试（尾数池全部装箱后为空、D15 精确 400 + 文案、真实样本识别 T3/T4/T6/T7 且删掉“下单模板”后不再判 T4、适配器/货代集合精确 ==、坏 JSON 横幅删文件后清除、price_checks 实际出 promo 提示）；test_s4fix_invoice_export 货代集合改回精确 ==。
- 决策记录：D-12 引用 Christopher 原话“加保护：促销低于正常价时用正常价报关并提示，然后开始修复”，注明 5% / 90 天是 New Bot 选的实现参数、可改；D-01 一节加“已被 D-12 修订”。钓鱼线 HS 说明改正：美国有 9507.90.20.00（零售包装钓鱼线），HQ 954309 / HQ 956007 认定零售包装并标明鱼线的归 9507.90.20，只绕线轴、无零售包装的按材质归 5404/3916/5607（s8-docs 改正：此前误把 HQ 954309 写成归 5404 的例子）；用户使用说明、打包使用说明同步。
- 盒子实测：pytest 677 passed / 2 skipped；tsc 0 错误。
- PC 实测（2026-10-16 约 11:55 ET，补丁提交 e550794，另有 PC 上的 00a81d8 取消跟踪 run_app.cpython-39.pyc；3 个 pyc 本地文件已从 %TEMP%\fba_s1\s8fix1\pyc_backup 恢复，未删除）：pytest 679 passed；tsc 0 错误；V3.1 重打 `dist/FBA_Smart_Tool_V3.1_便携版.zip`（206,740,396 字节，11:51 ET，覆盖旧 V3.1）；V2.0 / V3.0 等旧 zip 都在；qiluo.xlsx 已还原，工作区干净；冒烟 19/19（真实 app_data 53 个文件哈希不变）；exe 用临时 FBA_APP_DATA_DIR + FBA_NO_BROWSER=1 启动一次：/api/health 200，货代列表 send/jiufang/qiluo_t6/qiluo_t5/deshu，横幅 V3.1、数据目录为临时目录，未开浏览器，检查后已停止。

### 5. 当前进度
S1（S1a–S1f）全部完成，tag：s1-baseline、s1b-golden、s1c-parse、s1d-security、s1e-fba-rules、s1f-customs-defaults；验收修复 S1-fix1 完成，tag s1-fix1。详细见第 4 节表格。
S2 产品库与领星全部完成：tag s2-products，验收后补齐 tag s2-fix1，复测 96 分后修正 tag s2-fix2，复测 99 分后收尾 tag s2-final（见第 4、7 节）。
S3 报关导出全部完成：tag s3-customs（含第 0 步产品库本地编辑），验收修复 s3-fix1、s3-fix2，收尾 tag s3-final。
S4 发票全部完成：s4-invoice（91.5）→ s4-fix1（复测 99.1 通过）→ 收尾 tag s4-final。S5 领星 MCP 定时同步完成：s5-sync（97.8）→ s5-fix1（复测 99.8 通过）→ tag s5-final。

### 6. 阻塞 / 待用户决定
- （暂无阻塞）
- **待用户确认（S9-step2-fix2，Bot 自定参数）**：价格上限 `PRICE_MAX = 100000`（`backend/fba_tool/lingxing_adapter.py`）。领星售价 / 常规价 / 导入价超过它就当作无效、不写库并提示，申报价校验也用它。数值是 Bot 按“单件商品售价不会超过 10 万美元”自定的，用户可改。
- **待用户决定（S9-B：D-12 盲区提示，s9-step2 评审 §四 测试 BOT 意见）**：首次同步时 `_track_nonpromo` 会把当时售价记成“近 90 天非促销价”，之后无法区分“只有这一条自记录”和“确有历史正常价”。测试 BOT 建议：新增 `last_nonpromo_origin`（self_first / confirmed / unknown），首次无参照时记 self_first，之后有参照再次记录、出现有效常规价或用户手动确认时改 confirmed，过期后重新自记再置 self_first；旧数据统一标 unknown，不要一次性全部提示；提示只是提示，不改申报价（D-12），也不能建议用 list_price / history_price（D-13）；新 SKU 首次同步大多本来就是正常价，噪声大，可加“首次记录后 N 天内才提示”或只在报关导出时提示一次；更简单的替代：样本数 / 跨度判断，或比较 last_nonpromo_at 与首次同步时间，或只在预览里对新 SKU 提示。需要用户决定：
  1. 要不要这个提示，显示在哪里（预览 / 报关导出 / 两处都显示）；
  2. 多少次或多少天算“有历史”；
  3. 旧数据（无法区分来源，标 unknown）要不要提示；
  4. 能不能手动确认正常价来消除提示；
  5. 旧常规价要不要设有效期（A2：领星不再返回常规价时，库里旧值会一直参与 D-12 判断；本次不设）。
- ~~产品库还没有 declare_unit 字段~~（S2 已加）。~~按行毛重在混装箱时重复计~~（S3-3 已修：合并行按箱去重）。
- ~~待用户回复：单件装、标准尺寸、23kg 的箱子~~ 已定：D-2026-10-16-05，只提示不拦截（2026-10-16 08:10 ET 用户书面确认）。
- 产品表能否用 MCP 直接生成（D-2026-10-16-02）：S3 期间只读拉了 erp_listing（FBA，104 行，按 MSKU 去重 74 个 SKU），写进盒子临时库 /workspace/s3_mcp/appdata（未碰真实 app_data）。能直接生成：SKU、ASIN（74/74）、FNSKU（65/74）、listing_price（73/74，美元）、local_name（56/74）、品牌/英文名等。拉不到（MCP 没有这些字段）：报关中文品名、HS、申报单位、品类、单品/箱规尺寸与重量——这些仍需网页编辑或 Excel 批量导回（S3-0）补齐。
- 待办（不阻塞）：Excel 样表导入 load_from_excel 仍用 _to_int/_to_float 静默填 0，建议 S2 或 S7 改成同样的报错方式（方案 3.1 验收第 2 条要求 16 个样表逐值一致，届时一并做）。
- ~~待核实：九方 3 份发票缺货件 CSV~~ S4-fix1 已从测试目录补齐（第11批 装箱信息\FBA19JQTB2XL.csv、第14批 SEND\箱单 两份）。这 3 票仍缺九方“单箱数据”，实测值取自样例 Packing list。

### 7. S2 产品库与领星（tag s2-products → s2-fix1）— ✅ 全部完成，第 4 节 S2 各项均为已完成，无延后项
- 领星 MCP 实测（只读，erp_listing）：msku/local_sku/fnsku/asin/parent_asin/item_name/local_name/status_text/fulfillment_channel_type/listing_price_currency_code/currency_symbol；价格字段 listing_price(=price=regular_price，实时售价)、landed_price、list_price(划线价)、b2b_price、history_price。映射见 backend/config/lingxing_field_map.json。
- **Listing 来源（依据 docs/用户决策记录.md D-2026-10-16-01（06:04 对话原话 + 06:27 书面确认，美东））**：以 MCP erp_listing 拉取为主（预览确认后写入）；Excel/CSV 文件导入只作备用。
- **申报价（按实时售价报；依据 docs/用户决策记录.md D-2026-10-16-01（06:04 对话原话 + 06:27 书面确认，美东））**：领星 listing_price > 手填 declared_value > 领星 price/landed_price 兜底 > 旧 declared_value（legacy，警告）。领星售价不受手填锁定，领星有值时手填价不覆盖申报价。list_price/regular_price 不用。无价格：导出阻断（422），不再填 0。领星价比旧申报价低 20% 以上提示；**手填价存在但未采用时一律提示 `manual_price_not_used`（s2-fix2）；与采用价相等不提示，降价 20% 按原值比较、正好 20% 不提示（s2-final）**。预览里显示每个 SKU 的申报价来源。
- 价格差异：金样快照 X00DEMO002 29.99、X00DEMO001 28.99，领星实时均为 15.99；按用户决定以实时售价为准，导出时会有“大幅下降”提示。
- 手填锁定：除售价外，手填字段对 MCP 预览确认、领星文件导入都锁定，预览标 locked、默认不勾；写入字段来源记 lingxing。
- local_name 存新列 local_name，不覆盖报关中文品名 chinese_name。
- 品类/HS：category 为空的老产品按 pet；钓具（fishing）HS 和要素等报关行确认（E4）后在 `/api/master-data/hs-templates` 录入，未录入前导出阻断。
- fba_warehouse：琪珞「！」表 476 行 → 471 个代码入库（含 Walmart、加拿大仓、同仓备用地址如 MDT2-1；重复 HLI2 取后一行并提示）；只有亚马逊格式代码进仓库白名单。分区按州：美西/美中/美东。
- customs_rule_profile：默认宁波北仑、101、海路运输、净重每箱扣 0.2、运费和出口/申报日期留空；报关口岸/征免性质/运输方式默认值改从这里取。~~净重算法仍以 user_settings 为准~~ S3-1 起净重算法也只认 customs_rule_profile（net_weight_mode / net_minus_per_box / net_ratio）。
- shipment_ticket：按 FBA 号关联，来源排名 manual > tencent > freight = jiufang；毛重以腾讯表格为准（v5 Q2），九方实测逐箱明细存 boxes_json；总运费只作参考，不写报关单；运费测算表“合同协议号”列里不是订单号的值（如“买单出口”）不导入并提示。
- 密钥：lingxing.json 只存 mcp_key_enc（DPAPI，当前 Windows 用户）。**真实 app_data 里的旧明文会在用户下次启动软件、读取设置时自动迁移**（测试不碰真实 app_data）。换电脑/换用户需重新填写密钥。
- MCP 没有本地产品/箱规接口，箱规走 xlsx 模板导入。~~领星 Listing 导出列名仍【待用户提供导出样本】核对~~ 已撤销（D-2026-10-16-02，07:14 美东：产品表以 MCP 真实数据为唯一来源，导出列名核对撤销，文件导入仅备用）。
- 测试隔离：conftest 设置 FBA_APP_DATA_DIR 到临时目录；新用例都用 tmp 库。
- 决策出处：`docs/用户决策记录.md`（D-2026-10-16-01；D-2026-10-16-02：产品表以 MCP erp_listing 真实数据为唯一来源建表、以后 MCP 定期拉取更新，领星导出文件列名核对撤销，文件导入仅备用、不再列待办）。方案 L40/L83/L92/L150/L159/L261/L279/L299/L325/L435、规则清单 L68/L233/L278/L292、`待确认问题_初版答案.md` Q4 已改成新口径并引用该记录（修改前备份为 `*_s2fix2前备份.md`）。
- golden：README 与 `invoice_manifest.csv` 13 条 expected_warnings 改为“无”（新口径下来源 lingxing，不出回落警告），`test_golden_infra.py` 加用例锁定。
- 仓库表「！」476 行里有 4 行仓库代码为空，导入时跳过（不计入 471）。
- 下一步：~~S3~~（已完成，tag s3-customs）→ S4a 发票模板盘点。

### 8. 更新记录
- 2026-10-16 05:00 ET：完整备份完成；S1a 完成（tag s1-baseline，commit 8404f4b）。
- 2026-10-16 05:1x ET：S1b 完成：38 份报关 + 13 份发票样例副本、manifest、产品库快照（14 个 FNSKU，declared_value 全空）、compare_golden.py、test_golden_infra.py（15 条）。
- 2026-10-16 05:2x ET：S1c 完成：parse_smart_text_detailed（表头识别、FNSKU、Tab/逗号/空格、NFKC 全角、千分位、带单位提示、错误 {row,field,value,message}）；/api/parse_text 出错返回 422（detail.message 前端直接显示）；test_parse_text.py 16 条。
- 2026-10-16 ET：S1d 完成：backend/security.py（FBA_HOST 默认 127.0.0.1；非本机地址无口令拒绝启动；FBA_ACCESS_TOKEN 可选，启用后 /api/*（health、auth/login 除外）需 X-Access-Token 头或 cookie；浏览器打开 /api/auth/login?token=口令 写 cookie）；main.py 去掉 0.0.0.0；test_security.py 15 条。默认不启用口令，行为与原来一致。
- 2026-10-16 ET：S1e 完成：fba_compliance 用 Decimal + 精确系数（lb_to_kg_exact/in_to_cm_exact），22.5 预警/22.68 阻断/63.5cm 多件箱阻断（新增 box_side_violations 计入 blocked）/45.36 Mechanical Lift；单件箱重>22.68 或单件重>22.68 直接算大件（Team/Mechanical Lift 提示，不阻断）；placement_fee 改精确系数；test_fba_rules_s1e.py 20 条。注意：摘要里旧用例“标准尺寸 23kg 阻断”按 v8 理解为多件箱阻断，单件 23kg 按 v8 算大件只提示。sta_template_export 的 2.2046 仅用于 STA 导出显示，未改。
- 2026-10-16 ET：S1f 完成：征免性质 101、海路运输（写 报关单!E6）、合同!A33 装运口岸宁波北仑、委托书!E12 当年 12 月 31 日（都可用 overrides 改）、运费 K12 清空、出口/申报日期默认留空并清掉模板 H3 旧日期；单价 HALF_UP、总价=凑整单价×数量；净重=毛重−0.2×箱数（settings 可选 ratio）；修正毛重原写进 G12(净重格) 的错误→F12 毛重/G12 净重；毛重按箱累加不再重复计混装箱；单位取产品库 declare_unit/申报单位，缺省“件”；test_customs_defaults.py 13 条。核实结果：模板 报关单!H7 本来就是“（101）”、E6 本来就是“海路运输”，所以 601/海运运输 只是代码默认值，导出结果原本无误，本次只改默认值并加测试锁定。
- 2026-10-16 ET：S1-fix1 完成（D1–D4 + 千分位提示 + 登录 POST + .gitattributes），tag s1-fix1。
- 2026-10-16 ET：S2 完成（S2-1~S2-7），tag s2-products。
- 2026-10-16 ET：S2 验收 81 分后补齐方案 3.2 全部范围（票级导入器、DPAPI 密钥、category/HS 模板/钓具缺配置、fba_warehouse/customs_rule_profile 及初始导入、MCP 锁定修复、申报价警告与阻断、白名单修正、local_name/币种），并按用户决定改申报价优先级、MCP 为主；tag s2-fix1。
- 2026-10-16 ET：S2 复测 96 分后修正（s2-fix2）：新建 docs/用户决策记录.md（06:04 原话 + 06:27 书面确认），方案/规则清单/Q4/项目文档改新口径并引用；golden 期望警告更新；手填申报价未采用一律提示。
- 2026-10-16 ET：S2 收尾（s2-final）：方案 L82 改为“文件导入（备用通道）”，规则清单 L261 标“已被 D-2026-10-16-01 取代”，决策记录 06:04 出处注明“与 New Bot 的主对话（用户消息）”；代码：相等价不提示未采用、降价按原值比较。
- 2026-10-16 ET：S3 第 0 步“产品库本地编辑”（D-2026-10-16-03，07:15 美东）：网页可编辑字段增加 品类/申报单位/本地品名/单箱毛重；网页 PATCH 改任何字段都记 manual 并锁定（修复：之前 brand/english_name/chinese_name/hs_code 等非 WRITABLE 字段改后不记来源，MCP 会覆盖）；新增 GET /api/master-data/export.xlsx 导出、POST /api/master-data/import/edits/preview|apply 导回（先预览改动，确认后写入，留空不改、未知 SKU/非数字报错不写）；申报价仍按 D-2026-10-16-01 领星优先。
- 2026-10-16 ET：D-2026-10-16-04（07:16 美东）：S4 扩大为全部发票模板（含琪珞等货代）可配置映射 + 自动识别/手选；先写 docs/发票模板清单.md，S3 完成后按 S4a 开始。取代 Q6“琪珞不再投入”。
- 2026-10-16 ET：S3 报关导出完成（tag s3-customs）：规则引擎、单元格/日期、订单号与文件名、一致性校验、.xls 导出、38 份报关 golden（xlsx/xls 失败 0）、钓具验收；PC 需安装 xlwt==1.3.0（随补丁离线 wheel 安装）。
- 2026-10-16 ET：S4a 发票模板盘点完成，清单写在 docs/发票模板清单.md（8 套模板、字段差异、5 个待确认点）。
- 2026-10-16 ET：S3-fix1 完成（tag s3-fix1）：毛重/净重 > 0 校验、货代毛重差异提示、混装分摊规则、golden 九方样例不一致说明、方案 §6 申报价口径；决策 D-05（单件 23kg 只提示，08:10 ET 确认）、D-06（08:11 ET：“不确定的东西，你就搜索权威资料”——拿不准的规则先查权威资料并在文档注明出处，只有用户业务数据才请用户确认）。

- 2026-10-16 ET：S4-fix1（S4 评审 91.5 分，报告 docs/评审报告/S4_测试评审.md）交付，tag s4-fix1：SEND / 九方发票导出适配器 + invoice_rules；golden 改为以 13 份货代原始样例为期望（2557 格，失败 0，已知差异 24）；解析侧对 CSV / 九方单箱数据原件独立核对；D-09 第 2 点按 D-08 重写（T6 单件实重不设默认，CSV 判定）；核对修正改为确认后生效、多口径不采用、仓库取 CSV 配送地址、无 CSV 标未核对；T5/T7 同分不自动选；坏 JSON 配置、S1–S3 回归、真实 app_data 不变测试。盒子全套 585 passed / 1 skipped。S4 **待评审**，评审通过前不写“完成”。
- 2026-10-16 ET：S4 复测 99.1 分通过（docs/评审报告/S4_测试评审_v2.md）；收尾 tag s4-final：SEND 尺寸逐格登记 + 正向核验、待分配货件九方箱唛为空提示、VGT2 地址按亚马逊官方公告纠正（config/fba_warehouse_corrections.json）。
- 2026-10-16 ET：S5 领星 MCP 定时同步交付 tag s5-sync（asyncio 定时、默认关闭、锁防重入、失败重试+日志、D-02 自动写入/手填锁定/申报价 D-01 例外、只读白名单、DPAPI、同步记录与差异界面），待评审。
- 2026-10-16 ET：S7-fix1（评审 98.6 的 5 项 + 建议项），版本号改 V3.0，tag s7-fix1，S7 仍待评审。
- 2026-10-16 ET：S7-archive（D-11）：重复件按引用检查后 git mv 到 archive/（2 个文件），不删除、不重新打包；评审 v2 的 3 个轻微项记为待办；tag s7-archive，S7 仍待评审。
- 2026-10-16 ET：S5-fix1（tag s5-fix1）：改间隔立即重算下次时间；上次成功时间取自数据库，启动按“上次成功+间隔”计算、过期 60 秒后补跑；白名单拒绝/缺密钥/鉴权失败不重试并立即释放锁；共用锁改真实并发测试。另核对 HANDOFF_交接清单.md（仓库根目录） 被覆盖一事：测试员 09:22 的快照与 git s4-fix1 版本逐字一致，历次 git 版本删掉的行都是有意改写的状态行，没有发现丢失；以后覆盖前先备份到 /workspace/handoff_backup/。待评审。
- 2026-10-16 ET：S5-fix1 复测 99.8 分通过，S5 标完成，tag s5-final。
- 2026-10-16 ET：S7 工程整理交付 tag s7-cleanup（config 统一 *.default.json、Streamlit 归档、依赖锁定、前端 tsc 0 错误并完整打包、Step 4.5 货代发票导出面板、领星鉴权错误文字按真实返回改准、端到端冒烟脚本、用户使用说明），待评审。
- 2026-10-16 ET：S8 深度测评 V3.0 修复（4 中等 + 14 轻微 + D-12 + HS 校验/钓具参考），版本号 V3.1，tag s8-fix，待评审；S7 仍待评审。
- 2026-10-16 ET：S8 复测 93.0 未过；S8-fix1（D-12 端到端修复、发票重量口径按 CSV 核对、三个新适配器对原件测试、pyc 取消跟踪、6 条弱测试加强、决策记录与钓鱼线说明更正），V3.1 重打，tag s8-fix1，待评审。
- 2026-10-17 ET：S9-step2-fix（tag s9-step2-fix，832 passed）；S9-step2-fix2（tag s9-step2-fix2，918 passed）：价格解析统一拒绝欧式写法 / 超大数 / 舍入为 0 / 科学计数法，单行无效只跳该行，Excel 导入 422 带行号原值；403 限流可重试、JSON-RPC 鉴权判定收紧；预览面板用词与展示改进；文档品牌名、金样 FNSKU 脱敏。


---

# 附录 E：深度测评报告 V3.0（94.3 分，S8 的修复依据，全文）

## FBA Smart Tool V3.0 深度测评报告

- **被测版本**：tag `s7-fix1` = 048c9b2，代码提交 48107b8。副本位于 `%TEMP%\fba_s1_verify`（HEAD 048c9b2，工作区干净）。
- **测评角色**：模拟美国站卖渔具的 FBA 卖家，日常商品为碳素路亚竿 7 尺（M/MH 两个变体）、纺车轮 3000/4000、路亚饵 120 件套、单件 23 kg 船锚。另外复用测试文件夹里的真实素材：`test1` 五票、`backend/templates` 五票 CSV 加箱唛 PDF、golden 的 93 份货代原件、领星接口样例、15 MB 产品信息表。
- **环境与方法**：在用户电脑 HuangYHPC 上，每个测评脚本用一个独立的临时数据目录 `%TEMP%\fba_deep_ad_*`，通过 FastAPI TestClient 调用真实接口；领星用 mock 客户端，Key 为假 Key `lxFAKEKEY-…TESTONLY`；便携包里的 exe 放到**中文加空格路径**下实际启动。
  - **浏览器里的点击操作没法做**，改为“接口测试 + 前端代码审查”，下文逐项注明。
  - 测评脚本保存在 `%TEMP%\fba_deep\pA–pF.py`，结果保存在 `res_*.json`。
- **安全情况**：
  - 真实 app_data 共 54 个文件，测前测后 SHA256 和 mtime **0 差异**。
  - 没有用真实 Key 或账号，没有删除任何文件；“打开本地 Excel”接口会启动系统程序，所以没有调用。
  - 原仓库我没有动过。测评期间原仓库 HEAD 从 048c9b2 变成了 `fdc7b06`，是开发方的新提交，工作区干净；本报告仍以 048c9b2 为准。
- 时间均为美东时间（ET）。

---

### 总评：**94.3 / 100**（按日常使用频率加权）

核心链路能跑通，安全基线做得扎实：
- 领星只读，Key 用 DPAPI 加密且只显示掩码；
- 手改字段会锁定，申报价跟随领星价（D-01）；
- 写操作先预览再确认；
- 坏文件基本都返回清楚的 4xx，不会崩溃；
- 并发和大文件稳定；
- 便携版在中文路径下也能启动，只绑定本机。

主要短板在“边缘模块”：
- 货代表的仓库代码只从文件名取；
- 尾数分配不校验数量；
- 8 个发票模板里只有 2 种能导出，T1–T8 识别没有界面；
- 部分接口的异常输入返回 500 或被悄悄忽略。

| # | 模块 | 得分 | 一句话结论 |
|---|---|---|---|
| 1 | 领星产品库同步（mock） | **97** | 只读、加密、预览确认、跨店去重、防重复确认都正常；乱码 MSKU 和缺 FNSKU 的条目不提示 |
| 2 | 产品管理 | **94** | 字段锁定和 D-01 正确，Excel 往返和坏数字报错正常；网页编辑校验偏弱 |
| 3 | 创建货件与分箱 | **92** | D-05 正确，CSV 和箱唛的交叉校验有力；尾数分配不限数量，可能超发 |
| 4 | 报关单导出 | **95** | 能导出 xlsx 和 xls，货件勾选和来源校验正确；渔具 HS 模板为空，内容核对依赖已有 golden |
| 5 | 发票导出（T1–T8） | **89** | 识别解析覆盖 6 种模板；导出只支持 SEND 和九方；T5 样例无法自动识别，也没有界面可以手选 |
| 6 | 货代对比（刷仓货代表） | **86** | 合并和小计正确；**仓库代码只从文件名取**，文件名里没有仓库代码就变成“1/2/3” |
| 7 | PDF 标签处理 | **94** | 批量转换、中文文件名、热敏标签都正常；坏 PDF 返回 500，尺寸参数不校验 |
| 8 | 定时同步与重启补跑 | **98** | 间隔边界、立即同步、记录、重启后计算、日志脱敏都通过 |
| 9 | 配置、启动器、便携包 | **96** | 中文路径 4.4 秒启动，只绑定 127.0.0.1，坏 JSON 有提示；横幅删文件后不消失 |
| 10 | 其它功能 | **96** | 路径穿越防护有效；仓库里的端到端脚本已失效且不在测试套件内；有一条测试不稳定 |

加权方法：模块 2、3、5 各占 15%，1、4、6 各占 10%，7、8、9、10 各占 6.25%。

**严重缺陷：无（没有“严重”级）。中等缺陷 4 个：D1、D2、D3、D4。**

---

### 一、功能清单（通读 17 个路由文件、5 个前端页面路由和 23 个组件后整理）

| 区域 | 接口 / 页面 | 本次覆盖 |
|---|---|---|
| Step1 录入 | /api/parse_text、parse_text/deepseek、parse_excel、validate_input、compute_preview、input_template；`step1-workspace`、成本看板 | ✔ |
| Step2 排箱 | calculate_boxes、box_metrics、tail_pool、box/assign_tail；`step2-workspace` | ✔ |
| Step3 导出 | export/step3/preview、internal、amazon | ✔ |
| Step3.5 刷仓货代表 | routing/preview、export、snapshots | ✔ |
| Step4 货件校验 | shipments/parse、validate、validate/stream；导出 worker_packing、shipping_sheet、forwarder | ✔（stream 只做了代码审查） |
| Step4.5 发票 | 旧流程 invoice/preview、generate、apply_edits、export_invoice；新流程 invoice-export/*；invoice-templates/detect、parse | ✔ |
| Step5 报关 | customs/preview、export；exporters；tickets 导入；customs-rule-profile；hs-templates | ✔ |
| 产品库 | master-data/*（list、sku、patch、delete、export、edits 导入、listing 和 carton 导入、仓库地址库、local-excel） | ✔（local-excel/open 没测） |
| 领星 | lingxing/settings、sync/stream、preview、confirm、alerts、last-run、schedule、run-now、runs、sync-log | ✔（mock） |
| PDF | pdf/sizes、convert_labels(/stream)、thermal_labels；`pdf-labels` 页面 | ✔ |
| 配置与其它 | config/*、templates/*、history/files、tasks/history、forwarders CRUD、health | ✔ |

---

### 二、各模块详情

#### 模块 1 领星产品库同步 — 97
| 用例 | 结果 |
|---|---|
| 保存假 Key → 返回 `lxFA****ONLY`；GET 接口不返回明文；遍历临时 app_data 所有文件，没有明文 Key | 通过 |
| mock 同步（SSE）：实际调用的只有 get_my_sids、get_multi_platform_shop_list、erp_listing、get_fba_stock_list、query_fba_valid_list、query_product_performance_asin_lists，全是只读 | 通过 |
| 8 条 listing 里，FISH-REEL-3000 在两个店铺各有一条 → 预览里只剩 1 条（去重） | 通过 |
| 预览不写库；确认后 7 个 SKU、60 个字段写入；**重复确认同一次预览返回 409** | 通过 |
| 乱码 MSKU `FISH-LINE-é锟斤拷`、FNSKU 和 ASIN 都为空的条目：作为“新品”默认勾选，**没有任何提示** | 轻微缺陷 D10 |

#### 模块 2 产品管理 — 94
| 用例 | 结果 |
|---|---|
| 网页编辑英文名、HS、中文名 → 记为 manual；再同步时预览里 english_name 显示 `locked=True`，确认后不被覆盖 | 通过 |
| **D-01**：网页把价格手改为 99.99，领星实时价改为 24.99 → 产品库跟随 24.99；导入时改价为 1.0，领星价改为 35.55 → 跟随 35.55；报关取价 `单个货值=35.55，申报价来源=lingxing` | 通过 |
| Excel 导出 → 批量改中文名、写入坏数字“十二”、加一行重复 SKU、加一行未知 SKU 后导入：坏数字和未知 SKU 都逐行报错，坏数字没有写成 0 | 通过 |
| 同一文件里**重复 SKU 的两行**都列为变更，最后一行生效，没有重复提示 | 轻微缺陷 D11 |
| 15 MB 产品信息表导入用时 1.5 秒；空文件、乱码、CSV 冒充 xlsx 都返回 422 | 通过 |
| 20 个线程并发编辑同一个 SKU，没有报错 | 通过 |
| **网页编辑数字字段填 `abc` → 返回 200，原值 55 不变**（被悄悄忽略，用户以为已经保存） | 轻微缺陷 D5 |
| HS 编码填 `12ab` 被接受（不校验 10 位数字） | 轻微缺陷 D5 |
| PATCH 一个**不存在的 SKU → 直接新建一条产品**（输错 SKU 会产生垃圾数据） | 轻微缺陷 D6 |

#### 模块 3 创建货件与分箱 — 92
| 用例 | 结果 |
|---|---|
| 渔具 6 款的预览、校验、排箱、矩阵预览，以及内部表和 Amazon 表导出 | 通过 |
| 坏数据（负数、装量为 0、非数字、空 SKU）被 validate_input 逐项指出 | 通过 |
| **D-05**：单件 22.5 kg 加纸箱，毛重 23.0 kg → `blocked=False`，提示贴 Team Lift；一箱 2 件、毛重 23.5 kg → 拦截；单根 190 cm 的竿按单件大件豁免；4 根一箱、190 cm 的竿 → 按亚马逊 25 英寸规则拦截 | 通过 |
| Step4：CSV 加箱唛 PDF 交叉校验通过；CSV 和箱唛错配能发现；GBK 编码 CSV 正常；空、乱码、只有表头、截断的 CSV 和坏 PDF 都给出明确错误，不会崩溃 | 通过 |
| 五票 CSV 加五份箱唛一起校验通过；8 个校验、4 个导出、8 个编辑并发跑，没有报错 | 通过 |
| **尾数分配接受 999 件（尾数池只剩 2 件）**：后端 `routers/boxing.py` L73–90 不校验，前端 `step2-workspace.tsx` L208–216 的输入框只设了 min=1。超额后的箱单照样能导出 Amazon 表（矩阵里第 1 箱显示 1005 件） | **中等 D1** |
| 同一个 CSV 上传两次，只给一条警告“重复的 CSV 货件编号”，ok=True | 轻微缺陷 D12 |
| Step1 填 SKU 简称（HUI-2PCS），在没有 SKU 映射的新库里对不上 Merchant SKU，Step4 判漏发和多发。仓库自带的 `test_e2e_workflow_simulation.py` 就是这样构造数据的，所以它现在**跑不过**；而且文件里没有 test_ 开头的函数，pytest 不会收集它 | 轻微缺陷 D13 |
| parse_text 只支持结构化写法，“每箱4支”“190*12*12cm”这类写法会解析失败，但报错清楚 | 不扣分，属设计限制 |

#### 模块 4 报关单导出 — 95
- 五票 Step4 结果 → 报关预览返回 200；xlsx 和 xls 都能导出。
- 勾选不存在的货件返回 400；货件 ID 写成小写也能匹配；来源 A 缺发票草稿返回 400；没有货件返回 400。
- 货代运单导入：81 票写入；“订单编号格式不对”的行逐行报告，不导入。
- 渔具 HS 模板（hs-templates?category=渔具）为空，渔具要靠产品库逐个填 HS。这属于配置缺失，记为风险，不扣分。
- 报关内容逐格正确性：本轮依赖现有 golden 和全套测试（上轮 629 passed），没有用渔具产品独立核对 → 部分未测，扣 5 分里的大头。

#### 模块 5 发票导出（T1–T8）— 89
**8 个模板的实际实现情况**（`config/invoice_template_map.json` 加实测）：

| 模板 | 名称 / 货代 | 识别 + 解析（读货代文件） | 按模板导出 |
|---|---|---|---|
| T1 | 九方·下单模板（新） | ✔（1/1 份） | ✘ |
| T2 | SEND Invoice Template | ✔（5/5 份） | ✔ SEND 适配器 |
| T3 | Commercial Invoice 9810（德速） | ✔（2/2 份） | ✘ |
| T4 | COMMERCIAL INVOICE 下单模板（旧，九方） | ✔ 去图片副本（1/1 份）；**`backend/templates` 下的原件只有“下单模板”一张表，匹配度 75%，识别不了，手动指定 T4 也被拒绝** | ✘ |
| T5 | 琪珞 黄底单行汇总 | **✘ 自动识别：第五批 5 份样例都与 T7 打平（各 1.0 分），按设计不自动选，parse 返回 422；手动指定 T5 可以解析** | ✘ |
| T6 | 琪珞 FBA 专线导入模版 | ✔（6/6 份） | ✘ |
| T7 | 义乌宁波运单（空白） | 只有空白模板，识别为 blank_template | ✘ |
| T8 | 九方系统导出 箱单发票 | ✔（8/8 份） | ✔ 九方适配器（Invoice + Packing list） |

- 结论：**识别和解析实现了 8 种规则**，6 种有样例能自动命中，T5 要手选，T7 没有填好的样例。**按模板导出只实现了 2 种**（SEND = T2 格式，九方 = T8 格式），琪珞和德速没有导出适配器。
- **前端完全没有调用 `/api/invoice-templates`**（全前端检索 0 处），T5 的“手动选模板”在界面上做不到 → **中等缺陷 D3**（开发方 S7 已列为已知局限，本轮仍计入）。
- SEND 和九方导出：缺发票必填字段时返回 409 并逐个列出 FNSKU；空 CSV 和乱码 CSV 返回 422。超长 CSV（3000+ 行）0.7 秒返回 409，没有崩溃。
- 传入不存在的货代 `deshu` 时，返回的是“请选择仓库”的 422，而不是“不支持该货代” → 轻微缺陷 D14（`routers/invoice_export.py` L64–78：先解析仓库，后校验货代）。
- 上轮遗留问题 **A**：仓库和 CSV 仓库代码冲突时不提示（详见第三节 P1）。
- 旧版发票流程：9 MB 模板预览 0.3 秒 ✔。

#### 模块 6 货代对比（刷仓货代表）— 86
- test1 五票合并：30 行；按 ONT8 → AVP1 → MDW2 → LAX9 → TOL3 的票序排列，5 条仓库小计 ✔。导出 xlsx ✔。
- **中等缺陷 D2：仓库代码只从文件名取。**
  - 代码：`routers/routing.py` L24–34 用正则从文件名提取，L63 调用，L75 **直接覆盖** CSV 里解析出的仓库代码。
  - 实测：`亚马逊FBA表1.csv`…`5.csv` 生成的货代表仓库列是 **1、2、3、4、5**，而 CSV 里实际是 RDU2、FWA4、ORF2、SMF3、GYR2。
  - 把 RDU2 那票的 CSV 改名为 `第一票ONT8.csv`，货代表里就写成 **ONT8**。
  - 亚马逊下载的原始文件名通常不含仓库代码，货代按这张表报价、派送会出错。
- `/api/routing/export` 传空数据返回 **500**（L126 抛出的 400 被 L130 的 except 包成了 500）→ 轻微缺陷 D15。

#### 模块 7 PDF 标签处理 — 94
- 5 份箱唛批量转 100×100：5.3 秒，输出 zip ✔。
- 自定义 60×40、中文文件名：Content-Disposition 带 UTF-8 文件名 ✔。
- 复用 Step4 结果生成热敏标签 ✔。
- 50 份 PDF 一次提交：75.8 秒完成（同步执行、没有超时，但耗时偏长）。
- **坏 PDF 或 zip 冒充 PDF → 500**；**坏 base64 → 500**（`routers/pdf_tools.py` L103、L150 把所有异常都包成 500）→ 轻微缺陷 D7。
- 尺寸参数 `-5`、`abc`、`100000 mm` 都返回 200 并照常生成（`_parse_mm` 在 L27 起，不校验范围）→ 轻微缺陷 D7。

#### 模块 8 定时同步与重启补跑 — 98
- 默认关闭 ✔。
- 间隔 14、0、-1、10081 返回 422；15 和 10080 返回 200 ✔。
- 立即同步（mock）：ok，attempts=1，记录状态 auto_applied ✔。
- 重启后计算：上次成功时间 14:56 ET 加 10080 分钟 = 10/23 10:56 ET ✔。
- 同步日志里没有明文 Key ✔。
- 补跑、致命错误不重试、共用锁：S5-fix1 已逐项实测，本轮没有重复。
- 扣 2 分：只有程序开着时才会同步，这是设计局限。另外 auto_apply 默认为 True，定时同步会**自动写入**新品和变更（锁定字段仍然受保护），用户可能没意识到。

#### 模块 9 配置、启动器、便携包 — 96
- 便携包复制到 `%TEMP%\渔具 测试 路径\`，并把临时数据目录也放在中文路径下：**4.4 秒**启动；只监听 `127.0.0.1:8002`；/api/health 返回 ok；数据库写进了临时数据目录 ✔。
- 运行中把 formulas.json 写坏 → `/api/config/errors` 立即报错，日志里有中文警告 ✔。
- 上轮问题 **B**：删除坏文件后，提示要重启才会消失（D8）。
- 启动器没有“不打开浏览器”的开关；启动横幅里的“数据目录”显示的是包内路径，与 `FBA_APP_DATA_DIR` 不一致（`run_app.py` L75、L187 附近）→ 轻微缺陷 D9。

#### 模块 10 其它功能 — 96
- 模板下载和上传的路径穿越 `..\..\` 都返回 400 ✔；新建货代必须提供模板 ✔；11 个只读 GET 接口全部返回 200 ✔。
- 历史文件下载要求 kind+name 两个参数，按代码审查看是白名单式读取，穿越测试没有构造成功，记为未测。
- 上轮问题 **C**：`test_forwarder_export_idempotent_with_subtotals` 仍不稳定（约 1.7%，原因是 docProps 里的时间戳）。
- D13：端到端脚本已失效（见模块 3）。

---

### 三、缺陷清单

| ID | 严重度 | 模块 | 描述 | 复现 | 位置 |
|---|---|---|---|---|---|
| D1 | 中 | 分箱 | 尾数分配不校验数量（也不校验 SKU 是否在尾数池），可分出远超尾数的件数，并能继续导出 Amazon 表 | POST /api/box/assign_tail，qty=999，target_box=1 → 200；再调 step3/amazon → 200 | `backend/routers/boxing.py` L73–90；`frontend/src/components/step2-workspace.tsx` L208–216 |
| D2 | 中 | 货代对比 | 仓库代码从文件名提取，并覆盖 CSV 里的真实仓库 | 上传 `亚马逊FBA表1–5.csv` → 仓库列为 1–5；把 RDU2 的 CSV 改名为 ONT8 → 写成 ONT8 | `backend/routers/routing.py` L24–34、L63、L75 |
| D3 | 中 | 发票 | T1–T8 识别解析没有任何前端入口；T5 和 T7 打平时没法手选，第五批 5 份真实样例无法使用；`templates` 下的单表原件 T4 识别不了 | 前端检索 `invoice-templates` 为 0 处；detect 第五批样例 → template_id=null，parse → 422 | `frontend/src`（缺入口）；`backend/routers/invoice_templates.py` L33–45 |
| D4 | 中 | 发票 | 8 个模板只有 2 种能导出，琪珞（T5/T6/T7）和德速（T3）不能按模板出发票 | GET /api/invoice-export/forwarders 只有 send 和 jiufang | `config/forwarders.default.json`（qiluo 的 export_adapter 为空） |
| P1 | 轻 | 发票 | 上轮问题 A：手选仓库、地址唯一对应的仓库与 CSV 仓库代码冲突时不提示 | 见 `S7_测试评审_v2.md` | `routers/invoice_export.py` L37–61 |
| D5 | 轻 | 产品 | 网页编辑数字字段填 abc 返回 200，但悄悄忽略；HS 编码不校验格式 | PATCH carton_length="abc" → 200，值不变；hs_code="12ab" → 200 | `backend/fba_tool/master_db.py` L496–497（_opt_float 返回 None 后不报错） |
| D6 | 轻 | 产品 | PATCH 不存在的 SKU 会新建产品 | PATCH /api/master-data/sku/NO-SUCH-SKU → 200 | `master_db.py` L492–494 |
| D7 | 轻 | PDF | 坏 PDF 或坏 base64 返回 500；尺寸参数不校验 | 见模块 7 | `backend/routers/pdf_tools.py` L27、L103、L150 |
| P2/D8 | 轻 | 配置 | 上轮问题 B：删除坏配置文件后，横幅要重启才消失 | 见 S7 v2 | `fba_tool/user_config.py` 的 CONFIG_ERRORS |
| D9 | 轻 | 启动器 | 没有关闭浏览器的开关；横幅里的数据目录与 FBA_APP_DATA_DIR 不一致 | 设置 FBA_APP_DATA_DIR 后启动 exe | `run_app.py` L75、L131/147/168 |
| D10 | 轻 | 领星 | 乱码 MSKU、缺 FNSKU 或 ASIN 的条目作为新品默认勾选，没有提示 | mock listing | `fba_tool/lingxing_preview.py`（新品分组） |
| D11 | 轻 | 产品 | 批量导入时同一 SKU 出现多行不提示，最后一行生效 | 见模块 2 | `fba_tool/product_edit.py` L63–111 |
| D12 | 轻 | 货件 | 同一 CSV 上传两次，只警告不拦截 | 见模块 3 | `routers/shipment.py` validate |
| D13 | 轻 | 测试 | `test_e2e_workflow_simulation.py` 已失效，pytest 也不会收集 | `python -c "import test_e2e_workflow_simulation as E…"` → Step4 失败 | `backend/test_e2e_workflow_simulation.py` L60–90、L268 起 |
| D14 | 轻 | 发票 | 未知货代返回仓库错误，而不是“不支持该货代” | forwarder_id=deshu | `routers/invoice_export.py` L64–78 |
| D15 | 轻 | 货代对比 | 导出空数据返回 500 | POST /api/routing/export，forwarder=[] | `routers/routing.py` L126–131 |
| P3 | 轻 | 测试 | 上轮问题 C：幂等测试比较 xlsx 字节长度，结果不稳定 | 300 轮里失败 5 次 | `backend/test_forwarder_export.py` L42–63 |

---

### 四、真实运营中的风险

1. **货代表仓库写错（D2）**：卖家直接上传亚马逊下载的 CSV（文件名一般不含仓库代码），货代表仓库列就是“1/2/3”或错误代码，货代会按错误仓库报价或派送，可能产生改派费或延误。目前只能靠在文件名里写对仓库代码，界面提示文案以“第一票ONT8.csv”为例，但没有强制。
2. **超发（D1）**：录尾数时手误（比如把 2 输成 20），程序不拦，Amazon 表和装箱单的数量就会大于计划。上传到 Send to Amazon 后会造成入库差异或亚马逊索赔。
3. **琪珞和德速票只能手工做发票（D3、D4）**：渔具卖家如果主要走琪珞专线（T5/T6），本工具帮不上发票导出，T5 文件连自动识别都做不到。
4. **定时同步默认自动写入**：开启后新品和变更会自动入库。手改字段受保护，但乱码或缺 FNSKU 的领星条目也会进库（D10），影响后续 FNSKU 匹配和报关。
5. **申报价完全跟随领星实时价（D-01，按设计）**：促销期间降价，报关价会跟着变低，存在低报风险。现有 S2 测试里有“与历史价相比跌幅过大”的警告，建议在报关预览里突出显示。
6. **渔具 HS 模板为空**：渔具、钓竿、渔线轮（9507.xx）要逐个填 HS，容易漏填或填错；而网页编辑 HS 不校验格式（D5）。
7. **单件 23 kg 船锚**：按 D-05 只提示贴 Team Lift，不拦截，行为正确；但提示只出现在 Step2 的合规信息里，工人装箱单上是否带出 Team Lift 标记没有核实（未测）。

### 五、改进建议
1. 货代表：仓库优先取 CSV 解析出的 `warehouse_code`；文件名里的代码与 CSV 不一致时给出警告。
2. 尾数分配：后端校验 `0 < qty ≤ 剩余数量`，SKU 必须在尾数池里，箱号必须存在；前端输入框设置 max。step3 导出前再核对一次各 SKU 的总数是否等于发货总数。
3. 给 T1–T8 识别加一个界面：识别结果、候选打平时手选模板、显示解析出的票据。补上琪珞和德速的导出适配器（至少 T6）。
4. 统一输入校验：网页编辑数字字段报 400；HS 校验 10 位数字；PATCH 不存在的 SKU 返回 404，新建走单独入口；PDF 坏文件和尺寸越界返回 4xx。
5. 领星预览：乱码、缺 FNSKU、缺 ASIN 的条目放进“待人工确认”分组，不默认勾选。
6. 预置渔具类 HS 模板（9507.10 钓竿、9507.30 渔线轮、9507.90 其他渔具）。
7. 测试：修好或删除 e2e 脚本，并改成 pytest 用例；幂等测试改为比较单元格；补上 D1、D2 的回归用例。
8. 启动器增加 `FBA_NO_BROWSER` 开关；横幅显示真实的数据目录。

### 六、未测项及原因
| 项 | 原因 |
|---|---|
| 浏览器里的实际点击、拖拽、表格编辑 | 不能操作用户的浏览器，改为接口测试加前端代码审查 |
| 真实领星账号同步、真实鉴权错误 | 规则禁止使用真实账号；S7 已用假 Key 复现过鉴权报错 |
| DeepSeek 智能解析 | 需要真实 API Key；只验证了没有 Key 时返回 400 |
| 渔具产品报关单逐格核对 | 没有渔具类货代或报关原件做期望值；报关正确性依赖现有 37 份报关 golden 和全套测试 |
| T7 填好的样例解析 | 素材里只有空白模板 |
| 打开本地 Excel（local-excel/open） | 会在用户电脑上启动外部程序，属于副作用，没有调用 |
| SSE 流式校验（validate/stream、convert_labels/stream） | 只做了代码审查，没有逐事件验证 |
| 工人装箱单是否带出 Team Lift 标记 | 时间所限 |
| 历史文件下载的路径穿越 | 接口需要 kind+name，只做了代码审查 |


---

# 第 14 节（s8-docs 新增）：仓库 docs/ 里的原始文档

| 文件 | 内容 |
|---|---|
| `docs/方案/FBA_Smart_Tool_优化方案.md` | v8 分模块方案、验收、评审对照 §8（代码注释里的“方案 v8 §x”指它） |
| `docs/方案/测试文件分析与规则清单.md` | 样例反推的规则、证据坐标、待确认事项 §7.1 |
| `docs/方案/待确认问题_初版答案.md` | 各决定的依据和链接 |
| `docs/用户决策记录.md` | D-01…D-12 全文（与附录 A 相同，以后改这份） |
| `docs/发票模板清单.md` | S4a 模板清单（与附录 B 相同） |
| `docs/评审报告/S1_测试评审.md` … `S7_测试评审_v2.md` | S1–S7 共 14 份评审报告（S1 93/99、S2 81/96/99、S3 98/98/99.5、S4 91.5/99.1、S5 97.8/99.8、S7 98.6/99.4） |
| `docs/评审报告/S8_测试评审.md`、`S8_测试评审_v2.md` | S8 93.0、S8-fix1 99.5 |
| `docs/评审报告/交接文档_评审.md` | 本交接文档评审（93 分） |
| `docs/评审报告/深度测评报告_V3.0.md` | 深度测评 94.3 分（与附录 E 相同） |

评审报告是原样保存的，里面的 `/workspace/...` 路径是原环境的，不用改。提交前已做密钥扫描（sk-、dpapi:v1:、ghp_、token/secret 等长串），0 命中。
