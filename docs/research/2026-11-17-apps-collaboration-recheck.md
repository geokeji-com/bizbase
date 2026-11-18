# 协作、官网与培训 App 复核

复核日期：2026-11-17。结合已介绍的 GEO 服务链、六品牌官网和运营 SOP，对前期清单中的 Raven、Builder、Learning、Gameplan 重新判断。本文没有安装应用、改变运行服务或测试新增应用组合。

## 结论

这四项均不是 BizBase 共享数据底座的必要依赖，目前不建议立即安装。Builder 可作为官网编辑工具的候选，Learning 可作为标准化培训工具的候选；Raven 和 Gameplan 暂缓。判断依据是公司是否缺少对应的业务能力，而非单纯避免界面重复。

| App | 建议 | 与现有业务的关系 | 重新评估的触发条件 |
|---|---|---|---|
| Builder | 后续按需试点 | 六品牌官网承担留资和自有信源发布，确实有适用场景；但现有官网通过 API 接入也能实现数据统一，无须为中台重建网站 | 运营明确需要统一可视化改版、专题页模板与发文页面，先选一个品牌试点 |
| Learning / LMS | 后续按需安装 | 适合把新人培训、售前诊断和运营规则变成课程、测验、作业与学习记录；仅有一份 SOP 不构成安装理由 | 有培训负责人、课程、考核标准，且需要追踪谁学过、是否通过 |
| Raven | 暂不安装 | 可在单据旁讨论、接收事件通知；当前更需要把已有沟通中的决定保存为业务确认事实 | 现有通信工具无法满足单据协作，团队愿意使用另一套内部通信入口 |
| Gameplan | 暂不安装 | 适合长期异步讨论、方案评审和会议记录；不会自动执行 GEO 服务交接、客户确认和考核规则 | 团队明确需要主题讨论平台，且已有文档、任务与沟通工具无法满足 |

## Builder：官网展示与编辑，不承担业务权威数据

