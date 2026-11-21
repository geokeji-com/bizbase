# 管理看板

显示名称 **管理看板**；Python 包、App 安装标识、标准模块和工作区内部名称统一为 `management_board`，BizBase 入口 `/desk/management-board`（兼容 `/desk/management_board`、`/desk/bizbase-mgmt` 和 `/desk/bizbase_mgmt`，见[命名规范](../../docs/naming.md)）。定位：管理层关注的经营总览。

版本 `0.0.1`：空 App，只含应用入口、标准模块和空工作区，无业务表、无业务数据；工作区暂仅向 System Manager 开放。

## 用 Build 开发

在开发模式站点创建标准 DocType 时保持 Custom 未勾选，模块选择「管理看板」（`management_board`），定义写入 `management_board/management_board/doctype/`。标准工作区保存后导出到 `management_board/management_board/workspace/`；Custom Field 等站点配置需单独导出。界面保存后检查 Git diff 再提交。
