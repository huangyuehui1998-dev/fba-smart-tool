# V3.3 Windows 便携包（CI 产物）

产品版本 `V3.3`。安装包只在 **GitHub Actions 的 `windows-latest`** 上打，不要在一台随意的电脑上手工打包再拿来发布。

工作流：`.github/workflows/portable-windows.yml`（名称 **Portable Windows package**）。

它只上传 workflow artifact，**不会创建或发布 GitHub Release**。人工模拟测试通过之后，再由 Marco / bots 把 zip 挂到 Release 上。

## 包里有什么

文件名：`dist/FBA_Smart_Tool_V3.3_便携版.zip`

zip 内（正斜杠，中文名带 UTF-8 标志）：

- `FBA_Smart_Tool/FBA_Smart_Tool.exe`
- `FBA_Smart_Tool/启动FBA工具.bat`
- `FBA_Smart_Tool/使用说明.txt`
- `FBA_Smart_Tool/_internal/templates/`（含 `forwarders/qiluo.xlsx`）
- `FBA_Smart_Tool/_internal/config/`
- `FBA_Smart_Tool/_internal/dist/`（前端）

模板和出厂配置来自白名单 `packaging/release_manifest.py`。PyInstaller 在 Analysis 之后若没收齐，打包直接失败。`scripts/finish_portable_dist.py` 只检查 `_internal` 里这些文件在不在，**缺了不会手工拷进去**。

不要打进包里的东西：`realdata`、`app_data`、领星密钥（`lingxing.json`）、发票历史（`invoice_history.default.json`）、会话、数据库。出厂规则 `policy.default.json`、`category_map.default.json`、`item_size_policy.default.json`、`forwarder_registry.default.json`、`sta_dropdowns.default.json` 在白名单里，否则首次启动会找不到 `_internal/config/policy.json`。

中文文件名是在 **Windows 构建机上的 Python** 写进 zip 的。不要在 Linux 上解压再重新压缩，locale 不对时中文名会坏。

## 构建机

| 项 | 值 |
|---|---|
| 系统 | `windows-latest` |
| Python | **3.12**（不用 3.14；引导程序出过问题） |
| Node | 22 |
| PyInstaller | `6.20.0`（`packaging/requirements-pyinstaller.txt`，与 `backend/requirements-dev.lock.txt` 一致） |
| 入口 | `scripts/build_standalone.ps1` |

虚拟环境是 `backend\.venv`。依赖用 `backend/requirements.lock.txt`（本机测过的版本；Python 3.12 有对应 wheel），然后脚本再安装上面的 PyInstaller 钉死版本。不用浮动的 `requirements.txt`，免得装到和 PyInstaller 6.20 不匹配的新 scipy。

## 什么时候会跑

1. **Pull request**（包括 draft）。打开或更新 PR 就会打一版，产物挂在那次运行上。
2. **Actions → Run workflow**（`workflow_dispatch`）。这个按钮只在工作流文件已经在默认分支 `main` 上之后才会出现。出现之后：选要打的分支，再点 **Run workflow**。
3. **推送 tag**，名字匹配 `v3.3*`（例如 `v3.3`、`v3.3.0`）。

在工作流还没进 `main` 之前，用第 1 条：打开 PR 的 Checks，或 Actions 列表里那次 **Portable Windows package** 运行。不要为了按按钮先合并。

## 下载 artifact

1. 打开仓库 **Actions** → 点开成功的 **Portable Windows package** 运行。也可以从 PR 的 Checks 进同一次运行。
2. 跑完后页面底部 **Artifacts** 里下载 **`FBA_Smart_Tool_V3.3_便携版.zip`**。
3. GitHub 下载 artifact 时会再套一层 zip。解**这一层**：
   - 如果里面是一个同名的 `FBA_Smart_Tool_V3.3_便携版.zip`，**这个内层文件**才是便携包。
   - 如果打开后直接看到目录 `FBA_Smart_Tool` 和 `FBA_Smart_Tool.exe`，说明客户端已经解开了内层，不要再打包。回到 Artifacts 重新下载，上传时用内层那个 zip 文件本身。
4. 运行摘要（Summary）里有 **SHA256** 和字节数。下载后的内层 zip 应与摘要一致。
5. Artifact 保留 30 天。过期就再跑一次工作流，不要用旧包在别的机器上重打。

## 挂到 GitHub Release（人工，测试之后）

CI **不会**执行这一步。人工模拟测试通过后再做。

1. 用上面下载的内层 zip，核对 SHA256 与那次 Actions 摘要一致。
2. 打开仓库 **Releases** → **Draft a new release**。
3. 选择已有 tag，或新建 tag（`v3.3.0` 这类 `v3.3*`）。新建 tag 会再触发一次打包；测试用的是哪一次运行的 zip，Release 上就挂哪一个，不要换成在 Linux 上重打的包。
4. 把 `FBA_Smart_Tool_V3.3_便携版.zip` 拖进 **Attach binaries**。不要解压后再压缩。
5. 先存 **Draft**。模拟测试没问题再 **Publish**。
6. 不要把 `realdata`、`app_data`、领星密钥或发票历史另附到 Release 上。

## 在 Windows 上按 CI 同样的步骤重打（排查用）

仍要用 Python 3.12，并且不要改完 zip 再拿到 Linux 上重打包。

```powershell
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
Set-Location frontend
npm ci
Set-Location ..
powershell -ExecutionPolicy Bypass -File scripts\build_standalone.ps1
```

成功后看 `dist\FBA_Smart_Tool_V3.3_便携版.zip`，以及脚本打印的 SHA256。

## 打包失败时

- 日志里是「没有进入 PyInstaller datas」或「`_internal` 缺少白名单资源」：修 `packaging/FBA_Smart_Tool.spec` / `packaging/release_manifest.py`，重新跑工作流。不要在 `finish_portable_dist.py` 里把模板拷进 `_internal`。
- 需要的文件至少包括 `_internal/templates/forwarders/qiluo.xlsx`、`_internal/config/forwarders.default.json`、`_internal/dist/index.html`。
- Python 不是 3.12：工作流会在建虚拟环境之前失败。本机排查也用 3.12。
