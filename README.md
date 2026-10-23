# FBA Smart Tool

Local-first tool for Amazon FBA packing, shipment checks, forwarder invoices, and customs paperwork. It runs on your machine. This repository ships no API keys and no real customer shipments.

本地运行的亚马逊 FBA 装箱、货件核对、货代发票和报关工具。浏览器里操作，数据留在你自己的电脑上。

## 这是什么

运营同学每天要过几关：把货装进合规的箱子，对上亚马逊货件，按货代模板开发票，再整理报关资料。这些规则散落在表格、经验和各家货代的版式里，错一格往往要返工。

FBA Smart Tool 把这条流水线收成一台本机程序：FastAPI 做业务，React 做界面。开发时前端走 Vite，打包后由同一个后端挂出页面。默认只监听 `127.0.0.1:8002`。

它不是亚马逊或领星的官方客户端，也不代替你向平台或海关申报。算出来的箱规、申报价和报关栏位仍然要人核对。

## 为什么开源

我做这个工具，是因为这些步骤自己每天都要过。规则写在一个人的电脑里，对的地方别人用不上，错的地方也只有一个人能撞见。

把它开源，是把方法交出来：装箱和发票的边界可以一起看，货代模板和报关栏位可以一起补。我为人人，人人为我。你拿走用得上的部分；你若踩中一个箱号、一个申报价或一张货代表的坑，也请把修法送回来。

仓库里是程序和合成例子。你的货件、地址、售价和密钥留在你的机器上。

## 能做什么

工作流大致是七步（界面上的「发票」是 Step 4.5）：

1. **发货录入** — 文本、表格，或可选的 DeepSeek 解析
2. **智能排箱** — 整箱、混装和 FBA 合规校验
3. **导出预览** — 内部留档和 Send to Amazon 模板
4. **分仓刷仓**（可选）— 分仓结果给货代预览
5. **回传校验** — 亚马逊 CSV / 箱唛 PDF 和工厂表、货代表交叉核对
6. **发票** — 货代模板填充，Univer 离线预览后再导出
7. **报关资料** — 报关单、发票、箱单、合同等预览和导出

产品库可以手填、用 Excel 进出，也可以导入领星在售表：先预览，确认后才写入，写错可以回滚。领星 MCP 定时同步默认关闭，并且只做读取。

发票目前按这些货代模板走：SEND、九方、琪珞国际、琪珞 T5、琪珞 T6、德速。

## 功能边界

- 单机工具。业务数据在本机 `app_data/`（SQLite、你改过的配置、导出历史）。
- 领星 MCP Key、DeepSeek Key 由使用者自己填写，加密或保存在本机设置里。仓库不提供钥匙。
- 便携版面向 Windows。源码也可以在其他系统上跑开发和测试；正式 zip 只在 GitHub Actions 的 Windows 构建机上打。
- 出厂规则在 `backend/config/*.default.json`。你的改动写到 `app_data/config/`，不要改出厂文件来“保存设置”。
- 产品代际是 `V4`，写在 `backend/fba_tool/app_version.py` 的 `APP_VERSION`。FastAPI 自带的 `version` 字符串是 API 文档号，和产品版本无关。

更细的使用步骤见 `docs/使用说明.md`（文中个别版号可能还停在更早的交付说明上，以 `APP_VERSION` 为准）。代码地图见 `docs/架构说明.md`。

## 不含密钥，不含真实客户数据

这个仓库**不包含**：

- 领星 MCP Key、DeepSeek Key，或任何 token / password
- `lingxing.json`、`app_data/`、数据库、会话
- 真实领星在售导出（文件名带 `listing` 的 xlsx 会被发布扫描拒绝）
- 真实货件批次（`realdata/`）

`.env` 只保留占位示例（`frontend/.env.example`）。请不要把真实地址、货件号或密钥写进 issue 和 PR。

开源范围、仍留在仓库里的样表，以及 git 历史没有改写这件事，写在 [`docs/OPEN_SOURCE.md`](docs/OPEN_SOURCE.md)。

## 快速开始

需要 Python 3.12（与 Windows 便携包的构建机一致）和 Node.js 22。

后端：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.lock.txt -r requirements-dev.lock.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8002
```

API 文档：<http://127.0.0.1:8002/docs>

前端（另一个终端）：

```bash
cd frontend
npm ci
npm run dev
```

浏览器打开 <http://127.0.0.1:5173>。开发代理把 `/api` 转到后端。需要固定端口时设置 `FBA_BACKEND_PORT=8002`（不要指到 8000，除非后端真的在 8000）。

Windows 上也可以在仓库根目录运行 `python run_app.py`，或使用打包版里的 `启动FBA工具.bat`。打包版由 FastAPI 同时提供页面，地址一般是 <http://127.0.0.1:8002>。

## 界面

截图还在整理。补图时请打码货件号、SKU、FNSKU、地址、金额和任何客户名称。下面是留位，没有放图片文件。

<!-- screenshot: workflow-home.png — 工作流首页 -->

（截图待补：工作流首页）

<!-- screenshot: invoice-univer.png — Step 4.5 发票，Univer 离线预览 -->

（截图待补：发票预览）

<!-- screenshot: product-master.png — 产品库，以及领星导入的预览 / 确认 -->

（截图待补：产品库与领星导入预览）

<!-- screenshot: customs.png — Step 5 报关资料预览 -->

（截图待补：报关资料）

## 测试

```bash
cd backend
pytest
```

```bash
cd frontend
npm test
```

依赖本机私有文件的测试，在环境变量没设或文件不存在时会 **skip**，例如 `FBA_LINGXING_OWNER_XLSX`、`FBA_REALDATA_DIR`。没有这些文件，CI 仍然应该是绿的。细节见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 环境、测试、PR |
| [`docs/MAINTAINING.md`](docs/MAINTAINING.md) | 维护者职责、审 PR、分支和版本 |
| [`docs/RELEASING.md`](docs/RELEASING.md) | tag、GitHub Release、便携包和 SHA256 |
| [`docs/OPEN_SOURCE.md`](docs/OPEN_SOURCE.md) | 开源范围，以及和业务数据怎么分开 |
| [`docs/delivery/PORTABLE_WINDOWS_CI.md`](docs/delivery/PORTABLE_WINDOWS_CI.md) | Windows 便携包构建的细节 |
| [`SECURITY.md`](SECURITY.md) | 私下报告漏洞 |
| [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) | 社区行为准则 |
| [`CHANGELOG.md`](CHANGELOG.md) | 版本记录 |
| [`llms.txt`](llms.txt) | 给协助改代码的模型看的短摘要 |

## 参与

欢迎修 bug、补合成测试、校对货代模板和报关栏位、改进文档。请先读 [`CONTRIBUTING.md`](CONTRIBUTING.md) 和 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。

## 许可证

[MIT License](LICENSE)。版权所有 © 2026 huangyuehui1998-dev。

## 安全

发现密钥泄露、路径穿越，或服务被绑到局域网，请按 [`SECURITY.md`](SECURITY.md) 私下报告。请不要开公开 issue 贴利用步骤或真实表格。
