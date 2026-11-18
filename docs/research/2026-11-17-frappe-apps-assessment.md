# Frappe 官方应用对 BizBase 的适用性评估

调研日期：2026-11-17。本文为选型建议，未安装新应用、修改运行服务或验证新增应用的完整运行链路。

后续更新：本文最初形成于完整 GEO 业务介绍之前，保留当时的候选与版本证据。结合实际业务、运营手册、补充 SOP 及 App / Site / API 边界，当前安装建议以[项目定位与官方应用选择](../business/2026-11-17-bizbase-positioning-and-app-selection.md)为准。原 13 项包含框架，并非 13 项均应安装；Wiki 已由优先试评调整为明确文档迁移需求后再考虑。

## 结论与评估边界

BizBase 要解决的是多个应用之间的数据隔离，以及身份、权限和基本业务能力不一致。允许销售、运营和开发人员制作不同的应用界面。因此，选型不能以“应用覆盖得越多越好”为标准，而应判断某个应用能否承担一个清晰的数据职责，并服从统一的授权和接入规则。

**当前没有必须立即补装的官方业务 App。** 保留 Frappe、ERPNext、Frappe CRM；优先完成 BizBase 自有共享模型、数据归属、统一 ID、权限及业务 API，再让官方应用和 AI 制作的应用接入。Insights 可在报表问题明确后优先试评；Wiki 可在确有统一文档发布需求时试评。其余应用按业务触发条件选装。

当前本地基线为 Frappe 16.56.0、ERPNext 16.55.0、CRM 16.0.4，见[项目状态](../bizbase.md)与[部署记录](../../deploy/local-crm/README.md)。用户尚未介绍实际 GEO 服务流程；下文的售前、交付、知识管理用途均为候选用途，不代表已确认的业务需求。

本报告先查 Context7，再以官方仓库的固定发布 tag、依赖声明和源码补足。Context7 返回的 develop 文档不能直接代表 v16 发布版。源码声明满足版本范围，只代表可进入安装验证，**不等于与本机整个应用组合已经兼容验收**。

## 官方身份的判定

