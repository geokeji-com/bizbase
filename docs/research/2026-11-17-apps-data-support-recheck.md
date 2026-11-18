# 数据分析、知识、客服与人事 App 复核

复核日期：2026-11-17。本文在公司 GEO 业务口述、运营手册和客户优化前 SOP 已补充后，更新 Insights、Wiki、Helpdesk、HRMS 四项选型建议。未安装应用、修改运行服务或进行组合验收。

## 本轮结论

当前先保留 Frappe、ERPNext、CRM，开发 BizBase 的共享实体、服务项、范围与指标版本、授权、交付证据和成本事实。四个候选 App 均不构成首期共享数据链的必装依赖。

| App | 当前判断 | 具体业务价值 | 为什么现在不直接装 | 何时再装 |
|---|---|---|---|---|
| Insights | 后装，新增 App 中优先试评 | 将销售漏斗、服务进度、效果、投放成本做内部经营分析 | 客户服务范围、指标版本和费用归属尚未落实；BI 不能替代这些定义。客户报告还需证据穿透、口径冻结及服务授权 | 先有一份可对账的真实经营报表和稳定数据源，再试评；固定报表若原生报表已满足则无需装 |
| Wiki | 当前不装，保留为文档迁移选项 | 发布 SOP、运营话术、数据字典、API 接入手册 | 已有运营手册及仓库文档；增加 Wiki 不会让“已发送”“已确认”“已验收”自动成为结构化事实 | 明确需要迁移统一文档入口，并确定编辑、审阅、维护责任后再装 |
| Helpdesk | 后装，取决于正式客服工单需求 | 客户反馈受理、分派、响应时限和关闭记录 | 建群、资料确认、换词、暂停、报告交付属于 GEO 服务生命周期，不能只用工单状态代替 | 客户问题量需要统一受理和 SLA 时引入；工单关联现有服务项和实体 |
| Frappe HR / HRMS | 后装，进入员工管理或薪酬阶段再评估 | 员工档案、入离职、请假、考勤、报销、绩效、薪酬 | 用户和角色已有框架能力；销售/运营分成需要先明确贡献、回款、成本、考核和规则版本，安装 HRMS 不会自动给出公司算法 | 明确接管 HR 流程或正式薪酬发放时采用；将已审核的业务结算结果交给 HR 流程 |

以上为结合公司需求的架构建议；产品能力的官方依据与适用边界如下。

## Insights

