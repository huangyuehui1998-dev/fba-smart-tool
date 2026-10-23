# 开源说明

仓库准备公开时，公开的是做法，不是某一家的货。我为人人，人人为我：方法可以拷走，客户数据留在各自的电脑上。

## 业务数据和程序怎么分开

程序设计成单机使用。

- 产品库、你改过的配置、导出历史放在 `app_data/`。这个目录被 git 忽略。
- 领星 MCP Key 写在本机 `app_data/config/lingxing.json`，以 DPAPI 密文（`mcp_key_enc`，前缀 `dpapi:v1:`）保存。仓库里没有这份文件。换一台电脑要重新填写。
- DeepSeek 之类的可选钥匙在使用者自己的本机设置里，不进提交。
- 服务默认绑定 `127.0.0.1`。它不是给公网部署的多用户系统。
- 真实货件批次放在本机目录，用 `FBA_REALDATA_DIR` 指给测试。目录不存在就 skip。
- 本机若要对照一份私有领星导出，设置 `FBA_LINGXING_OWNER_XLSX` 为那个文件的路径。未设置或文件不存在就 skip。不要把路径改回仓库里的某个 xlsx。

CI 不需要任何客户表就能跑合成测试。便携包白名单在 `packaging/release_manifest.py`，不收集 `lingxing.json`、`app_data`、`realdata`、发票历史。

## 开源范围

公开的是：

- 后端 `backend/`（FastAPI 与 `fba_tool`）、前端 `frontend/`、启动和打包脚本
- 出厂默认配置 `backend/config/*.default.json`
- 打进便携包的空白模板（以 `release_manifest.py` 的白名单为准）
- 合成测试夹具，例如 `backend/tests/fixtures/synthetic/lingxing_us_columns_82.xlsx`
- 文档，包括历史评审笔记

领星相关代码（预览、确认、回滚、只读定时同步）是功能，可以公开。钥匙和在售导出不在其中。

## 明确不放进仓库的东西

`packaging/release_manifest.py` 的 `forbidden_real_hits` 会把下面的文件当成失败：

- 文件名是 `lingxing_listing_prices.xlsx`
- 文件名里带 `listing` 且以 `.xlsx` 结尾

这次从树上删除了 `review/lingxing_listing_export_2026-10-21.xlsx`，并删除了只放行这一份文件的 `ALLOWED_LISTING_FIXTURES`。合成测试继续用内存里的工作簿，或 `backend/tests/fixtures/synthetic/` 里的脱敏表。

同样不要提交：

- `.env` 里的真实地址或钥匙（`frontend/.env.example` 只有占位和注释）
- `lingxing.json`、`*.key`、会话目录 `backend/config/sessions/`
- `app_data/`、`*.db`、`fba_tool/realdata/`
- `backend/tests/golden/*.json`（已忽略）

## 仍留在仓库里、需要知道的文件

2026-10-20 的决定留下三份样表，它们在 `backend/templates/`，**不在**便携包白名单里：

- `发货录入样表.xlsx`
- `工厂表.xlsx`
- `货代表.xlsx`

这次开源清理没有删除它们。它们体积不大，抽查没有看到 FBA 货件号。若公开前还想再过一遍单元格，应单独做决定，而不是在别的 PR 里顺手改掉测试所依赖的文件名。

`docs/评审报告/` 是内部评审记录，不是客户导出。阅读时不要把里面的例子当成可以对外粘贴的业务数据。

`backend/tests/fixtures/lingxing/*.json` 是脱敏后的字段样例（SKU、品名已换成示例）。文件头注明：更早的 git 历史里可能仍有原始值，本次没有改写历史。

## git 历史

删除文件的这个提交只影响当前树。旧提交里仍然能找到曾经跟踪过的领星导出（例如恢复该文件的提交，以及更早纳入它的提交）。本次**不** force-push，也**不**改写历史。

在把仓库可见性改成公开之前，维护者需要单独决定：是否接受历史里仍能检出该工作簿，或者另做一次经过同意的历史清理。可见性不在本次改动里切换。

## 社区期望

- 用合成数据讨论问题。货件号、地址、售价、密钥留在本地。
- PR 小一些，写清怎么验证。见 [CONTRIBUTING.md](../CONTRIBUTING.md)。
- 维护者按 [MAINTAINING.md](MAINTAINING.md) 的响应期望回复，那是努力目标，不是合同。
- 行为上互相尊重，见 [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)。
- 你修好的一条规则，就是下一个人不用再撞的坑。欢迎把它送回来。
