# GEO 运营

显示名称统一为 **GEO 运营**；Python 包、App 安装标识、标准模块、工作区内部名称统一为 `geo_operations`，入口为 `/desk/geo_operations`。中文界面通过应用自带翻译显示模块和工作区名称。

版本 `0.0.1`：空 App，包含应用入口、标准模块和空工作区，无业务表或业务数据。工作区仅向 System Manager 开放。

## 用 Build 开发

源码位于 `apps/geo_operations`，由当前仓库管理。现有 `frontend` 站点开启开发模式，App 目录持久挂载。创建标准 DocType 时保持 Custom 未勾选，模块选择「GEO 运营」（技术标识 `geo_operations`），定义会写入 `geo_operations/geo_operations/doctype/`。

标准工作区可保存导出；Custom Field、Property Setter、Client Script、Workflow 等站点配置需按对象选择 Export Customizations 或限定范围的 fixtures。当前未配置 fixtures；私人页面、业务数据和附件不会随源码发布。界面保存后仍需检查 Git diff 并提交。

部署及改名验证见 [本地预览说明](../../deploy/local-crm/README.md)。
