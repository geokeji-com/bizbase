# 自研应用命名

同一概念在不同层使用相同的词根，但不强求字符串完全相同。以「文件分享」为例：

| 位置 | 写法 | 示例 |
| --- | --- | --- |
| 应用 ID、Python 包/文件、数据库字段 | 小写单词，用 `_` 分隔 | `file_share`、`access_domain` |
| 新 Frappe Module Def 与 DocType 名 | 英文名称按词首字母大写，用空格分词，保留约定缩写 | `File Share`、`File Share Domain`、`Yishan ID Binding` |
| 桌面卡片、侧栏、标题、操作标签 | 面向使用者的产品名称，不直接显示包名。英文缩写保留原拼写 | 文件分享、访问记录、移山 ID、管理看板 |
| 自研网站 / Desk 的公开路径 | 小写单词用 `-` 分隔，功能层级用 `/` | `/desk/file-share/access-log`、`/file-share/s/<分享ID>` |

此规范不改写用户数据或第三方框架协议：随机分享 ID、文件名、历史版本、OIDC 标识等保持原始大小写；Python import、Frappe 白名单 API dotted path 和 `/assets/<app>/` 按框架约定保留下划线。

## 现有产品入口

| 显示名 | 安装 ID | 对外入口 | 兼容与边界 |
| --- | --- | --- | --- |
| 移山 ID | `yishan_id` | `/yishan-id` | 管理入口转到 `/desk/yishan-id-binding`；带模块的地址写作 `/desk/yishan-id/yishan-id-binding`，兼容旧的 `yishan_id/…`。保留已安装的 Module Def `yishan_id`。 |
| 文件分享 | `file_share` | `/desk/file-share` | 管理列表、访问记录和对外分享链接各用各的路径。 |
| 管理看板 | `management_board` | `/desk/management-board` | 升级后兼容 `/desk/bizbase-mgmt` 和 `/desk/bizbase_mgmt`。 |
| 销售看板 | `sales_board` | `/desk/sales-board` | 原 `/desk/sales_board` 仍可用。 |
| 运营看板 | `ops_board` | `/desk/ops-board` | 原 `/desk/ops_board` 仍可用。 |
| 客户看板 | `customer_board` | `/desk/customer-board` | 原 `/desk/customer_board` 仍可用。 |

四个看板原有的 Module Def 和 Workspace 名也是下划线形式。它们是已部署的键：权限、已禁用的模块、个人工作区和桌面布局均可能引用它们。管理看板由 `bizbase_mgmt` 统一为 `management_board`，已有站点必须按[管理看板迁移说明](../deploy/prod/management-board-migration.md)迁移这些引用，不可卸载重装；其余三个看板无需迁移。由管理看板应用提供的 BizBase 应用屏给已安装的工作区分配上述 URL，访问仍经 Frappe 当前用户的工作区列表解析，先前保存的地址会在同一页面规范化；保留查询参数与锚点。单独安装某个看板、没有 BizBase 应用屏整合层时，原生入口仍然可用。

新增应用与工作区时先选词根，再定义各层写法。涉及现有标识改名时，把旧地址、已保存的链接和权限配置列入验收；不要在路由或数据上全局转换大小写或分隔符。

## 开发中的 GEO 业务入口

| 显示名 | 安装 ID | 标准模块 | Desk 入口 |
| --- | --- | --- | --- |
| 服务管理 | `geo_service` | `GEO Service` | `/desk/geo-service` |
| 任务执行 | `task_execution` | `Task Execution` | `/desk/task-execution` |
| 内容管理 | `geo_content` | `GEO Content` | `/desk/geo-content` |
| 数据分析 | `geo_analysis` | `GEO Analysis` | `/desk/geo-analysis` |
