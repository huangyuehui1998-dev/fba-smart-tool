# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

产品代际写在 `backend/fba_tool/app_version.py` 的 `APP_VERSION`（当前 **V4**）。Git tag 使用 `v4.MINOR.PATCH`。发布步骤见 `docs/RELEASING.md`。

更早的交付说明在 `docs/delivery/`。那些文档记录的是当时的包，不从这份骨架倒推成已发布的 GitHub Release。

## [Unreleased]

### 新增

- 开源与协作文档：`README.md`、`CONTRIBUTING.md`、`CODE_OF_CONDUCT.md`、`SECURITY.md`、`LICENSE`、`llms.txt`、`docs/OPEN_SOURCE.md`、`docs/MAINTAINING.md`、`docs/RELEASING.md`。

### 移除

- 停止跟踪真实领星在售导出 `review/lingxing_listing_export_2026-10-21.xlsx`。
- 删除 `ALLOWED_LISTING_FIXTURES`。文件名带 `listing` 的 xlsx 再次一律视为禁止入库。
- 本机领星回归改为读取 `FBA_LINGXING_OWNER_XLSX`；未设置或文件不存在时跳过，不再依赖仓库内的那份导出。

### 变更

- 三方评审后订正文档：界面名字和 step id 分开写；DeepSeek Key 仅 Windows DPAPI；便携包 CI 不跑 pytest；冒烟脚本在仓库根目录执行。记录见 `docs/评审报告/开源前置_三方评审.md`。
- 开源文档测试 r1：三份 SKU 映射出厂文件改为 `{}`，与便携包一致。报关资料模板改为脱敏版。发货录入样表的 SKU / FNSKU 改为 `DEMO-SKU-*` / `X0DEMO*`。德速填写示例的货件号改为 `FBATEST0DEMO`。
- `.gitignore` 与 `FORBIDDEN_REAL_NAMES` / `FORBIDDEN_REAL_GLOBS` 对齐。`lingxing_listing_prices.xlsx` 和 `*listing*.xlsx` 会被 `git check-ignore` 拦住。

### 说明补充

- 源码默认和便携包仍有差别的地方（货代原件上的图片、说明文字里的历史样例文件名、不进安装包的样表）写在 `docs/OPEN_SOURCE.md`。

### 说明

- git 历史没有改写。旧提交里仍可能检出该工作簿。见 `docs/OPEN_SOURCE.md`。
- V4 尚未打 `v4*` 正式 tag。发布那天把 `Unreleased` 挪到具体版本标题下，并写上日期。见 `docs/RELEASING.md`。
