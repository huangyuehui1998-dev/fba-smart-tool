# 维护者手册

这份手册写给愿意长期看这个仓库的人，也写给现在的维护者自己。项目可以只有一个人值班，但审 PR、打版本、处理漏洞的方式要让后来的人接得住。

社区相处见 [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)。私下报告漏洞的步骤见 [SECURITY.md](../SECURITY.md)。发布步骤见 [RELEASING.md](RELEASING.md)。

## 维护者职责

- 看 PR 和 issue，给出能执行的回复：接受、请改哪里，或说明为什么这次不做
- 守住边界：密钥、真实领星导出、`app_data/`、`realdata/` 不进仓库，也不进便携包
- 合进去的行为要有合成测试，或写明为什么现有测试已经覆盖
- 用户能看见的变化记在 `CHANGELOG.md` 的 `Unreleased`
- 产品代际 `APP_VERSION`、Git tag、便携包文件名三者一致
- 安全报告走私下渠道，修完再公开
- 发布只挂 CI 打出来的 Windows zip，并核对 SHA256

当前版权和仓库所有者是 GitHub 用户 `huangyuehui1998-dev`。增加维护者时，把人写进这里，并给 GitHub 上相应的合并与安全通告权限。

## 怎么审 PR

按这个顺序看，比通读每一行更快，也不容易放进不该进仓库的文件。

1. **读说明。** 动机、范围、验证命令是否都在。对不上 diff 的，先问。
2. **扫文件清单。** 出现 `.env`（示例文件除外）、`lingxing.json`、`*.db`、`app_data/`、`realdata/`、文件名带 `listing` 的 xlsx、密钥样值，直接请作者拿掉。不要用白名单把真实导出留在仓库里。
3. **看行为。** 发票数量、箱号、申报价、仓库地址、报关栏位，要有合成夹具。测试失败时 skip 只适用于「本机私有文件没提供」，不适用于逻辑错误。改工作流入口时，界面名字（「5 发票」）和 step id（4.5）要一起核对，两套数字不是一回事。
4. **跑相关测试。** 至少跑作者点名的 pytest。动到发布清单时跑 `backend/tests/release/test_s9step5_release.py`。动到前端时看 vitest。
5. **看便携包工作流。** 审 PR 先看 Linux 上的 `ci`（pytest 和前端 build）。发布包看 Portable Windows package：它只证明这台构建机能打出 zip。它不会创建 GitHub Release，也不代替人工打开 exe。
6. **决定。** 能合就合。要改就指出哪一段行为和期望不符。不要在别人的 PR 里夹带无关重构。

提交说明保持可读。一串 WIP 可以请作者整理成几条完整句子后再合。合进 `main` 之后不要为了改字而 force-push。

## 分支策略

- `main` 是别人克隆后默认看到的线，也是最终发布的线。
- 功能用单独分支，经 PR 进入 `main`。
- 不要 force-push `main`。功能分支在已经有人审过之后，也不要改写已推送的提交，除非作者和审阅者都同意，并在 PR 里说明。
- `main` 已开启分支保护：必须通过的检查是 Backend pytest 和 Frontend build；禁止 force-push；合并后删除来源分支（`delete_branch_on_merge`）。`backend/requirements.lock.txt` 和 `backend/requirements-dev.lock.txt` 按 Python 3.12 生成，与 CI、便携包一致。分支保护是先前的仓库设置，这次只记在这里，不改设置。
- 长生命周期的整理分支可以存在。PR 说明里写清基线，避免把无关的本地脚本一起提交。
- 带注释的 Git tag（`v4*`）表示「这一个提交要出包」。打 tag 的步骤在 [RELEASING.md](RELEASING.md)。不要在未准备发布时推 tag。

## CI、Action 钉版与 BUILDINFO

