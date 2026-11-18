# Frappe Framework 在 BizBase 中的能力边界

核查日期：2026-11-17。目标版本：Frappe `v16.56.0`；ERPNext 与 CRM 的业务对象另行评估。本文区分官方能力、工程建议和待验证事项，不表示功能已经在 BizBase 实现。

已先调用 Context7 的 `resolve_library_id` 查询 Frappe Framework，但工具返回 `fetch failed`，未取得库 ID，因此无法继续版本化文档查询。随后读取官方文档，并用 Frappe `v16.56.0` tag 源码补证关键行为。通用文档可能跨版本，实施前仍须在实际安装版本验证。

## 结论

Frappe 适合承载 BizBase 的业务主数据、权限、审批、管理后台与公共业务 API。原始高频采样、RPA 执行、重型分析、媒体投放适配和可靠集成需要独立设计，不能因框架有 DocType、队列和 Webhook 就认定业务底座已经完成。建议先用自定义 App 实现明确的业务边界，复用已有执行系统，不先拆成大量微服务。

## 1. 数据与应用扩展

| 能力 | 官方已有 | BizBase 需要做 |
|---|---|---|
| DocType、字段、表单、列表、ORM | DocType 描述模型与视图，普通 DocType 对应数据库表，可生成 Desk 表单与列表 | 自研组织、服务范围、事实、指标版本等领域对象及校验；明确哪个对象由谁维护 |
| Link、Table/Child DocType | 提供对象关联和依附父记录的子表 | 有独立生命周期、权限、外部 ID 或高频更新的数据应建独立对象，不放在一个客户记录的大子表里 |
| Custom App | 有标准 App 目录、hooks、patches、代码与资源组织 | 将业务规则、迁移和默认配置纳入版本管理；关键不变量放服务端 Controller/领域方法 |
| 标准对象扩展 | v16 文档支持 `extend_doctype_class` | 必要时扩展现有对象，避免直接修改上游核心源码；扩展冲突和升级行为须测试 |

