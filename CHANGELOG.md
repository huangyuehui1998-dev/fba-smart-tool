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

### 说明

- git 历史没有改写。旧提交里仍可能检出该工作簿。见 `docs/OPEN_SOURCE.md`。

## [4.x] - 未发布

V4 的功能仍在整理，尚未打 `v4*` 正式 tag。打 tag 之前，把上面 `Unreleased` 的条目移到具体版本标题下，并写上发布日期。
