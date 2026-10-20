# 给下一次 AI 的交接说明（FBA Smart Tool V2.0）

> **现状说明（s8-docs，2026-10-16）**：本文是历史文档，内容停在当时版本，**不随代码更新**。现行说明看：用户 `用户使用说明.md`、便携包 `packaging/使用说明.txt`、开发 `backend/README.md`、代码定位 `FBA_Smart_Tool_代码架构定位手册.md`、交接 `交接文档_给新Bot.md` / `HANDOFF_交接清单.md`。


> 备份日期：2026-09-19  
> 产品界面顶栏：**U盘便携版 V2.0**  
> 本压缩包是 **源码交接**，不是便携版 exe。便携版另在仓库 `dist/FBA_Smart_Tool_V2.0_便携版/`。  
> 压缩包路径：`C:\Users\huang\Desktop\FBA_Smart_Tool_Cursor2026.7.1\FBA_Smart_Tool_V2.0_源码交接_给AI.zip`  
> 解压后根目录名：`FBA_Smart_Tool_Cursor_V2.0/`，先打开包内 `00_先读我.txt`。

**你是接手的 AI：先读本文件，再读 `FBA_Smart_Tool_代码架构定位手册.md`。不要全库盲搜。**

---

## 1. 这是什么

Windows 单机 FBA 工具：运营在浏览器走 **Step1 录入 → 2 排箱锁定 → 3 STA/内部表 → 3.5 刷仓 → 4 PDF/CSV 校验 → 4.5 发票 → 5 报关**。另有独立页 `/master-data`（产品主表 + 领星同步）、`/pdf-labels`。

技术栈：FastAPI（`backend/fba_tool/`）+ React 19 / Vite / TanStack Router。主数据在 SQLite `app_data/fba_master.db` 表 `product_master`（SKU=MSKU 主键）。

现行入口：仓库根 `run_app.py` + `backend/main.py`。`backend/app.py` 是旧 Streamlit，不要当入口。

---

## 2. 压缩包里有 / 没有

**有：** 源码、测试、`scripts/`、`packaging/`、`backend/templates/`、`backend/config/` 出厂默认 JSON、架构手册、本交接说明、开发用 `一键启动.bat` / `一键重启.bat`。

**没有（刻意排除）：**

| 排除项 | 原因 |
|--------|------|
| `app_data/` | 用户库、会话、**领星 MCP 密钥** `app_data/config/lingxing.json` |
| `frontend/node_modules/`、`backend/.venv/` | 依赖，需本地重装 |
| `dist/`、`build/`、`_internal/`、PyInstaller 产物 | 构建输出，不要手改 |
| `frontend/dist/`、`backend/dist/`、`backend/dist2/`、`backend/static/` | 前端同步产物，打包脚本会再生 |
| `scratch/`、`history/`、`test1/`、`*_export_test/` | 探针/样票，不是现行源码 |
| `*.zip`、`.env`、密钥 JSON | 体积或泄密 |

本机密钥不在包内。用户机器上领星 MCP 仍在 `app_data/config/lingxing.json`（`mcp_url` + `mcp_key`）。**永远不要把该文件打进仓库或压缩包。**

---

## 3. 接手后怎么跑（开发）

仓库根：

```
一键启动.bat
```

调用 `scripts/start_dev.ps1`：后端端口 **8000–8099**，前端 **5173–5199**，写入 `.dev/ports.json`。Vite `/api` 代理每次请求重读该文件。

重启前后端（只杀本应用记录的 PID）：

```
一键重启.bat
```

环境（若本机没有）：

```
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
cd ..\frontend
npm install
```

测试：

```
backend\.venv\Scripts\python -m pytest backend -q
cd frontend && npx vitest run
```

上次深度测试：**pytest 167 passed / 1 skipped，vitest 56 passed**。

---

## 4. 怎么打便携版（只走这一条）

```
powershell -ExecutionPolicy Bypass -File scripts/build_standalone.ps1
```

版本号权威：`scripts/finish_portable_dist.py` 的 `RELEASE_VERSION = "V2.0"`，以及 `frontend/src/components/app-header.tsx` 顶栏文案。  
`backend/main.py` 里 FastAPI `version="1.2.0"` **是 API 文档号，不要改成产品版号。**

**不要用：** `backend/build_v1.8.bat`、`FBAWizard*.spec`、Streamlit 旧打包。

便携包启动器是包内 `启动FBA工具.bat`，**不是** 仓库根 `一键启动.bat`。

打包 spec 已排除 `sessions`、`lingxing.json`、`invoice_history.json`。`finish_portable_dist.py` 忽略 `app_data`。

---

## 5. V2.0 相对此前已落地的能力

1. **领星 MCP 同步（预览后确认）**  
   - 主数据页一键同步。Listing **不直接写** `product_master`。  
   - `lingxing_sync` 拉 listing → `lingxing_preview.build_listing_preview` → 状态 `preview_pending`。  
   - 用户在 `lingxing-preview-panel.tsx` 按 SKU/字段勾选后 `confirm_lingxing_preview`。  
   - 同一 MSKU 多店铺（US/CA）会去重：优先美站，再已有 sid，再字段完整度。  
   - 默认勾选：新 SKU 远端有值的字段默认勾；身份字段变更默认勾；不一致字段默认不勾；本地已有 `english_name`/`brand` 默认不勾。  
   - 库存/补货等辅助表仍立即写入。  
   - 陈旧/已确认预览 → `LingxingPreviewError` 409。