官方定位为 BI，提供多数据源连接、查询构建、可视化和看板，适合非开发人员做分析。[v3.15.1 官方说明](https://github.com/frappe/insights/blob/v3.15.1/README.md)

建议先用于**内部经营分析**：按服务项和周期核对收入依据、媒体成本、执行费用及效果。Top 3/Top 5、可见度、引用率的口径、分母及分析版本由 BizBase 记录和计算；不让每张工作簿自行定义合同指标。客户证据看板可继续由独立应用使用业务 API 构建；Insights 是否承担客户展示，应经真实授权场景验收后决定。

该版本并非没有业务权限支持：站点数据源可调用 Frappe 的权限查询并过滤列与行，但受 `apply_user_permissions` 配置控制，外部数据库和上传数据不会自动得到 Frappe 权限过滤。[表读取及权限过滤源码](https://github.com/frappe/insights/blob/v3.15.1/insights/insights/doctype/insights_table_v3/insights_table_v3.py) Insights 还管理自己的数据源、表、团队、工作簿等资源权限；公共链接、预览与定时提醒涉及指定执行身份。[资源权限](https://github.com/frappe/insights/blob/v3.15.1/insights/permissions.py)、[执行身份](https://github.com/frappe/insights/blob/v3.15.1/insights/permission_user.py)

因此试评至少覆盖销售、运营、渠道、客户的不同服务范围，以及共享、导出和定时执行；同 Site 安装本身不能证明授权一致。若开放到客户，不能用内部管理员的可见范围生成公开结果。

## Wiki

官方具备空间、富文本编辑、变更请求与审阅、页面历史、搜索和 GitHub 同步；空间可以公开或按角色限制访问。[v3.5.0 官方说明](https://github.com/frappe/wiki/blob/v3.5.0/README.md)

这些能力适合管理手册的**内容与版本**。公司 SOP 还涉及分支、责任人、等待客户确认、执行证据和服务时钟，应在 BizBase 中形成记录；Wiki 页面可以解释步骤并链接业务入口，不能成为执行状态的唯一来源。公司事实资料及客户授权同样应通过结构化记录与受控附件维护，不能把一篇手册文章等同于事实库。

现有手册能继续使用时，不把“数据统一”扩大成全公司文档迁移。若后续决定采用 Wiki，可优先迁移通用 SOP 和公开接入说明，再评估含客户信息的私有文档。

## Helpdesk

官方具备客服与客户入口、工单、SLA、分派规则、知识库与常用回复。[v16.1.0 官方说明](https://github.com/frappe/helpdesk/blob/v16.1.0/README.md)

可承接报告疑问、内容纠错、发布异常等**问题受理过程**。换词、暂停、资料确认等操作即使由工单提出，仍应调用 BizBase 的正式业务动作，在服务项及范围版本上留痕。工单关闭不自动表示合同验收或客户授权完成。

Helpdesk 有独立的 `HD Customer`，联系人关联 `Contact`；它并不直接复用 ERPNext 的 `Customer` 记录。[客户模型](https://github.com/frappe/helpdesk/blob/v16.1.0/helpdesk/helpdesk/doctype/hd_customer/hd_customer.json) 官方 ERPNext 集成由 `ERPNext HD Settings.enabled` 控制，包含客户映射与部分字段同步；事件代码还涉及关联记录的更名、合并和删除。[同步设置与映射](https://github.com/frappe/helpdesk/blob/v16.1.0/helpdesk/integrations/erpnext/utils.py)、[ERPNext 客户事件处理](https://github.com/frappe/helpdesk/blob/v16.1.0/helpdesk/integrations/erpnext/customer.py)

引入时要增加共享实体映射、服务项关联及客服可见范围，并明确客户资料的维护方；不能仅打开同步就视为解决重复客户问题。

## Frappe HR / HRMS

官方覆盖员工生命周期、请假考勤、报销、绩效、薪酬等业务；报销等流程能与 ERPNext 会计集成。[v16.53.2 官方说明](https://github.com/frappe/hrms/blob/v16.53.2/README.md)

建议分开保存两类事实：BizBase 保存某人在哪个期间负责哪些服务、完成哪些贡献、应计哪些销售或运营分成；HRMS 若引入，负责员工与人事薪酬流程。员工档案与登录用户建立关联，业务应用按需使用最少字段；客户和运营看板不应因此读取薪酬等人事信息。

“支持绩效和工资”不能推导成“内置本公司的 GEO 提成方案”。首期应从任职、贡献、费用和验收事实开始积累；规则明确后实现计算、审核与调整，再决定怎样交接 HRMS。当前未核验任何地区的完整薪税适配，不作相关承诺。

## 固定版本与安装边界

本轮按既有候选 tag 复核，没有将它们重新宣称为最新版本。当前基线为 Frappe 16.56.0、ERPNext 16.55.0、CRM 16.0.4；下列声明仅证明框架版本范围符合，**未证明本地全部依赖可以共存或业务权限验收通过**。

| 候选版本 | 官方依赖声明 | 对当前部署的影响 |
|---|---|---|
| Insights `v3.15.1` | `frappe >=15.0.0,<17.0.0`；Pandas、DuckDB、Ibis、SQLAlchemy 等依赖。[声明](https://github.com/frappe/insights/blob/v3.15.1/pyproject.toml) | 新增分析查询、数据导入、缓存及依赖组合；实际资源消耗须按报表和数据量测量 |
| Wiki `v3.5.0` | `frappe >=15.0.0,<=17.0.0-dev`；Markdown 库和 DuckDB。[声明](https://github.com/frappe/wiki/blob/v3.5.0/pyproject.toml) | 增加文档、搜索、附件与维护入口 |
| Helpdesk `v16.1.0` | `frappe >=16.0.0,<17.0.0`，`telephony >=0.0.1,<1.0.0`。[声明](https://github.com/frappe/helpdesk/blob/v16.1.0/pyproject.toml) | Telephony 是该 tag 的安装依赖，具体版本需另核验；不据其他分支文档预装 Studio 或更换搜索服务 |
| HRMS `v16.53.2` | 同时要求 `frappe`、`erpnext >=16.50.0,<17.0.0`。[声明](https://github.com/frappe/hrms/blob/v16.53.2/pyproject.toml) | 当前基线满足声明范围，仍需验证角色、人事数据隔离与组合升级 |

本轮先查询 Context7 的 `/frappe/frappe/__branch__version-16`。其权限文档确认 `permission_query_conditions` 和 `has_permission` 等扩展入口；具体应用能力与依赖使用以上固定 tag 源码核对。[Frappe v16 hooks](https://github.com/frappe/frappe/blob/version-16/hooks.md)

该顺序不妨碍后续逐步引入官方 App：先把共同数据和真实业务动作做实，再让 App 承担明确的一项职责。