官方固定版本支持可视化页面、可复用组件、动态数据页面、一键发布和页面历史。可服务于官网文章展示和活动页制作。[Builder v1.39.0 README](https://github.com/frappe/builder/blob/v1.39.0/README.md)

对 BizBase 的建议：文章正文版本、事实依据、发布授权和发布回执归属业务模型，Builder 读取可发布内容；留资提交进入统一线索接入流程，保留入口、品牌、来源及分配记录。不要让每个页面自行创建另一套线索或文章权威表。现有官网可以继续使用原技术栈，不要求迁入 Builder。

Context7 返回的是 develop 资料，本次另读了固定 tag 的页面脚本说明：脚本按访问者运行，通常为 Guest；`frappe.db.get_all` 绕过权限检查。故“页面可以直接读数据库”并不保证对外只公开获准数据，官网查询必须限制为已批准公开的内容和字段。[固定版数据脚本说明](https://github.com/frappe/builder/blob/v1.39.0/skills/frappe-builder/reference/data-and-scripts.md)

依赖声明为 `frappe >=15.121.3,<18.0.0`，注释另外要求 v16 至少为 16.36.1。当前 16.56.0 满足该声明。新增依赖含 Pandas、DuckDB、LiteLLM 等；不能因名称是网页编辑器就认为没有后端依赖。六个独立域名、路由、模板与发布权限的具体部署方式尚未验证，不承诺安装后自动统一六个站点。[固定版依赖及版本注释](https://github.com/frappe/builder/blob/v1.39.0/pyproject.toml)

## Learning：培训事实与交付事实分开

官方产品提供课程/章节/课时、班级、测验、作业和证书，适合有考核要求的标准化培训。[Learning v16.1.1 README](https://github.com/frappe/lms/blob/v16.1.1/README.md)

对 BizBase 的建议：保存“某员工学过某版课程、通过某次考核”等培训事实，并关联人员身份；某个客户是否完成资料交接、是否确认竞品、是否允许发文，仍由服务流程保存。完成课程不等于获得某个客户的访问权，也不等于完成该客户的 SOP。

固定 tag 要求 `frappe >=16.0.0,<17.0.0`、`payments >=0.0.1,<1.0.0`，且声明 `libxml2-dev`、`libxslt1-dev` 系统包；Payments 是应用依赖，不代表必须启用收费课程。若安装，应连同 Payments 版本一起验证。[依赖声明](https://github.com/frappe/lms/blob/v16.1.1/pyproject.toml)

其 hooks 还包含课程权限、文件权限、用户事件以及统计/提醒任务；接入现有 Site 需验证这些行为与现有 App 的组合。课程视频、附件、搜索索引和实际学员量会影响资源需求，本次未作容量测量。[固定版 hooks](https://github.com/frappe/lms/blob/v16.1.1/lms/hooks.py)

## Raven：可用作协作入口，不作为确认记录

官方提供频道、私聊、线程、文件、单据卡片、文档通知和可配置机器人；README 将 main 与 Frappe 16 配对列为稳定组合。[Raven v3.2.0 README](https://github.com/frappe/raven/blob/v3.2.0/README.md)

对 BizBase 的建议：未来若选用，可以把“资料待确认”“投放回链缺失”等通知送到频道；确认动作仍需落为具有操作者、授权范围、目标版本和时间的业务记录。群成员、已读消息、点赞不能替代客户确认或服务权限。现阶段先接现有通信工具，集中保存业务决定；仅增加内部聊天界面不会自动接入小红书、抖音和客户群中的线索。

固定 tag 的作者为 Frappe，声明 `frappe >=15.111.0,<=17.0.0-dev`，符合当前框架版本范围。Python 依赖包含 OpenAI、OpenAI Agents、MarkItDown、Pandas、Google Document AI 等；外部 AI 功能是否启用及其服务费用需要另行配置和判断。消息量、附件保留和并发通信需要实际测量。[固定版元数据和依赖](https://github.com/frappe/raven/blob/v3.2.0/pyproject.toml)

## Gameplan：讨论空间不等于 GEO 项目

官方定位是异步讨论平台，支持按项目、客户或主题组织空间及记录页面。README 明确支持 Frappe 16，使用 develop 分支且没有单独 version-16 分支。[Gameplan v0.1.33 README](https://github.com/frappe/gameplan/blob/v0.1.33/README.md)

对 BizBase 的建议：未来可以用于内容策略复盘、方案评审和会议记录，但讨论空间仅关联正式服务 ID。自己的 `GP Project`、`GP Task`、`GP Team` 具有专门权限钩子，不能直接当作 GEO 服务项、ERP 项目或全公司授权范围。[固定版权限与任务 hooks](https://github.com/frappe/gameplan/blob/v0.1.33/gameplan/hooks.py)

固定 tag 依赖声明为 `frappe >=16.0.0-dev`。其 hooks 注册 SQLite 搜索、事件钩子和定时任务；README 的旧架构段仍提到 RediSearch，本次不据此要求给当前 Redis 加装搜索模块，实际部署应以完整固定版本验证为准。[依赖](https://github.com/frappe/gameplan/blob/v0.1.33/pyproject.toml)、[搜索和任务声明](https://github.com/frappe/gameplan/blob/v0.1.33/gameplan/hooks.py)

## 版本与验证边界

- 本次核查固定版本：Raven `v3.2.0`、Builder `v1.39.0`、Learning `v16.1.1`、Gameplan `v0.1.33`；这是已有候选的复核，不声称重新取得最新发布版本。
- 与 Frappe 16.56.0 的版本范围相容，只代表可以进入试装；不等于与 ERPNext 16.55.0、CRM 16.0.4 及未来 BizBase App 的完整组合已经验收。
- 不提供未经实测的内存或成本数字。依赖、表、索引、任务和共享权限钩子都会增加维护工作；实际资源影响按启用功能与业务量验证。
- 安装决策不应仅因为“同一个 Site 数据共通”。这些 App 的对象和权限各有语义，需要通过共享身份、明确关联和服务端规则接入。
