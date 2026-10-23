# 参与贡献

谢谢你愿意看这份代码。能用的规则、能复现的 bug、写清楚的文档，都是在帮后面的人少返一次工。我为人人，人人为我：改动请带着测试或说明回来，维护者也会认真看。

行为上的期待见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。漏洞不要开公开 issue，见 [SECURITY.md](SECURITY.md)。

## 欢迎的贡献

- 修一个能用合成数据复现的 bug，并补上测试
- 货代发票模板、箱号、数量、申报价、报关栏位的校正（请写明依据：公开规则、模板表头，或你构造的最小例子）
- 让错误提示更清楚，尤其是会拦住导出的那些中文说明
- 文档、打过码的截图、把过时步骤改成和当前 `V4` 一致
- 测试缺漏：某条边界只有手工点过、没有进 pytest / vitest

## 请不要这样做

- 提交密钥、`.env` 真值、`lingxing.json`、`app_data/`、数据库、真实领星导出、真实货件批次
- 为了“让测试变绿”把真实客户表放进仓库，或给某个真实文件名开白名单
- 在一个 PR 里重写整个发票或报关引擎
- 把只在你电脑上存在的路径写死进测试；本机文件用环境变量，没有就 skip
- 公开贴出别人的货件号、地址、售价或密钥，包括 issue 和 PR 描述

## 环境

- Python **3.12**（便携包 CI 用这一版）
- Node.js **22**
- 后端锁文件：`backend/requirements.lock.txt`、`backend/requirements-dev.lock.txt`
- 前端锁文件：`frontend/package-lock.json`（用 `npm ci`）

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.lock.txt -r requirements-dev.lock.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8002
```

```bash
cd frontend
npm ci
npm run dev
```

浏览器：<http://127.0.0.1:5173>。API 文档：<http://127.0.0.1:8002/docs>。

可选环境变量：

| 变量 | 作用 |
|---|---|
| `FBA_BACKEND_PORT` | 前端代理要连的后端端口，默认开发流程用 `8002` |
| `FBA_APP_DATA_DIR` | 换一套本机数据目录。测试和冒烟应指向临时目录 |
| `FBA_NO_BROWSER` | 设为 `1` 时启动器不打开浏览器 |
| `FBA_LINGXING_OWNER_XLSX` | 本机私有领星导出的路径。未设置或文件不存在时，对应用例 skip |
| `FBA_REALDATA_DIR` | 本机货件批次目录。没有就 skip，不要把目录提交进仓库 |

`frontend/.env.example` 里只有注释和占位。复制成 `.env` 后也请只写本机地址，`.env` 已被 git 忽略。

## 测试

后端（在 `backend/` 下）：

```bash
pytest
```

只跑你碰到的文件也可以，例如：

```bash
pytest tests/v4/test_v4_ops_r3.py tests/release/test_s9step5_release.py
```

发布扫描会拒绝文件名里带 `listing` 的 xlsx，以及 `lingxing_listing_prices.xlsx`。合成夹具放在 `backend/tests/fixtures/synthetic/`，不要用真实导出的文件名。

前端：

```bash
cd frontend
npm test
```

改了页面或路由时再跑 `npm run build`。`npm run e2e` 是 Playwright，需要本机浏览器和已经启动的服务，不是每个 PR 的必跑项；你跑了就在 PR 里写结果。

端到端冒烟（会真的拉起后端，数据目录用临时的）：

```bash
python scripts/smoke_e2e.py
```

在 Windows 上从 `backend` 虚拟环境调用时，路径按你的外壳写。冒烟不应读写你的真实 `app_data/`。

## 提交说明

用完整的句子写出这次做了什么。近期提交是英文祈使句，例如 `Compare qiluo rows by box segment and skip rebox CSVs.` 中文也可以，只要别人半年后还读得懂。一个提交一件事。

## PR 清单

- [ ] 说明里写了动机、改了什么、怎么验证
- [ ] 没有密钥、`.env` 真值、`lingxing.json`、`app_data/`、`realdata/`、真实领星导出
- [ ] 新行为有合成测试；依赖本机文件的用例在文件不存在时 skip
- [ ] 相关的 `pytest` 已跑过，结果写在 PR 里（跳过的也写上原因）
- [ ] 改了前端：`npm test` 已跑；改了构建或路由时 `npm run build` 已跑
- [ ] 用户能看见的变化写进了 `CHANGELOG.md` 的 `Unreleased`
- [ ] 截图打过码

审阅的人会按 [docs/MAINTAINING.md](docs/MAINTAINING.md) 看。小 PR 比大 PR 更容易被合并。

## 分支

从最新的 `main` 拉功能分支，用 PR 合并回去。不要 force-push `main`。若你的工作必须接在一条已经存在的长分支上，请在 PR 里写明基线提交。
