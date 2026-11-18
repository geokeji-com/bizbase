# BizBase 定位与官方应用选择

日期：2026-11-17。依据公司实际 GEO 业务介绍、已阅读的运营手册、补充 SOP，以及本轮官方资料复核。本文是选型与建设建议；没有安装新增 App、开启集成或迁移业务数据。

## 1. 项目定位

**BizBase 是公司级的业务数据与能力底座，以 GEO 为第一条落地业务线。** 它提供共享业务对象、权限、确定的业务动作和可追溯事实，让销售、运营、客户看板及独立开发的系统使用同一套业务依据。

公司允许重复界面和不同工作方式。应用的选择依据是：能否承担清晰职责、接入共同身份与权限、解决实际问题，并有维护责任人。功能重复本身不构成否决条件。

首期采用一个业务 Site，安装 Frappe、ERPNext、CRM 和自研 BizBase App。开发、测试、生产仍应使用各自环境；“一个业务 Site”不表示把测试数据混入生产。多个 App 共用站点数据库，但各专业对象和权限语义仍需关联、配置与验证。

2026-11-17 本轮只读执行 `bench --site frontend list-apps`，当前本地安装为：

| 项目 | 已安装版本 |
| --- | --- |
| Frappe | 16.56.0 |
| ERPNext | 16.55.0 |
| CRM | 16.0.4 |

