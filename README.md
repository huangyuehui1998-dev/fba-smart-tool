# FBA Smart Tool

Local-first tool for Amazon FBA packing, shipment checks, forwarder invoices, and customs paperwork. It runs on your machine. This repository ships no API keys and no real customer shipments.

本地运行的亚马逊 FBA 装箱、货件核对、货代发票和报关工具。浏览器里操作，数据留在你自己的电脑上。

## 怎么拿到 Windows 便携版

日常使用打开 [GitHub Releases](https://github.com/huangyuehui1998-dev/fba-smart-tool/releases)，下载 Latest [v4.0.0](https://github.com/huangyuehui1998-dev/fba-smart-tool/releases/tag/v4.0.0) 的 **`FBA_Smart_Tool_V4_Portable.zip`**。

「Latest 仍是 v3.3.0、Release 上还没有 V4」这句已经过时。当前 Latest 就是 v4.0.0。更早的 [v3.3.0](https://github.com/huangyuehui1998-dev/fba-smart-tool/releases/tag/v3.3.0) 仍在列表里，附件是 `FBA_Smart_Tool_V3.3_Portable.zip`（产品代际 V3.3）。

Actions artifact 和构建输出里，内层 zip 仍可能显示中文名 `FBA_Smart_Tool_V4_便携版.zip`。Release 页面上的文件名是 `FBA_Smart_Tool_V4_Portable.zip`。来自同一个 tag 那次构建时，两份是同一批字节，用 SHA256 核对。

解压后双击包里的 `启动FBA工具.bat`。使用步骤见 [`docs/使用说明.md`](docs/使用说明.md)。维护者打 tag、核对 SHA256 再发布的顺序见 [`docs/RELEASING.md`](docs/RELEASING.md)。

六问不在本页展开，见 [`docs/OPEN_SOURCE.md`](docs/OPEN_SOURCE.md) 的「常见六问」。

## 这是什么

运营同学每天要过几关：把货装进合规的箱子，对上亚马逊货件，按货代模板开发票，再整理报关资料。这些规则散落在表格、经验和各家货代的版式里，错一格往往要返工。

FBA Smart Tool 把这条流水线收成一台本机程序：FastAPI 做业务，React 做界面。开发时前端走 Vite，打包后由同一个后端挂出页面。默认只监听 `127.0.0.1:8002`。

它不是亚马逊或领星的官方客户端，也不代替你向平台或海关申报。算出来的箱规、申报价和报关栏位仍然要人核对。

## 为什么开源

我做这个工具，是因为这些步骤自己每天都要过。规则写在一个人的电脑里，对的地方别人用不上，错的地方也只有一个人能撞见。

把它开源，是把方法交出来：装箱和发票的边界可以一起看，货代模板和报关栏位可以一起补。我为人人，人人为我。你拿走用得上的部分；你若踩中一个箱号、一个申报价或一张货代表的坑，也请把修法送回来。

仓库里是程序和合成例子。你的货件、地址、售价和密钥留在你的机器上。

## 能做什么

界面上有七项。名字里的数字和代码里的 step id 不是同一套，改界面时对名字，改代码时对 id（`frontend/src/lib/workflow-steps.ts`）。

| 界面 | step id | 做什么 |
|---|---|---|
| 1 录入 | 1 | 文本、表格，或可选的 DeepSeek 解析 |
| 2 排箱 | 2 | 整箱、混装和 FBA 合规校验 |
| 3 导出 | 3 | 内部留档和 Send to Amazon 模板 |
| 7 刷仓 | 3.5 | 可选。分仓结果给货代预览 |
| 4 货件校验 | 4 | 亚马逊 CSV / 箱唛 PDF，对照工厂表、货代表 |
| 5 发票 | 4.5 | 货代模板填充，Univer 离线预览后再导出 |
| 6 报关 | 5 | 报关单、发票、箱单、合同等预览和导出 |

产品库可以手填、用 Excel 进出，也可以导入领星在售表：先预览，确认后才写入，写错可以回滚。领星 MCP 定时同步默认关闭，并且只做读取。

发票目前按这些货代模板走：SEND、九方、琪珞国际、琪珞 T5、琪珞 T6、德速。

## 功能边界

- 单机工具。业务数据在本机 `app_data/`（SQLite、你改过的配置、导出历史）。
- 领星 MCP Key 写在本机 `app_data/config/lingxing.json`（DPAPI 密文）。DeepSeek Key 只在 Windows 上写入 `app_data/secrets/deepseek_key.bin`（同样是 DPAPI）；其它系统保存会得到 422。仓库不提供这两把钥匙。
- 便携版面向 Windows。源码也可以在其他系统上跑开发和测试；正式 zip 只在 GitHub Actions 的 Windows 构建机上打。日常拿哪一只包，见上文「怎么拿到 Windows 便携版」。
- 产品入口 `run_app.py` 监听 `127.0.0.1`，首选端口 **8002**（占用时按 `PREFERRED_PORTS` 顺延，跳过 8010）。开发时请显式启动在 8002。直接执行 `python backend/main.py` 时端口来自 `FBA_PORT`，没设则是 8000，那不是日常入口。监听地址默认 `FBA_HOST=127.0.0.1`；改成非本机地址时必须同时设置 `FBA_ACCESS_TOKEN`，否则拒绝启动。
- 出厂规则在 `backend/config/*.default.json`。你的改动写到 `app_data/config/`，不要改出厂文件来“保存设置”。
- 产品代际是 `V4`，写在 `backend/fba_tool/app_version.py` 的 `APP_VERSION`。FastAPI 自带的 `version` 字符串是 API 文档号，和产品版本无关。

更细的使用步骤见 `docs/使用说明.md`（文中个别版号可能还停在更早的交付说明上，以 `APP_VERSION` 为准）。代码地图见 `docs/架构说明.md`。

## 不含密钥，不含真实客户数据

这个仓库**不包含**：

- 领星 MCP Key、DeepSeek Key，或任何 token / password
- `lingxing.json`、`app_data/`、数据库、会话
- 真实领星在售导出（文件名带 `listing` 的 xlsx 会被发布扫描拒绝）
- 真实货件批次（`realdata/`）

从源码第一次启动，和从 Windows 便携包第一次启动，用的出厂文件不完全相同。三份 SKU / FNSKU / ASIN 映射（`amazon_sku_metadata.default.json`、`fnsku_mapping.default.json`、`sku_mapping.default.json`）两边都是 `{}`。报关资料模板两边都是脱敏版（`DEMO-ORDER`、`FBA-DEMO`）。货代说明文字、产品图，以及不进安装包的样表，仍以 [`docs/OPEN_SOURCE.md`](docs/OPEN_SOURCE.md) 的对照表为准。

2026-10-20 留下的三份样表还在 `backend/templates/`（发货录入样表、工厂表、货代表），不进便携包。发货录入样表的 SKU / FNSKU 已是 `DEMO-SKU-*` / `X0DEMO*`。它们不是领星在售导出。

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

浏览器打开 <http://127.0.0.1:5173>。开发代理把 `/api` 转到后端。端口先看仓库根目录 `.dev/ports.json` 的 `backend`，没有再看 `FBA_BACKEND_PORT`，再否则 8002。

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

`FBA_LINGXING_OWNER_XLSX` 没设或文件不在，对应用例会 skip。货件批次路径不存在时，相关用例 skip，原因里带「需要 box realdata」。GitHub Actions 的 `ci` 在 Linux 上跑 pytest 和前端 `npm run build`。便携包工作流另打 Windows zip；纯文档 PR 不跑那只构建。细节见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

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
| [`docs/评审报告/开源前置_三方评审.md`](docs/评审报告/开源前置_三方评审.md) | 代码、测试、运营对这套开源文档的评审 |

## 参与

欢迎修 bug、补合成测试、校对货代模板和报关栏位、改进文档。请先读 [`CONTRIBUTING.md`](CONTRIBUTING.md) 和 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。

## 许可证

[MIT License](LICENSE)。版权所有 © 2026 huangyuehui1998-dev。

## 安全

发现密钥泄露、路径穿越，或服务被绑到局域网，请按 [`SECURITY.md`](SECURITY.md) 私下报告。请不要开公开 issue 贴利用步骤或真实表格。
