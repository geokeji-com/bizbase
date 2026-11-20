# 运营看板

显示名称 **运营看板**；Python 包、App 安装标识、标准模块和工作区内部名称统一为 `ops_board`，BizBase 入口 `/desk/ops-board`（兼容 `/desk/ops_board`）。定位：运营关注的服务、监测与交付。

版本 `0.0.1`：空 App，只含应用入口、标准模块和空工作区，无业务表、无业务数据；工作区暂仅向 System Manager 开放。由原「GEO 运营」（`geo_operations`）按角色拆分而来。

## 用 Build 开发

在开发模式站点创建标准 DocType 时保持 Custom 未勾选，模块选择「运营看板」（`ops_board`），定义写入 `ops_board/ops_board/doctype/`。标准工作区保存后导出到 `ops_board/ops_board/workspace/`；Custom Field 等站点配置需单独导出。界面保存后检查 Git diff 再提交。