来源：[DocType](https://docs.frappe.io/framework/user/en/basics/doctypes)、[子表](https://docs.frappe.io/framework/user/en/basics/doctypes/child-doctype)、[创建 App](https://docs.frappe.io/framework/user/en/tutorial/create-an-app)、[扩展钩子](https://docs.frappe.io/framework/user/en/python-api/hooks#extend-doctype-class)。

**设计判断：** 把合同条目的静态小明细放子表可行；有单独 ID、可能跨多个服务复用的问句、事实、内容、发布记录应优先独立建模。该选择是业务边界判断，不是框架限制所有明细都必须独立。

## 2. 权限可复用基础，服务范围授权需要开发

官方提供 User、Role、DocType 权限、字段权限级别、User Permissions、分享及导出等权限类型。User Permissions 可以按 Link 字段关联值限制记录。适合配置销售、运营、财务、客户等基础操作权限。[官方权限说明](https://docs.frappe.io/framework/user/en/basics/users-and-permissions)

自定义范围有两类主要扩展点：列表查询的 `permission_query_conditions`，以及文档的 `has_permission`。官方特别说明前者作用于 `get_list`，不作用于 `get_all`。Frappe 源码还将角色、用户、所有者、共享及子文档父权限等组合判定。[权限钩子](https://docs.frappe.io/framework/user/en/python-api/hooks#modify-list-query)、[v16.56.0 permissions.py](https://github.com/frappe/frappe/blob/v16.56.0/frappe/permissions.py)

**BizBase 自研范围：** 授权主体（人或应用）、服务范围、业务动作、有效期、授权依据；同一组织的不同合同/品牌是否互通、渠道可见哪些终端服务、客户能否导出等均由明确规则决定。组织树不能自动当作授权树。

实现时统一复用权限判定方法，并覆盖列表、详情、搜索、报表、导出、附件、后台任务和自定义 API。隐藏菜单只改变入口；服务端仍需判权。自定义 SQL、`get_all`、`ignore_permissions` 等路径不能假设会自动继承全部策略。

## 3. REST、RPC、OAuth 是接入基础，不是完整业务契约

Frappe 自动提供 DocType REST CRUD，支持调用白名单 Python 方法。API key/secret 归属于一个 User，请求按该用户执行；支持 Bearer token。Frappe 也可作为 OAuth 服务供第三方应用登录。[REST API](https://docs.frappe.io/framework/user/en/api/rest)、[OAuth 服务](https://docs.frappe.io/framework/user/en/using_frappe_as_oauth_service)

`v16.56.0` 认证源码显示 OAuth Bearer 与 API key 认证会设置当前请求用户。**统一身份认证并不自动表达“某应用只允许替某人执行某服务的某动作”**；具体应用授权仍需 BizBase 设计。[认证源码](https://github.com/frappe/frappe/blob/v16.56.0/frappe/auth.py)

建议的接口分工：

- 常规主数据读取可复用受权限约束的 REST；关键操作开放稳定业务方法，例如确认范围、暂停服务、提交采样结果、发布报告版本、接收投放回执。
- 用户操作保留真实用户身份；后台集成使用最小权限服务身份，不能给所有 AI 应用共用 Administrator key。
- API 契约补充应用标识、资源范围、幂等键、外部 ID、版本、关联请求 ID、分页和错误语义；平台生成的 CRUD 不能替代这些约束。
- 不信任客户端任意填写的“操作人”或“客户 ID”；必须由认证与授权信息核验。
- 现有身份系统可作为身份来源，Frappe 与它的映射、登出/停用同步、令牌续期和应用授权需要实际 PoC。当前无需认定必须替换现有 SSO。

## 4. Workflow、修改日志与业务版本分别使用

Workflow 支持状态、角色、条件和多级审批，会改变普通保存/提交过程；提交类文档仍有 Draft/Submitted/Cancelled 的底层状态。它适合审批词包变更、暂停申请、预算或内容发布申请。[Workflow](https://docs.frappe.io/erpnext/workflows)、[v16.56.0 workflow.py](https://github.com/frappe/frappe/blob/v16.56.0/frappe/model/workflow.py)

Frappe `Version` 的核心内容是记录文档变更差异，并关联记录类型及 ID。**修改历史并不等于一份可供合同验收、报告复算引用的业务版本。** 服务范围、竞品集合、别名规则、事实基准、分析策略、内容及报告仍应有显式版本、确认状态、生效区间与不可静默改写的历史引用。[Version 源码](https://github.com/frappe/frappe/blob/v16.56.0/frappe/core/doctype/version/version.py)

Workflow 可以承接审批状态；外部客户确认、授权确认人、消息/截图证据以及期限影响需要业务对象补充。审批通过不自动说明客户已确认，也不自动执行暂停顺延等业务计算。

## 5. 队列与定时器可复用，执行控制与业务幂等需要开发

框架提供 `frappe.enqueue`、默认及自定义队列、worker 和 scheduler/cron；可在事务提交后入队。官方说明 scheduler 触发任务默认按 Administrator 执行，不能依靠浏览器会话来保护每个计划任务。[后台任务](https://docs.frappe.io/framework/user/en/api/background_jobs)

`v16.56.0` 使用 Redis/RQ；`deduplicate=True` 配合 `job_id` 只防止同一任务已排队或运行时再次入队，任务完成后可再次执行。`enqueue_after_commit` 是提交后回调，不是业务状态与外部消息队列之间的原子提交协议。[v16.56.0 background_jobs.py](https://github.com/frappe/frappe/blob/v16.56.0/frappe/utils/background_jobs.py)

**工程建议：** Frappe 先承担服务调度控制、轻量校验、通知和集成编排；RPA 设备/浏览器实例、长时间会话、模型推理及批量分析继续由独立 worker/已有执行服务承担。平台保存计划、尝试、执行状态与证据引用。采集时间窗、随机/均匀调度、漏采补采、并发限额、租约/心跳、重试及暂停策略属于自研。实际吞吐量需用业务样本压测，不能从默认队列数量推断。

## 6. Webhook 可做通知，关键数据同步要可靠交付

官方 Webhook 支持按文档事件和条件发请求、模板化数据与 HMAC 签名。`v16.56.0` 源码有最多三次发送尝试及请求日志。[Webhook 文档](https://docs.frappe.io/framework/user/en/guides/integration/webhooks)、[对应源码](https://github.com/frappe/frappe/blob/v16.56.0/frappe/integrations/doctype/webhook/webhook.py)

这些能力不等于接收方 exactly-once，也未替 BizBase 提供跨系统业务对账。关键同步建议开发持久事件发件箱和收件记录：业务变更与待发送事件同事务保存；事件 ID 稳定；接收方按业务幂等键去重；失败可重试、人工重放；有状态查询和定期对账。订单超时不能盲目重新发文，先查询供应商受理状态。

一期可以在同一自定义 App 中实现发件箱、幂等表和重试任务，不需为了形式先引入独立消息中间件。

## 7. 文件与高体量数据分层

Frappe 现有 File/附件可关联文档，并支持外部链接；私有附件依赖相应权限。官方明确没有“新上传自动存 S3/GCS”的内置开关，默认本地磁盘；社区 S3 App 兼容性不由官方保证。[附件](https://docs.frappe.io/framework/user/en/desk/attachments)、[官方 S3 说明](https://docs.frappe.io/framework/help/can-i-store-my-files-on-s3-gcs-or-google-drive-instead-of-the-server)

对应版本源码含 `write_file` 等扩展钩子，默认回落到站点文件系统。这证明可以开发适配层，不等于项目已具备对象存储或其权限闭环。[v16.56.0 File 源码](https://github.com/frappe/frappe/blob/v16.56.0/frappe/core/doctype/file/file.py)

**推荐分层是工程建议：**

| 数据 | 初期承载方式 | 升级条件 |
|---|---|---|
| 组织、服务、范围/规则版本、授权、交付、费用关系 | Frappe DocType/当前事务数据库 | 根据真实慢查询和数据规模优化，不提前分库 |
| 原始回答与引用明细 | 先接已有采集存储，统一 ID 与受控 API；小规模新增明细可先用独立 DocType | 写入量、保留期、聚合延迟和备份成本证明需要时再拆分析存储 |
| 截图、原始载荷、大文档、导出文件 | 文件服务/对象存储适配；Frappe 存受控资产标识、归属和摘要 | 上线前核查鉴权、短期下载链接、留存及恢复 |
| 报表汇总与搜索索引 | 由原始证据和明确版本生成的可重建读模型 | 报表负载影响事务业务时独立扩展 |

统一数据源意味着身份、维护权、业务语义和访问契约统一，不要求所有字节放在同一数据库。外部对象链接不能仅以知道 URL 为访问依据；需要与服务授权一致。

## 8. 上线前必须完成的验证

1. 建立两家公司、渠道和多个服务的合成权限场景，验证列表/详情/导出/附件/API/后台执行的授权一致性；权限撤销后再次请求不可访问。
2. 一个关键业务动作通过 Desk 和外部应用分别执行，规则、审计主体和结果相同，不能从通用 CRUD 绕过确认或生效规则。
3. 数据变更提交后模拟消息发送失败、接收成功但回执丢失、重复回调；最终只产生一次业务结果并可对账。
4. 换词、竞品或事实规则更新后，旧报告仍引用旧版本；明确复算生成新结果，不覆盖旧结果。
5. 用真实数量级的合成载荷验证采样入库、并发回调、报表查询与附件访问；性能结论以测量为准。
6. 验证自定义 App 在实际 Frappe/ERPNext/CRM 版本上安装、迁移、备份恢复与升级；本研究未执行这些测试。

以上是面向上线的验收要求，本轮只进行文档和源码核查，没有安装 App、改配置或运行生产任务。