BizBase 领域 App 尚未创建、安装；当前仓库主要承载部署与方案。原生 App 使用框架扩展点，独立系统通过受控 API 接入，RPA、AI 推理和已有采集/投放执行器保留独立运行位置。Frappe 已提供 DocType REST API，不需要在 BizBase 中逐一重写 ERP/CRM 的增删改查；跨应用业务动作和公司特有规则再由 BizBase 扩展。[Frappe REST API](https://docs.frappe.io/framework/user/en/api/rest)、[原生 App 扩展结构](https://docs.frappe.io/framework/user/en/tutorial/create-an-app)

## 2. 自研 App 负责的三组能力

| 模块 | 首要职责 | 与现成 App 的关系 |
| --- | --- | --- |
| 公共业务 | 组织/品牌/产品身份及外部 ID 映射；签约方、渠道、被服务方关系；服务项、范围版本、确认、任职和授权 | CRM 继续管理销售记录，ERP 管理交易档案；共同实体只保存共享身份，不再复制完整客户档案 |
| GEO 业务 | 拓词依据、问句与词包、采样条件/频率、回答与截图/分享证据、信源、别名与竞品版本、指标及报告快照、内容版本、投放回执/回链和费用事实 | 原生表单、任务、工作流作为承载工具；既有采集/分析/生文/投放系统通过接口提交和消费事实 |
| 集成与治理 | 多渠道线索接入、保留已有分配、业务幂等、权限检查、审计、可靠通知与对账；对外业务接口 | 能直接复用的原生 API 按授权开放；公司统一业务动作调用既有能力并补充规则，规则同样作用于原生写入路径 |

SOP 落地为服务产品适用的模板、关键节点、确认对象与版本、证据和时间规则。Wiki 保存可读说明，Learning 保存培训记录，Helpdesk 保存客户请求；这些都不能替代“某客户确认了哪个版本的词包/母稿”这一业务事实。

对后续业务线，首先复用主体、服务、权限和接入机制；GEO 的 Top 判定、探针参数、信源和文章投放留在 GEO 模块中，不扩散为所有业务的通用必填项。详细模型和分期见[整体方案](2026-11-17-bizbase-overall-plan.md)。

## 3. 原有 13 项逐项结论

此前的清单是 **13 项评估对象，包含 Frappe 框架本身**；并不表示 13 项都通过选型或都应安装。下表是结合完整业务后的推荐，安装时点由实际需求触发。

| # | 官方项目 | 当前建议 | 对本公司的价值与理由 |
| --- | --- | --- | --- |
| 1 | Frappe Framework | 保留，基础必需 | 提供数据模型、用户、基础权限、接口、任务和管理界面；公司授权和业务规则在自研 App 扩展。[官方说明](https://docs.frappe.io/framework/user/en/introduction) |
| 2 | ERPNext | 保留，按流程启用 | 复用客户交易档案、合同、报价、订单、供应商、项目/任务和费用/账务能力；不需要另开发 ERP。服务范围与考核规则由 BizBase 关联。正式财务是否迁入另行决定。[固定版 README](https://github.com/frappe/erpnext/blob/v16.55.0/README.md)、[业务边界](../research/2026-11-17-business-apps-boundary.md) |
| 3 | Frappe CRM | 保留，作为销售入口 | 线索、商机和跟进匹配销售流程；多渠道触达、去重、已有分配、诊断交接再扩展。官方 ERP 集成可复用，但不会自动解决渠道/终端客户身份。[官方集成](https://docs.frappe.io/crm/erpnext) |
| 4 | Insights | 下一批优先试评，当前不必装 | 适合经营分析，例如服务收入与投放成本、客户/项目表现、销售漏斗。先统一指标和费用归属，再验证只读看板；复杂客户证据穿透和服务授权仍由 BizBase 定义。[官方固定版](https://github.com/frappe/insights/blob/v3.15.1/README.md) |
| 5 | Wiki | 暂缓；明确迁移需求再装 | 能承载 SOP、术语和 API 文档。现有运营手册与仓库文档已经存在，先确定维护与发布需要；客户事实、材料授权、确认结果仍用结构化业务记录。[官方固定版](https://github.com/frappe/wiki/blob/v3.5.0/README.md) |
| 6 | Helpdesk | 有正式工单需求再装 | 适合客户反馈、投诉、异常、处理分派与 SLA。当前交付 SOP 先用 ERP 任务加 BizBase 节点；换词、暂停、母稿确认需关联业务记录，不能只记一张工单。其客户对象也需映射。[官方固定版](https://github.com/frappe/helpdesk/blob/v16.1.0/README.md) |
| 7 | Frappe HR / HRMS | 人事薪酬需求启动后再装 | 员工、考勤、请假、报销与工资有现成能力。销售/运营分成涉及回款、达标、成本、任职时间和规则版本，需要先在 BizBase/ERP 形成依据；HRMS 可承接经确认的工资结果。[官方固定版](https://github.com/frappe/hrms/blob/v16.53.2/README.md) |
| 8 | Raven | 暂缓 | 提供业务环境内的聊天、频道、通知和机器人。如果现有沟通工具已够用，当前先把确认和交接转成业务记录；引入 Raven 不会自动接通外部客户群，也不会自动统一数据授权。[官方固定版](https://github.com/frappe/raven/blob/v3.2.0/README.md) |
| 9 | Builder | 六品牌官网需要统一可视化维护时试点 | 适合运营自己制作落地页、官网和可发布内容页。已有官网可先接线索 API；采用 Builder 的价值来自页面维护方式。公开内容与私有客户/服务数据必须有清晰发布边界。[官方固定版](https://github.com/frappe/builder/blob/v1.39.0/README.md) |
| 10 | Learning / LMS | 培训需要留痕和考核时再装 | 可将 SOP 做成课程、测验、作业和培训记录，适合新人能力培养。实际客户项目是否完成、是否获得确认，继续以业务记录为准。[官方固定版](https://github.com/frappe/lms/blob/v16.1.1/README.md) |
| 11 | Gameplan | 暂缓 | 适合异步讨论、团队/项目协作；其项目任务有自己的模型。当前先让 ERP 执行任务关联 GEO 服务，日后确有异步协作需求再决定映射，避免增加一套无人维护的项目身份。[官方固定版](https://github.com/frappe/gameplan/blob/v0.1.33/README.md) |
| 12 | 独立 Drive | 不建议新装 | 官方独立仓库已归档，产品迁入 Suite。客户材料和采集截图先使用已有私有文件能力及按规模增加的证据存储，不以旧 Drive 作为新部署起点。[官方仓库说明](https://github.com/frappe/drive) |
| 13 | Suite | 当前不建议作为业务底座依赖 | 官方仓库仍标 WIP，涵盖文档、网盘、表格、会议、邮件等较大范围；目前没有核实到可推荐的稳定 release。并有独立产品共存/迁移限制。当前没有完整办公套件替换需求。[官方仓库](https://github.com/frappe/suite) |

这里的“暂缓”表示当前投入收益和接入条件不成立，不代表产品质量否定。前一轮将 Wiki 列为优先试评；在确认已有成体系手册之后，现降为按文档迁移需求引入。Insights 仍是首个值得验证的新增官方应用，但先用一个真实经营问题判断原生报表是否已经足够。

## 4. 原 13 项之外的补充判断

| 项目 | 当前建议及理由 |
| --- | --- |
| Print Designer | 不另装。官方已声明停止维护，并推荐 Frappe 16 内置 Print Format Editor；先用内置能力处理报价、确认单等版式。GEO 指标计算与历史报告仍由业务模型负责。[官方维护说明](https://github.com/frappe/print_designer/blob/70e40eae9d4c70dcc6d9d29b150327004419b64a/README.md) |
| Studio | 仅考虑隔离试验。与可视化、AI 辅助搭应用相关，但官方明确仍很早期、暂不建议生产使用；BizBase 的数据契约不依赖它。[官方状态说明](https://github.com/frappe/studio/blob/5b9d70a5582ed55058f8d4962a7c9b7d3c3d8489/README.md) |
| Webshop | 当前不装。官网当前负责内容与留资，服务还要经过诊断、协商和签约；未来出现标准套餐自助下单需求再评估购物车等能力。[官方功能](https://github.com/frappe/webshop/blob/develop/README.md) |
| Telephony | 按所选 App 依赖或明确电话供应商需求引入。官方当前列出 Twilio/Exotel，不能当作现成的中国 400、活码或社媒线索连接器。[官方接口范围](https://github.com/frappe/telephony/blob/9447577500a25d242088398157b72c654fa34b20/README.md) |
| Payments | 按所选 App 依赖或真实在线收款需求引入。支付网关不能替代公司分成算法、投放成本归属及供应商结算规则。[官方功能](https://github.com/frappe/payments/blob/develop/README.md) |

这是相关候选的补查，并非对所有官方垂直行业应用的穷尽评估。没有发现当前共享业务底座必须补装的新 App。

## 5. 选择顺序与边界

1. **现在：新增官方业务 App 为 0，自研 BizBase App 为 1。** 先复用已装 ERP/CRM 与框架能力，明确主体/服务/范围/确认/权限和 API 契约，接通一个采集来源和一个报告消费者。
2. **有真实分析需求后：先试 Insights。** 使用已有、口径明确的数据验证一份经营报表，同时验证客户、渠道、内部人员的数据范围。BI 只消费业务事实，不能替代原始证据、指标规则与报告快照。
3. **按具体痛点引入 Builder、Learning 或 Helpdesk。** 分别对应六品牌官网的可视化维护、员工培训考核、客户服务请求管理，彼此没有必须先后安装的依赖。
4. **管理流程正式扩展后再评 HRMS、Wiki、Raven、Gameplan。** 安装之前明确业务负责人、来源数据、更新责任、权限边界与现有系统如何衔接。

采集、生成和投放程序先接入统一事实与接口，再按维护收益决定是否迁入自研 App。底座保存执行请求、版本、结果与费用，不要求所有执行代码迁入同一进程。品牌官网数量、独立应用数量，也不决定必须创建相同数量的 Frappe Site。

## 6. 版本、依赖与验证说明

“官方”“功能适用”“依赖版本满足”“在当前组合运行正常”是四个不同判断。此前锁定的候选及本轮复核资料见[原始评估](../research/2026-11-17-frappe-apps-assessment.md)。本轮没有进行新增应用的组合安装或负载测试，不承诺未经实测的内存占用。

当前候选 Helpdesk 需要 Telephony，Learning 需要 Payments；这些属于所选版本的依赖，不表示公司现在要同时上线电话系统或付费课程。不能照搬其他分支的依赖，也不能把声明兼容视为试装通过。

同 Site 可复用基础服务，但额外 App 仍会增加依赖、表/索引、后台任务、权限对象和升级组合。若选择安装，应固定实际版本及依赖，在隔离环境验证原有 ERP/CRM 正常、数据映射与业务权限正常、相关任务和文件可恢复。需要隔离的 BI 或办公协作也不必强行安装到核心业务 Site。

本轮分项证据：

- [Insights / Wiki / Helpdesk / HRMS](../research/2026-11-17-apps-data-support-recheck.md)
- [Raven / Builder / Learning / Gameplan](../research/2026-11-17-apps-collaboration-recheck.md)
- [Drive / Suite 与清单外候选](../research/2026-11-17-apps-suite-catalog-recheck.md)

以上报告保留官方事实与对本项目的判断边界；本文件作为当前选型入口，整体模型继续以[整体方案](2026-11-17-bizbase-overall-plan.md)为准。