本次列入的项目均核对了 `frappe` GitHub 组织下的仓库、项目作者或官网链接，不以 Frappe Cloud Marketplace 上架为官方认证。Raven 当前位于 [`frappe/raven`](https://github.com/frappe/raven)，发布版作者与 publisher 均为 Frappe；不能继续根据历史仓库归属把它简单列为社区应用。[Raven v3.2.0 元数据](https://github.com/frappe/raven/blob/v3.2.0/pyproject.toml)

官方维护也不意味着所有应用共用一套业务数据模型、权限语义或发布周期。本次没有将未核验维护方的市场应用纳入建议。

## 安装分级

| 分级 | 项目 | 建议及触发条件 |
| --- | --- | --- |
| 保留现有 | Frappe Framework | 用作身份、模型、权限、接口和后台任务基础；补充公司业务约束，而非另建通用框架。 |
| 保留现有 | ERPNext | 承担报价、订单、客户交易档案、账务等专业单据；仅启用实际使用的业务流程。 |
| 保留现有 | Frappe CRM | 承担销售线索和商机；不要把其组织、联系人或销售角色自动等同于全公司的主数据与权限。 |
| 优先试评 | Insights | 先定义一份真实的跨系统报表，再用只读数据和不同权限账号验证；它是分析工具，不是交易数据源头。 |
| 优先试评 | Wiki | 需要统一发布数据字典、API 接入说明、SOP，并有维护人时试评；已有 Git 文档够用时无需安装。 |
| 有明确需求才装 | Helpdesk | 出现正式的客户工单、SLA、客服分派或客户自助门户需求时评估。 |
| 有明确需求才装 | Frappe HR / HRMS | 要管理员工生命周期、请假、考勤、报销或薪酬时评估；仅为统一登录和角色，无需 HRMS。 |
| 有明确需求才装 | Raven | 确需在业务单据旁协作、聊天和接收通知时评估；先考虑现有通信工具能否满足。 |
| 有明确需求才装 | Builder | 需要可视化制作官网、专题页或动态内容页面时评估；它不替代统一数据与权限接口。 |
| 有明确需求才装 | Learning / LMS | 有课程、考试、培训记录、认证需求时评估；普通知识文章用 Wiki 或现有文档即可。 |
| 有明确需求才装 | Gameplan | 需要按主题、项目开展异步讨论并长期保留讨论上下文时评估；不默认取代业务项目模型。 |
| 暂不建议 | 独立 Drive | 官方仓库已归档并迁入 Suite，不建议再以旧独立应用作为新部署起点。 |
| 暂不建议 | Suite | 当前仓库标为 WIP，覆盖大量协作产品，部署与迁移范围明显超过眼前底座问题；先观察和隔离试验。 |

以上是针对 BizBase 当前目标的判断，不是官方应用质量排名。具体产品能力与版本证据见下文。

## 固定版本与依赖核验

下表的“候选版本”是本次访问官方 latest release 接口得到的非预发布版本。正式安装还需冻结对应 commit 与镜像，并在试验环境验证；不能使用随时间漂移的 `latest`。

| 项目 | 本次候选 tag / 官方发布分支 | 对 Frappe 16 的直接证据 | 附加应用或限制 |
| --- | --- | --- | --- |
| Insights | `v3.15.1` / `version-3` | `frappe >=15.0.0,<17.0.0`；README 的 version-3 矩阵明确含 Frappe 16、Python 3.14、Node 24。[依赖](https://github.com/frappe/insights/blob/v3.15.1/pyproject.toml)、[矩阵](https://github.com/frappe/insights/blob/v3.15.1/README.md#compatibility-matrix) | 依赖 DuckDB、Ibis、Pandas 等分析组件；完整组合尚未试装。 |
| Helpdesk | `v16.1.0` / `version-16` | `frappe >=16.0.0,<17.0.0`。[依赖](https://github.com/frappe/helpdesk/blob/v16.1.0/pyproject.toml) | `telephony >=0.0.1,<1.0.0`，hooks 的 required_apps 也为 telephony。具体 Telephony tag 尚待安装前核验。[hooks](https://github.com/frappe/helpdesk/blob/v16.1.0/helpdesk/hooks.py) |
| Wiki | `v3.5.0` / `version-3` | `frappe >=15.0.0,<=17.0.0-dev`；README 将 version-3 标为支持 15/16 的稳定系列。[依赖](https://github.com/frappe/wiki/blob/v3.5.0/pyproject.toml)、[说明](https://github.com/frappe/wiki/blob/v3.5.0/README.md#compatibility) | 依赖 DuckDB 等库；无需把 Wiki 当成客户或服务数据的权威来源。 |
| HRMS | `v16.53.2` / `version-16` | 同时要求 `frappe >=16.50.0,<17.0.0` 和 `erpnext >=16.50.0,<17.0.0`；当前基线满足声明范围。[依赖](https://github.com/frappe/hrms/blob/v16.53.2/pyproject.toml) | 明确依赖 ERPNext。[hooks](https://github.com/frappe/hrms/blob/v16.53.2/hrms/hooks.py) |
| Raven | `v3.2.0` / `main` | `frappe >=15.111.0,<=17.0.0-dev`；README 把 main 与 Frappe 16 配对列为 Stable。[依赖](https://github.com/frappe/raven/blob/v3.2.0/pyproject.toml)、[矩阵](https://github.com/frappe/raven/blob/v3.2.0/README.md#compatibility) | 含 AI、文档解析等 Python 依赖；外部 AI 能力另需配置服务。 |
| Builder | `v1.39.0` / `master` | 声明 `frappe >=15.121.3,<18.0.0`，源码注释另外明确 Frappe 16 的实际前端最低版本为 16.36.1；当前 16.56.0 满足。[依赖及注释](https://github.com/frappe/builder/blob/v1.39.0/pyproject.toml) | 不能只看跨大版本范围而忽略 v16 最低版本注释。 |
| Learning | `v16.1.1` / `version-16` | `frappe >=16.0.0,<17.0.0`。[依赖](https://github.com/frappe/lms/blob/v16.1.1/pyproject.toml) | 依赖 `payments >=0.0.1,<1.0.0`；还声明系统包。具体 Payments tag 尚待安装前核验。安装依赖不代表必须开通付费课程。 |
| Gameplan | `v0.1.33` / `develop` | 声明 `frappe >=16.0.0-dev`；README 明确支持 Frappe 16，且说明没有独立 version-16 分支。[依赖](https://github.com/frappe/gameplan/blob/v0.1.33/pyproject.toml)、[支持版本](https://github.com/frappe/gameplan/blob/v0.1.33/README.md#supported-versions) | 不能套用“所有 develop 都是 Frappe 17”的推断；若选用应固定该 release，仍需同站点验证。 |
| 独立 Drive | 不选新安装版本 | 官方仓库已 archived，README 顶部指向 Suite。[归档说明](https://github.com/frappe/drive) | 历史 standalone 安装命令仍出现在 README，不能据此忽略归档状态。 |
| Suite | 仅查看 `develop`，未确认可推荐的稳定 tag | `frappe >=16.0.0,<18.0.0`、Python `>=3.14,<3.15`；项目仍标 WIP。[项目](https://github.com/frappe/suite)、[依赖](https://github.com/frappe/suite/blob/develop/pyproject.toml) | 符合版本范围不等于适合生产。本文只建议观察，未验证迁移与组合兼容。 |

Helpdesk 存在明确的版本文档差异：Context7 的 develop 迁移说明提到 Studio 与 RediSearch，但本次固定的 `v16.1.0` 声明依赖 Telephony，不能直接把 develop 的新增依赖套入该 tag。后续若改选更新 release，需要重新检查。

## 各应用与数据底座的关系

### Frappe、ERPNext、CRM：保留，但职责要分清

Frappe 提供 DocType、用户身份、权限、REST 接口和后台任务等基础设施。原生 API 可以作为实现工具，但 BizBase 对外还需要稳定的业务契约、调用者授权、幂等、统一 ID 和审计语义；不应让每个 AI 应用任意写内部业务表。[REST API](https://docs.frappe.io/framework/user/en/api/rest)、[后台任务](https://docs.frappe.io/framework/user/en/api/background_jobs)、[权限检查的 v16 API 源码](https://github.com/frappe/frappe/blob/version-16/frappe/api/v2.py)

ERPNext 中的客户交易档案、报价和销售订单继续承担商业交易职责；Frappe CRM 的线索和商机承担售前职责。官方提供 CRM 与 ERPNext 的集成，但这需要设置和流程选择，不能把“安装在同一站点”视为已经形成统一业务模型。[CRM 与 ERPNext 集成](https://docs.frappe.io/crm/erpnext)

当前已知的边界是：`Lead` / `CRM Lead`、`Opportunity` / `CRM Deal`、`Customer` / `CRM Organization` 为不同记录；联系人使用 Frappe 的 `Contact`。因此必须决定公司的“客户主体”如何被识别、由谁修改，并给这些专业记录建立明确映射。**新增一个 `bizbase_core` 模型也不能成为无人负责的第三套客户表。**是否新增实体、复用现有实体或只建立身份映射，应在真实 GEO 流程梳理后决定。[CRM 联系人源码](https://github.com/frappe/crm/blob/v16.0.4/frontend/src/pages/Contacts.vue)、[CRM 数据模型](https://github.com/frappe/crm/tree/v16.0.4/crm/fcrm/doctype)

### Insights：优先验证真实报表，不把 BI 当数据统一工程

Insights 提供多数据源连接、查询构建、图表和看板，适合在业务口径明确后验证跨系统报表。把几个数据库连接到同一看板只能集中查询，不能自动消除重复客户、冲突字段或不同统计口径。[功能与架构](https://github.com/frappe/insights/blob/v3.15.1/README.md)

固定版本已有站点数据库的用户权限过滤实现，但 `apply_user_permissions` 设置会影响该路径；外部数据库和上传文件没有可直接套用的 Frappe 行权限。它还有自己的数据源、表、团队、工作簿等授权对象，以及公共链接和后台任务执行身份。试评必须分别验证当前用户、分享对象、导出、定时任务和公共页面，不能笼统宣称“同站点，所以继承全部业务权限”。[表数据权限实现](https://github.com/frappe/insights/blob/v3.15.1/insights/insights/doctype/insights_table_v3/insights_table_v3.py)、[资源权限](https://github.com/frappe/insights/blob/v3.15.1/insights/permissions.py)、[执行身份](https://github.com/frappe/insights/blob/v3.15.1/insights/permission_user.py)

建议第一份报表只读访问已经有清晰定义的数据，先不开放任意数据库连接和公共分享。若只有少量固定报表，先评估 Frappe/ERPNext 原生报表能否解决，避免为界面需求提前引入分析数据副本。

### Wiki：适合发布标准，不负责执行业务规则

Wiki 的空间、富文本/Markdown、变更评审、历史记录和 GitHub 同步，适合发布数据字典、API 接入指南、业务说明与 SOP。它解决知识组织问题；真正的数据校验和权限仍必须由服务器执行。公共与私有空间应单独规划，文档中的客户信息不能因为业务数据有权限就默认安全。[Wiki v3.5.0 功能](https://github.com/frappe/wiki/blob/v3.5.0/README.md)

若当前规模下仓库文档已经足够，先完成文档内容和维护责任，不必为“有一个知识库”而安装 Wiki。

### Helpdesk：工单场景明确后再引入

Helpdesk 有客服与客户入口、工单、SLA、分派规则、知识库和保存回复，适合客户反馈与支持处理。它不自动代表 GEO 的全部交付流程。[Helpdesk 功能](https://github.com/frappe/helpdesk/blob/v16.1.0/README.md)

关键风险是 `HD Customer` 是独立客户对象，虽然联系人链接到 `Contact`，但不等于 ERPNext `Customer`。固定版本有 ERPNext 同步逻辑，并受 `ERPNext HD Settings.enabled` 控制；同步包含创建、部分字段更新，以及关联记录的重命名、合并和删除处理。接入时要确认唯一写入方和级联行为，不能只打开同步开关就视为治理完成。[HD Customer 模型](https://github.com/frappe/helpdesk/blob/v16.1.0/helpdesk/helpdesk/doctype/hd_customer/hd_customer.json)、[同步开关与映射](https://github.com/frappe/helpdesk/blob/v16.1.0/helpdesk/integrations/erpnext/utils.py)、[客户事件处理](https://github.com/frappe/helpdesk/blob/v16.1.0/helpdesk/integrations/erpnext/customer.py)

### HRMS、Raven、Builder、Learning、Gameplan：按场景选装

| 应用 | 真实能力 | 对 BizBase 的边界 |
| --- | --- | --- |
| HRMS | 员工生命周期、请假考勤、报销、绩效、薪酬。[官方说明](https://github.com/frappe/hrms/blob/v16.53.2/README.md) | 员工记录不等于登录用户。需要 HR 业务时再接入，并明确 HR 资料与业务应用可访问范围；不为获得用户/角色能力而安装。 |
| Raven | 频道、私聊、线程、文件、单据卡片、通知及可配置的机器人/AI。[官方说明](https://github.com/frappe/raven/blob/v3.2.0/README.md) | 频道成员关系不能替代客户或服务权限；转发单据卡片、通知、机器人读取都需要验证授权。不把聊天记录当核心业务状态。 |
| Builder | 可视化页面制作、动态数据页面、复用组件及发布。[官方说明](https://github.com/frappe/builder/blob/v1.39.0/README.md) | 页面数据脚本与公开路由仍需权限审查；它解决制作界面的效率，不自动保证数据源统一。无需要求所有 AI 应用改用 Builder。 |
| Learning | 课程、章节、课时、测验、作业、班级、证书。[官方说明](https://github.com/frappe/lms/blob/v16.1.1/README.md) | 课程学员和讲师角色不等于公司的全部业务角色。只有正式培训或课程产品需要这一套记录。 |
| Gameplan | 异步主题讨论、空间、页面及协作。[官方说明](https://github.com/frappe/gameplan/blob/v0.1.33/README.md) | 自有 `GP Team`、`GP Project`、`GP Task` 及权限钩子，不应直接替代底座团队、GEO 服务实例或 ERP 项目。[权限与模型入口](https://github.com/frappe/gameplan/blob/v0.1.33/gameplan/hooks.py) |

### Drive 与 Suite：需要重新评估产品路线

独立 Drive 已明确归档并迁入 Suite。Suite 将 Drive、Writer、Sheets、Slides、Meet、Mail、Calendar 合到一个应用，但官方也明确它与这些独立应用存在模块/DocType 冲突，不能在仍安装这些应用的站点上直接共存。[Drive 归档说明](https://github.com/frappe/drive)、[Suite 内容与迁移约束](https://github.com/frappe/suite/blob/develop/README.md)

Suite 当前不是本项目解决数据隔离的必要依赖。若仅需要给客户、任务附加文件，先利用已有 Frappe 文件能力；若需要完整协作文档套件，再单独审查 Suite 的稳定发布、存储、权限、备份和迁移。本文未验证 Suite 的生产可用性。

## 资源与部署影响

不提供未经实测的“每个 App 占多少 MB 内存”估算。同站点应用可以复用现有基础服务，但会增加 Python/前端依赖、数据表、索引、事件钩子、定时任务和升级组合；并非零成本。[Frappe Apps](https://docs.frappe.io/framework/user/en/basics/apps)

| 应用 | 本次确认的部署影响 | 尚需验证 |
| --- | --- | --- |
| Insights | DuckDB/Ibis/Pandas 和数据库连接器；分析查询、数据存储与缓存会占用资源。[依赖](https://github.com/frappe/insights/blob/v3.15.1/pyproject.toml) | 是否需要独立分析实例、数据副本与刷新任务，取决于真实数据量和查询负载。 |
| Helpdesk | 固定 tag 需要 Telephony App，并增加工单、邮件与后台任务相关能力。[依赖](https://github.com/frappe/helpdesk/blob/v16.1.0/pyproject.toml) | 实际是否接邮件或电话服务，以及所选 Telephony 版本。不能据 develop 文档先加装 Studio/RediSearch。 |
| Wiki | Markdown 与 DuckDB 等库。[依赖](https://github.com/frappe/wiki/blob/v3.5.0/pyproject.toml) | 文档规模、搜索、附件与发布任务的实际负载。 |
| HRMS | 复用 ERPNext 依赖，新增 HR 业务表和后台处理。[依赖](https://github.com/frappe/hrms/blob/v16.53.2/pyproject.toml) | 考勤导入、薪酬批处理、附件量以及组合升级。 |
| Raven | 消息、文件、实时通信，Python 依赖含 AI 与文档处理库。[依赖](https://github.com/frappe/raven/blob/v3.2.0/pyproject.toml) | 并发连接、文件保留、推送与外部 AI 服务配置。 |
| Builder | 前端资源及 Pandas、DuckDB、LiteLLM 等依赖。[依赖](https://github.com/frappe/builder/blob/v1.39.0/pyproject.toml) | 公网页面访问量、动态脚本负载、AI 是否启用。 |
| Learning | Payments App；声明 `libxml2-dev`、`libxslt1-dev` 等系统依赖。[依赖](https://github.com/frappe/lms/blob/v16.1.1/pyproject.toml) | 视频存储/分发、直播集成与学习人数。 |
| Gameplan | 当前固定 tag 的 hooks 注册 SQLite 搜索。README 的旧架构段仍提及 RediSearch，不能据此直接更换现有 Redis。[hooks](https://github.com/frappe/gameplan/blob/v0.1.33/gameplan/hooks.py)、[README](https://github.com/frappe/gameplan/blob/v0.1.33/README.md) | 以固定版本完整代码和试装确认搜索后端、通知和索引负载。 |
| Suite | 声明 ffmpeg；协作编辑和视频会议涉及独立服务，邮件涉及 JMAP/邮件服务器与可选 Suite Cloud 管理体系。[依赖](https://github.com/frappe/suite/blob/develop/pyproject.toml)、[架构](https://github.com/frappe/suite/blob/develop/README.md) | 完整部署拓扑、存储增长、备份一致性及各产品实际启用范围。 |

## 安装前必须解决的接入问题

1. **确定数据归属。** 客户主体、品牌、服务实例、联系人等概念尚需结合 GEO 流程确认；每类共享数据和重要字段要有明确维护方。相同数据库或全局 ID 不能代替字段归属。
2. **定义权限交集。** 应用能访问的能力与当前用户能访问的数据取交集；后台任务另设最小权限身份。普通应用不能持有 Administrator 密钥。查询、搜索、导出、附件和异步任务都要执行同一规则。
3. **区分应用运行位置与信任边界。** 未经审查的 AI 生成服务器代码不应直接安装为共享站点 App。对它们优先开放受控 API；被安装到共享后端的 App 代码属于更高信任层，需要代码与依赖审查。
4. **规划专业数据与共享数据的映射。** CRM 线索、ERP 交易、Helpdesk 工单等保留专业模型，不能强行合并成一张万能表；共享身份及事实从一个明确入口维护。
5. **用组合测试决定是否安装。** 固定版本，隔离试装，验证两种不同界面操作同一客户、普通用户越权失败、撤权生效、重复请求幂等、变更可追溯、原有 CRM/ERP 功能正常、备份可恢复。角色相同不等于所有应用自动执行同一授权规则。

## 建议推进次序

第一步梳理一条真实 GEO 业务链，明确必须共享的对象和写入责任；第二步完成最小 BizBase 业务接口与两应用接入验证；第三步选择一份真实报表验证 Insights 是否比原生报表更合适；第四步根据工单、文档、HR、培训、协作的真实需求逐项安装。

这条次序允许保留多个界面和不同操作方式，同时用数据定义、写入入口和服务器权限保证基本事实一致。新增 App 的申请应说明“要解决什么业务问题、复用哪些共享实体、增加哪些专业数据、由谁维护”，而不是仅列出产品名。

## 证据局限

- 官方仓库状态、release 与源码访问日期均为 2026-11-17；它们会继续变化。版本表中的 tag 是本次调研快照，安装前仍需检查发布状态与依赖变化。
- 新候选均未在当前 Docker 组合中安装、压测或验收；兼容结论分为“官方版本声明支持”与“本机实测通过”，本文只有现有 Frappe/ERPNext/CRM 有后者的历史部署记录。
- 对 Insights、Helpdesk、Gameplan 已发现 develop 文档、README 与固定 tag 实现的差异，报告按固定 tag 给出范围；没有把尚未核实的功能写成既有能力。
- 当前尚无公司完整 GEO 流程、数据量、并发、审计要求和现有工具清单，因此没有给出容量承诺、迁移周期或替换现有系统的决定。
