# 亚马逊 FBA 智能装箱与货件处理工具 — 后端

> S7（2026-10-16）：旧 Streamlit 入口已归档到 `legacy_streamlit/`；现在只有 FastAPI + React 一套。

FastAPI + `fba_tool/` 业务模块，为 React 前端提供 `/api/*` 接口。

## 工作流（7 步）

1. **发货录入** — 文本/DeepSeek/Excel、实时预览、2026 入库配置费  
2. **智能排箱** — 整箱 + 贪心混装 + FBA 合规校验  
3. **导出预览** — 内部留档表 + Send to Amazon 模板  
3.5 **分仓刷仓** — 分仓 CSV → 货代预览（可选）  
4. **回传校验** — CSV/PDF 交叉比对 + 工厂表/货代表  
4.5 **发票自动化** — 模板填充 + 在线编辑导出  
5. **报关资料** — 报关预览与导出  

## 开发启动

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.lock.txt -r requirements-dev.lock.txt   # S7：锁定版本（Python 3.9 / Windows 实测）
.\.venv\Scripts\uvicorn main:app --reload --host 127.0.0.1 --port 8002
```

API 文档：`http://127.0.0.1:8002/docs`

前端开发（另开终端）：

```powershell
cd frontend
npm install
$env:FBA_BACKEND_PORT="8002"
npm run dev
```

浏览器：`http://127.0.0.1:5173`

## 单机打包启动

```powershell
# 根目录
python run_app.py
```

或双击 `一键启动.bat` / `启动FBA工具.bat`。打包版由 FastAPI 同时挂载 `backend/dist` 前端 SPA，默认 `http://127.0.0.1:8002`。

## 目录结构

```
backend/
├── main.py              # FastAPI 入口 + SPA 挂载
├── routers/             # HTTP 路由（按步骤/功能）
├── services/            # 复杂流程编排（货件校验等）
├── fba_tool/            # 核心业务逻辑
├── schemas/             # Pydantic 请求/响应契约
├── templates/           # Excel 样表（可替换）
├── config/              # 出厂配置：*.default.json（首次运行复制到 app_data/config/，之后只改那边）+ 规则配置
├── legacy_streamlit/    # 已归档的旧 Streamlit 版（不再维护、不打包）
└── tests/ + test_*.py   # 单元/集成测试
```

持久化数据目录：`app_data/`（SQLite 主库、用户设置、历史文件等）。

## 通用表格：不写死 SKU / 箱数

- Step 2 锁定方案后，**实际 SKU 个数与箱数**决定导出列数与数据行数  
- 模板里原有样例行/列只是示例；程序会自动插行、扩列、清空旧数据区再写入  
- 直接替换 `templates/*.xlsx` 即可换版式，无需改代码  

## 用户可改参数

侧边栏「参数与公式（持久化）」或编辑 `app_data/config/`（出厂默认在 `backend/config/*.default.json`，不要直接改出厂文件）：

| 文件 | 内容 |
|------|------|
| `user_settings.json` | 重量上限、抛重系数、混装上限等 |
| `formulas.json` | Excel 公式模板占位符 |
| `sku_mapping.json` / `fnsku_mapping.json` | SKU 映射 |

## 本地测试

```powershell
cd backend
.\.venv\Scripts\pytest
```

端到端启动冒烟（真起后端进程，只用临时 app_data）：`.\.venv\Scripts\python ..\scripts\smoke_e2e.py`

## 依赖

- `requirements.txt`：直接依赖（下限）；`requirements.lock.txt`：运行时全部锁定版本；`requirements-dev.lock.txt`：测试与打包（pytest、httpx、pyinstaller）。
- 升级依赖：改 requirements.txt → 在干净虚拟环境安装并跑全套测试 → 用 `pip freeze` 更新两个 lock 文件。

## 使用说明

面向使用者的说明见仓库根目录 `用户使用说明.md`（产品库 / 发票 / 报关三大功能）。