- 审 PR 的常规检查看 **CI**（`.github/workflows/ci.yml`）：后端 pytest 和前端 build。发布用的 Windows zip 看 **Portable Windows package**（`.github/workflows/portable-windows.yml`）。后者只上传 artifact，不创建 GitHub Release。
- 这两个工作流里的 Action 都钉在 40 位 commit SHA 上，同一行注释写着对应的版本标签（例如 `# v4.4.0`）。不要改回浮动的 `@v4` / `@v5`。`.github/dependabot.yml` 只跟踪 `github-actions`，每周开更新 PR，不自动合并。npm 和 pip 不在这份配置里。
- 从下一只发布起（`v4.0.1` 及以后的便携包），zip 里有 `FBA_Smart_Tool/BUILDINFO.txt`。已经挂在 Release 上的 v4.0.0（SHA256 `616e939e…`）没有这个文件；不要重打，也不要移动那个 tag。写法见 [PORTABLE_WINDOWS_CI.md](delivery/PORTABLE_WINDOWS_CI.md)。
- `ci.yml` 里有两条在 `main` 上已经失败的测试，用 `--deselect` 留着，并标了 TODO。修测试之前不要拿掉这两行。
- 密钥扫描（secret scanning，以及可选的 push protection）可以在仓库 Settings → Code security 里打开。这里只说明可以开；这次改动没有在网页上改仓库设置，开没开以 GitHub 上的设置为准。

## 版本号

两套号码不要混用。

| 名字 | 放在哪 | 含义 |
|---|---|---|
| `APP_VERSION` | `backend/fba_tool/app_version.py` | 产品代际，当前是 `V4`。界面和便携包文件名跟它走 |
| Git tag | `v4.MINOR.PATCH`，例如 `v4.0.0` | 一次发布。`v4*` 会触发便携包工作流 |
| FastAPI `version` | `backend/main.py` | OpenAPI 文档号，不是产品版本 |

规则：

- tag 用语义化版本，并且以 `v4` 开头，这样现有工作流才认。
- `MINOR` 增加是向后兼容的功能，`PATCH` 是修复。
- 产品代际从 V4 升到下一版时，同时改 `APP_VERSION`、便携包文件名、工作流里的 tag 过滤器，并在 `CHANGELOG.md` 写明。
- 已经推送并公开使用的 tag 不再移动。打错了就发下一个 patch，在 Release 说明里写清楚。

`CHANGELOG.md` 遵循 Keep a Changelog：平时记在 `Unreleased`，发布那天把条目挪到版本标题下，并写上日期。

## 安全漏洞

私下报告，步骤以 [SECURITY.md](../SECURITY.md) 为准。维护者在这边要做到：

- 公开 issue、PR 评论里如果出现密钥或真实客户表，先把内容撤下或编辑掉，再请报告人改走私下渠道
- 确认报告之后，用最小的修复堵住泄漏或越权；补一个合成测试，证明仓库扫描或权限检查会失败在修复前的那种输入上
- 修复进入仓库之前，不要在公开讨论里贴利用细节
- 若问题已经随着某个 commit 进了 git 历史，评估要不要另做一次历史清理。清理需要相关的人同意，并且不能靠 force-push `main` 来偷偷完成

## 响应期望

这是个人维护的业务工具，没有值班表，也没有商业 SLA。下面是努力目标，写出来是为了让报告的人知道会有人看。

| 类型 | 目标 |
|---|---|
| 安全报告 | 3 个工作日内确认收到；7 个工作日内给出初步判断（接受、需要更多信息，或不构成这个项目的漏洞） |
| 能造成密钥或客户数据泄露的修复 | 优先于新功能。有缓解办法时，先在讨论里告诉报告人 |
| 普通 issue / PR | 两周内第一次回复。逾期可以在话题下礼貌地提醒一次 |
| 发布后的打包事故 | 先在 Release 或 PR 里标明哪一个 zip 不能用，再打修复版 |

做不到时，说一声「这周看不了」，比沉默好。沉默不代表拒绝。
