# 管理看板

显示名称 **管理看板**；Python 包、App 安装标识、标准模块和工作区内部名称统一为 `bizbase_mgmt`，入口 `/desk/bizbase_mgmt`。定位：管理层关注的经营总览。

版本 `0.0.1`：空 App，只含应用入口、标准模块和空工作区，无业务表、无业务数据；工作区暂仅向 System Manager 开放。由原「GEO 运营」（`geo_operations`）按角色拆分而来。

## 用 Build 开发

在开发模式站点创建标准 DocType 时保持 Custom 未勾选，模块选择「管理看板」（`bizbase_mgmt`），定义写入 `bizbase_mgmt/bizbase_mgmt/doctype/`。标准工作区保存后导出到 `bizbase_mgmt/bizbase_mgmt/workspace/`；Custom Field 等站点配置需单独导出。界面保存后检查 Git diff 再提交。
