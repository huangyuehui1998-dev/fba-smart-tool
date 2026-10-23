# 开源说明

仓库准备公开时，公开的是做法，不是某一家的货。我为人人，人人为我：方法可以拷走，客户数据留在各自的电脑上。

## 业务数据和程序怎么分开

程序设计成单机使用。

- 产品库、你改过的配置、导出历史放在 `app_data/`。这个目录被 git 忽略。
- 领星 MCP Key 写在本机 `app_data/config/lingxing.json`，以 DPAPI 密文（`mcp_key_enc`，前缀 `dpapi:v1:`）保存。仓库里没有这份文件。换一台电脑要重新填写。
- DeepSeek Key 只在 Windows 上写入 `app_data/secrets/deepseek_key.bin`（DPAPI）。非 Windows 调用保存接口会得到 422。这个文件在 `app_data/` 里，不进提交。
- 服务默认绑定 `127.0.0.1`。它不是给公网部署的多用户系统。
- 真实货件批次放在本机目录，用 `FBA_REALDATA_DIR` 指给测试。路径不存在就 skip，原因里带「需要 box realdata」。变量没设时，部分用例会去看默认路径 `/workspace/fba_tool/realdata`，那里没有同样 skip。
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

`.gitignore` 写了同样的两条，并且放在 `!backend/templates/**/*.xlsx` 之后。`git check-ignore` 会拦住仓库根、`review/` 和 `backend/templates/` 里的这些 xlsx。合成夹具文件名不含 `listing`，不会被这两条拦住。

这次从树上删除了 `review/lingxing_listing_export_2026-10-21.xlsx`，并删除了只放行这一份文件的 `ALLOWED_LISTING_FIXTURES`。合成测试继续用内存里的工作簿，或 `backend/tests/fixtures/synthetic/` 里的脱敏表。

同样不要提交：

- `.env` 里的真实地址或钥匙（`frontend/.env.example` 只有占位和注释）
- `lingxing.json`、`*.key`、会话目录 `backend/config/sessions/`
- `app_data/`、`*.db`、`fba_tool/realdata/`
- `backend/tests/golden/*.json`（已忽略）

## 源码默认和便携包

从源码跑和从 Windows 便携包跑，读的不是同一套出厂文件。便携包只收 `packaging/release_manifest.py` 白名单里的条目。标成 `release` 的，取 `packaging/release_templates/` 里的版本，不取 `backend/` 里的原件。生成脚本是 `packaging/build_release_templates.py`。

| 文件 | 源码 `backend/` | 便携包 |
|---|---|---|
| `amazon_sku_metadata.default.json`、`fnsku_mapping.default.json`、`sku_mapping.default.json` | `{}` | `{}`。两边一样。新用户不会被种进 SKU / FNSKU / ASIN |
| `customs/报关资料模板.xlsx` | 与便携包那份单元格相同：订单号 `DEMO-ORDER`，货件号 `FBA-DEMO`，品牌 `DEMO` | 同一份脱敏工作簿 |
| `forwarders/deshu_t3.xlsx`、`forwarders/qiluo_t6.xlsx` | 测试用原件。德速「填写示例」货件号是 `FBATEST0DEMO` | 去掉发票主表上的产品图，并清掉公司名 / 信用代码那一格。德速示例货件号同样是 `FBATEST0DEMO` |
| `forwarders.default.json`、`invoice_template_map.json` | `source` / `decision` 说明里仍有历史样例文件名 | 只改这些说明文字里的货件号，换成 `<已脱敏>`。其余字段照旧 |
| `发货录入样表.xlsx`、`工厂表.xlsx`、`货代表.xlsx` | 留在仓库，不进白名单 | 包里没有这三份 |

以前有一句「抽查没有看到 FBA 货件号」。那句话不成立。`backend/templates/customs/报关资料模板.xlsx` 里曾经有订单号 `JUS7HB115` 和货件号 `FBA19GV*`。源码里的那份现在已经换成上面的脱敏版，和便携包对齐。

`发货录入样表.xlsx` 里曾经有 `J-PETWOODSTAIRS-*` 和 `X0054*`。SKU / FNSKU 现已改成 `DEMO-SKU-*` / `X0DEMO*`，和 `backend/fba_tool/input_template.py` 的 `EXAMPLE_ROWS` 相同。下载接口按 `EXAMPLE_ROWS` 现场生成，不读这张表里的旧格子。`工厂表.xlsx` 和 `货代表.xlsx` 这次按 FBA 货件号、`X00` FNSKU、`B0` ASIN 扫过，没有这些形态；它们仍不进便携包。

`invoice_history.default.json` 不进便携包。品牌已写成 `DEMO`。从源码第一次启动时，它会补进本机 `app_data/invoice_history.json`。

## 仍留在仓库里、需要知道的文件

2026-10-20 的决定留下上面三份样表。文件名还在，发货录入样表的货号已经换成示例。不要在别的 PR 里顺手删掉测试和白名单还点名的文件名。

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
