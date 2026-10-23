# 发布

发布物是 Windows 便携包 `FBA_Smart_Tool_V4_便携版.zip`。构建只在 GitHub Actions 的 `windows-latest` 上做。工作流名称是 **Portable Windows package**（`.github/workflows/portable-windows.yml`）。

工作流只上传 Actions artifact，**不会**创建 GitHub Release。人工核对 SHA256、并在 Windows 上打开过之后，再把 zip 挂到 Release 上。

构建机、包内目录、首次启动所依赖的出厂配置，写在 [PORTABLE_WINDOWS_CI.md](delivery/PORTABLE_WINDOWS_CI.md)。本文只规定发布顺序。两边不一致时，以工作流文件和那份构建说明为准，并回来改本文。

## 版本和 tag

1. 确认 `backend/fba_tool/app_version.py` 的 `APP_VERSION` 仍是这次代际（当前 `V4`）。
2. 把 `CHANGELOG.md` 里 `Unreleased` 的条目挪到新标题下，例如 `## [4.0.0] - 2026-10-23`。日期用发布当天。
3. 在准备发布的那个提交上打带注释的 tag。tag 必须匹配 `v4*`，例如 `v4.0.0`。

在干净的 `main` 上（或你明确要发布的提交上）：

```bash
git checkout main
git pull origin main
git tag -a v4.0.0 -m "FBA Smart Tool v4.0.0"
git push origin v4.0.0
```

不要 force-push tag，也不要移动已经公开的 tag。tag 打早了或 zip 有问题，发下一个 patch（`v4.0.1`），并在说明里写明上一只包不要用。

推送 tag 会再跑一次便携包构建。PR 上已经绿过的那次运行，可以作为测试依据；**挂到 Release 上的 zip，必须来自你最终核对 SHA256 的那一次运行。**

## 取构建产物

1. 打开仓库 Actions，进入成功的 **Portable Windows package**。
2. 在 Artifacts 下载 `FBA_Smart_Tool_V4_便携版.zip`。GitHub 有时会再套一层 zip。
3. 解开外层之后：
   - 若里面是同名的 `FBA_Smart_Tool_V4_便携版.zip`，这一只内层文件才是便携包。
   - 若直接看到目录 `FBA_Smart_Tool` 和 `FBA_Smart_Tool.exe`，说明客户端已经解开了内层。回到 Artifacts 重新下载，上传时用内层那个 zip 本身。
4. 运行摘要（Summary）里有 SHA256 和字节数。用这一次运行的摘要，不要用上一只包的哈希。

不要使用缺少 `policy.default.json` 的旧包。那次失败的原因和后来核对过的构建，写在 [PORTABLE_WINDOWS_CI.md](delivery/PORTABLE_WINDOWS_CI.md)。

## 校验 SHA256

Windows（PowerShell）：

```powershell
Get-FileHash .\FBA_Smart_Tool_V4_便携版.zip -Algorithm SHA256
```

macOS / Linux：

```bash
sha256sum FBA_Smart_Tool_V4_便携版.zip
```

比对的是 **内层** zip 和 **同一次** Actions 摘要。大小写不敏感，空格和文件名不要算进哈希。

对不上就不要上传。在 Linux 上解压再压缩会破坏中文文件名，这种包也不能当发布物。

本机为了排查，可以按构建说明里的 Python 3.12 步骤重打。重打的 zip 只用于查问题，正式发布仍用 Actions 上那一只，并重新核对它的 SHA256。

## GitHub Release

1. 打开仓库的 Releases → Draft a new release。
2. 选刚刚推送的 tag（`v4.0.0` 这类）。不要在这里又新建一个不同的 tag，除非你有意再触发一次构建，并且随后只用新运行的 zip。
3. 标题与 tag 一致。正文贴上 `CHANGELOG.md` 里该版本的条目，并写上：

   ```text
   FBA_Smart_Tool_V4_便携版.zip
   SHA256: <与 Actions 摘要一致的哈希>
   字节数: <与摘要一致>
   Actions run: <那次运行的链接>
   ```

4. 把内层 zip 拖进 Attach binaries。不要附 `realdata`、`app_data`、`lingxing.json` 或发票历史。
5. 先存 Draft。
6. 在一台 Windows 上解压，双击 `启动FBA工具.bat` 或 `FBA_Smart_Tool.exe`，确认页面能打开、`_internal/config/policy.default.json` 一类出厂文件在包里。
7. 模拟通过后再 Publish。

## 发布前的仓库扫描

在仓库根目录跑。`forbidden_real_hits` 拒绝 `lingxing_listing_prices.xlsx`，以及文件名里带 `listing` 的 xlsx。有命中就先拿掉文件，不要带进这次 tag。

```bash
python - <<'PY'
import importlib.util
from pathlib import Path

path = Path("packaging/release_manifest.py")
spec = importlib.util.spec_from_file_location("release_manifest", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
hits = mod.forbidden_real_hits(Path("."))
if hits:
    print("\n".join(hits))
    raise SystemExit(1)
print("forbidden_real_hits: none")
PY
```

便携包白名单、脱敏模板和空映射由这组 pytest 守着。在 `backend/` 下：

```bash
pytest tests/release/test_s9step5_release.py tests/release/test_portable_package.py
```

## 发布检查清单

- [ ] `CHANGELOG.md` 已从 `Unreleased` 挪到版本号，日期正确
- [ ] `APP_VERSION` 与 tag 的代际一致（现在是 V4 / `v4*`）
- [ ] 该提交上 `pytest` 的相关结果已知；这次发布碰过的前端也跑过测试或构建
- [ ] 上面的 `forbidden_real_hits` 打印 `none`
- [ ] `pytest tests/release/test_s9step5_release.py tests/release/test_portable_package.py` 通过
- [ ] 仓库里没有准备发布的 `lingxing.json`、`app_data/`、`realdata/`
- [ ] tag 已推送，Portable Windows package 成功
- [ ] 内层 zip 的 SHA256、字节数与该次 Actions 摘要一致
- [ ] Release 正文写了哈希和运行链接
- [ ] Release 附件只有这只 zip
- [ ] Windows 上实际打开过
- [ ] 仍然是 Draft，直到上面各项都勾完再 Publish

## 发布之后

在 PR 或 Release 讨论里留一句：哪一个 tag、哪一次 Actions run、SHA256 前 12 位。发现包不能启动时，在 Release 正文顶部写明「不要使用这一只」，然后走下一只 patch，而不是悄悄换掉同一个 tag 上的文件。
