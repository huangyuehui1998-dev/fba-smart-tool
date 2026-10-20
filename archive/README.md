# archive/ — 归档区（D-2026-10-16-11）

用户决定：重复/过时文件**归档，不删除**。这里的文件不再被任何代码、打包配置、测试或文档引用；需要时可用 `git log --follow` 查原位置。

| 归档后路径 | 原路径 | 清单条目 | 归档 tag |
|---|---|---|---|
| `archive/frontend_export_test/test_amazon.xlsx` | `frontend/_export_test/test_amazon.xlsx` | 第 5 条（调试残留） | s7-archive |
| `archive/frontend_export_test/test_internal.xlsx` | `frontend/_export_test/test_internal.xlsx` | 第 5 条（调试残留） | s7-archive |
| `archive/private_data/产品信息表.csv` | `backend/templates/产品信息表.csv` | D-2026-10-17-19（真实产品数据，不随安装包发布；改用 `backend/templates/产品信息表_示例.csv`） | s9-step4-fix3 |

其余条目为什么没有移动，见 `docs/S7_重复文件清单_待用户确认.md` 的“S7-archive 处理结果”。