2. **主数据数据流**  
   - 启动时 `catalog_seed.import_catalog_gaps_into_master()` 把 CSV 缺口补进 SQLite（`overwrite=False`）。  
   - 运行时发票/报关/STA/发货表/工人单 **只读 SQLite**，不再读运行时 `产品信息表.csv`。  
   - Step1「应用主数据」：FNSKU 可从主表补；外箱尺寸/每箱件数只填空，不覆盖用户已填。

3. **GitHub 开源排箱**  
   对比过 `gsisinna/3D-bin-packing-opt`（py3dbp）。现行排箱用的是 **外箱体积 ÷ 每箱件数** 的立方体，不是真实单件长宽高，3D 装箱收益很小，**未接入**。

4. **开发启动**  
   根目录一键启动；一键重启只杀 `.dev` 记录的本应用 PID；前端端口在 `npm` 前即时重选。

5. **货代导出列**  
   `_forwarder_display_columns` 固定输出全部 `FORWARDER_COLUMNS` 再追加额外列。重量列名是 **总实重(kg)**，不是 `实重(kg)`。

---

## 6. 改代码时的硬约束

- 对用户说话用 **简体中文**。未要求不要 git commit。  
- SQLite 只允许 `ADD COLUMN` / `CREATE TABLE IF NOT EXISTS`，不要破坏性迁移。  
- 实现期不要手改 `dist/`、`frontend/dist/`、`backend/dist/`。  
- 密钥不进仓库：`lingxing.json`、`.env`、PAT。  
- 前端全局状态只在 `frontend/src/context/workflow-context.tsx`。  
- HTTP 在 `backend/routers/`；装箱/货件/发票编排在 `backend/services/`；业务在 `backend/fba_tool/`。  
- 改正式下载先看 `frontend/src/lib/workflow-invalidation.ts`。  
- FNSKU：发货表/工人单走 `fnsku_resolve.resolve_fnsku`；Step3 内部留档/STA 只用 `load_static_fnsku_map()` + overrides。不要第三条链。

---

## 7. 按任务先打开这些文件

| 要改的事 | 文件 |
|----------|------|
| 领星预览/勾选/确认 | `backend/fba_tool/lingxing_preview.py`、`lingxing_sync.py`、`routers/lingxing.py`、`frontend/src/components/lingxing-preview-panel.tsx`、`lib/api/lingxing.ts`、`master-data-workspace.tsx` |
| 领星 MCP 客户端 | `backend/fba_tool/lingxing_mcp_client.py`（QPS ≥ 1s，`X-Mcp-Key`） |
| 主表 SQLite | `backend/fba_tool/master_db.py` |
| CSV 缺口导入 | `backend/fba_tool/catalog_seed.py` |
| Step1 应用主数据 | `backend/fba_tool/master_data_apply.py` |
| 产品主表页 | `frontend/src/components/master-data-workspace.tsx` |
| 工作流状态 | `frontend/src/context/workflow-context.tsx` |
| 开发启动/端口 | `scripts/start_dev.ps1`、`restart_dev.ps1`、`stop_dev.py` |
| 便携打包 | `scripts/build_standalone.ps1`、`packaging/FBA_Smart_Tool.spec`、`scripts/finish_portable_dist.py` |
| 架构定位（必读） | `FBA_Smart_Tool_代码架构定位手册.md` §6 |

更多任务表见手册 **§6**。

---

## 8. 已知坑（修过，不要回退）

- Listing 多店同 MSKU 曾触发 `UNIQUE constraint failed lingxing_sync_preview_sku.run_id,sku`。已用 `dedupe_listing_products` 去重。  
- `/master-data` 曾因 `Slider` 未 import 白屏。  
- `test_master_data.py` 曾把 `CARTON-SKU` 等写入 **真实** `app_data`；测试已加 `autouse` 隔离。本机库里若还有这些测试 SKU，可在主数据页删。  
- 货代导出测试列下标必须用 `FORWARDER_COLUMNS.index`。仓汇总重量键是 `总实重(kg)`。  
- 便携版 smoke 不要和开发 uvicorn 抢 8002（`SO_REUSEADDR` 会误判健康）。  
- PowerShell 里不要用 `curl.exe` 拼带括号的 JSON；改用文件或 Python。  
- pytest 用 `backend\.venv`，系统 Python 缺依赖。

---

## 9. MCP（本机 Cursor，不在压缩包里）

- 领星：`user-lingxing-mcp`，工具 `help` / `search` / `action`。  
- GitHub：`user-github`。  
- 本机配置在用户 Cursor MCP，不是这份源码。应用内领星走 `lingxing_mcp_client` + `app_data/config/lingxing.json`。

---

## 10. 用户未要求、不要擅自做的事

- 不要 git commit / push（除非用户明说）。  
- 不要删除 `dist` 里残留的 V1.8 文件夹（除非用户明说）。  
- 不要把领星密钥、PAT、`.env` 写进源码或再打进压缩包。  
- 未要求不要自动重启已被用户杀掉的开发服务器。
