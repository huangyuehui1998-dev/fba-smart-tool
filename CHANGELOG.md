# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

产品代际写在 `backend/fba_tool/app_version.py` 的 `APP_VERSION`（当前 **V4**）。Git tag 使用 `v4.MINOR.PATCH`。发布步骤见 `docs/RELEASING.md`。

更早的交付说明在 `docs/delivery/`。那些文档记录的是当时的包，不从这份骨架倒推成已发布的 GitHub Release。

## [Unreleased]

### 变更

- GitHub Release 附件是 `FBA_Smart_Tool_V4_Portable.zip`（与 `FBA_Smart_Tool_V4_便携版.zip` 同一份字节）。README、`llms.txt`、`docs/RELEASING.md` 已按这两个名字对齐。
- Linux CI（`.github/workflows/ci.yml`）在 PR 和 `main` 上跑后端 pytest 与前端 `npm run build`。便携包工作流对纯文档 PR（`docs/**`、`*.md`、`review/**`）不再构建；`v4*` tag 与手动 Run workflow 仍会构建。
- GitHub Actions 改为钉死 commit SHA。下一只便携包（`v4.0.1` 起）会带 `FBA_Smart_Tool/BUILDINFO.txt`；已发布的 v4.0.0 不重打。

## [4.0.0] - 2026-10-26

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
- 开源文档测试 r2：`packaging/Step5报关资料_架构与工作流.txt` 的订单号、品牌、货件号示例改为 `DEMO-ORDER` / `DEMO` / `FBA-DEMO`。便携包历史核对段标明 `FBA_Smart_Tool_V3.3_便携版.zip` 是历史包名、非当前 V4。

### 说明补充

- 源码默认和便携包仍有差别的地方（货代原件上的图片、说明文字里的历史样例文件名、不进安装包的样表）写在 `docs/OPEN_SOURCE.md`。
- README「怎么拿到 Windows 便携版」：尚无 v4.0.0 Latest 时先读警告，不要用 Latest（仍是 v3.3.0，附件 `FBA_Smart_Tool_V3.3_Portable.zip`）；日常用户暂时没有 GitHub Release 上的 V4 包，维护者用 Actions Portable Windows package 的内层 `FBA_Smart_Tool_V4_便携版.zip`。v4.0.0 成为 Latest 之后，日常用户再到 Releases 下载该 zip。`docs/RELEASING.md` 写明运营机器人不点 Publish，只有维护者发布。

### 说明

- git 历史没有改写。旧提交里仍可能检出该工作簿。见 `docs/OPEN_SOURCE.md`。
