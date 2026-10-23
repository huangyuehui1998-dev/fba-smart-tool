# 安全政策

请私下报告漏洞。公开 issue 会让还没升级的使用者暴露在细节里，也可能把密钥或客户表留在讨论区。

## 支持范围

当前产品代际是 `V4`（`backend/fba_tool/app_version.py` 的 `APP_VERSION`）。正在整理的这条线和随后打上 `v4*` tag 的发布，会处理被接受的安全修复。

更早的便携包只在你仍在使用、且问题会泄露密钥或越过本机数据目录时尽量修。请在报告里写上版本或 git 提交。

## 怎样报告

优先使用 GitHub 的私人漏洞报告（Security Advisory）：

<https://github.com/huangyuehui1998-dev/fba-smart-tool/security/advisories/new>

若仓库还不能提交 Advisory，请通过 GitHub 联系所有者 `huangyuehui1998-dev`，说明你有安全报告。不要在公开 issue、PR 或讨论区粘贴利用步骤。

报告里请写：

- 影响的版本或提交
- 复现步骤，使用合成数据
- 你认为的影响（谁的密钥或文件会被读到）
- 是否已经有演示。演示不要附带真实领星导出、货件批次或钥匙

## 我们关心的问题

- 密钥被写进仓库、日志、前端包或便携版 zip
- 路径穿越读到 `app_data` 约定之外的文件
- 本机服务被绑到非回环地址，局域网可以访问
- 依赖中的已知高危问题，且本项目的用法确实受影响

需要先拿到这台电脑的操作系统用户权限才能进行的攻击，以及领星、亚马逊、海关官方系统自身的问题，不作为本仓库的漏洞处理。你仍然可以私下告知，我们会说明判断。

## 响应期望

这是个人维护的项目，下面是努力目标，不是商业 SLA。

- 3 个工作日内确认收到
- 7 个工作日内给出初步判断：接受、需要更多信息，或不构成这个项目的漏洞
- 接受之后，修复优先于新功能
- 修复进入仓库后，再和报告人商量公开说明的时间
- 感谢愿意私下告知的人。若你希望在说明里具名，我们会照你的意愿写；你没有说，就保持匿名

维护者侧的处理步骤见 [docs/MAINTAINING.md](docs/MAINTAINING.md)。

## 给使用者

- 领星钥匙只填在本机。不要把 `app_data/config/lingxing.json` 发给别人。
- DeepSeek Key 只在 Windows 上落到 `app_data/secrets/deepseek_key.bin`。不要把这个文件提交或转发。其它系统上程序不会保存它。
- 不要把真实 `.env`、数据库或货件目录提交到 fork 的公开分支。
- 便携包从 GitHub Release 下载后，用 Release 正文里的 SHA256 核对文件。步骤见 [docs/RELEASING.md](docs/RELEASING.md)。
