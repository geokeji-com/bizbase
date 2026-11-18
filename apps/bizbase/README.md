# GEO App

应用显示名称为 **GEO**。安装包名仍为 `bizbase`，标准模块和工作区标识保留 `BizBase`，入口仍为 `/desk/bizbase`。Frappe 自带的 `Geo` 模块属于框架地理信息功能，不作为本业务应用的模块。

版本 `0.0.1`：空的 Frappe App，包含应用首页入口、`BizBase` 标准模块和空工作区，没有业务表、业务数据、API 或后台任务。当前工作区仅向 System Manager 开放，业务权限后续按需求配置。

本目录由外层 `geokeji-com/bizbase` 仓库管理，不创建嵌套 Git 仓库。安装在现有 `frontend` 站点，继续使用原来的账号、数据库和文件卷。

## 用 Build 开发

本地部署将整个 App 目录挂载到容器的 `apps/bizbase`，并仅在该预览站点启用 `developer_mode`。进入 Build 创建标准 DocType 时，确认 `Custom` 未勾选（当前新建界面默认如此），模块选择 `BizBase`；框架会把定义和控制器写入 `bizbase/bizbase/doctype/`。后续编辑先检查 Git diff，再提交。

标准工作区在开发模式下保存到所属模块目录；私人页面不属于可发布定义。Custom Field、Property Setter、Client Script、Workflow 等站点配置不能仅靠填写模块字段自动进入 Git；需要按实际对象选择 Export Customizations 或范围明确的 fixtures，并验证导入。本空 App 尚未配置 fixtures，避免带入其他应用或站点数据。

自定义模块的 `App Name` 只决定导航位置，不会把它变成 App 所拥有的标准模块。业务记录与附件保留在数据库和站点卷中，不随源码提交。

部署、备份及验证见 [本地预览说明](../../deploy/local-crm/README.md)。
