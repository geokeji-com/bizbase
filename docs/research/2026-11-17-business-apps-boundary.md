# ERPNext 与 Frappe CRM 在 BizBase 中的职责边界

调研日期：2026-11-17。基线为仓库已记录的 Frappe 16.56.0、ERPNext 16.55.0、CRM 16.0.4；本轮只核对官方文档和固定 tag 源码，没有启用集成、迁移数据或修改运行权限。以下区分官方能力与 BizBase 设计建议。

## 1. 结论

保留 Frappe CRM 承担销售线索与商机，保留 ERPNext 承担交易、采购和财务单据；BizBase 自研跨应用身份映射、服务范围及 GEO 专用业务。通过共同身份和受控业务动作连接它们。不能把安装在同一站点等同于共享一套客户和权限模型。

暂时没有为这一目标必须新增的官方 App。原生能力优先配置，业务差异放在自有 App 的可测试代码中；不要改 ERPNext/CRM 核心源码。

Context7 已查询 `/frappe/crm` 与 `/frappe/erpnext/__branch__version-16`。CRM 返回内容主要来自 develop，ERP 查询还混入历史建议页面，因此以下关键集成结论以 `crm/v16.0.4`、`erpnext/v16.55.0` 固定源码补核。官方在线文档用于说明功能，不能保证每项新文档行为都已在本机验收。

## 2. 现成、配置与自研的分工

| 业务 | 可复用的现成能力 | 配置/扩展 | 需要自研或接入的部分 |
| --- | --- | --- | --- |
| 销售线索、跟进、商机 | Frappe CRM 的 Lead、Deal、Organization、Contact、任务及活动界面 | 阶段、字段、分配规则、销售权限 | 中国平台线索接入、原始触达事件、跨入口防重、已有分配保留、归属冲突与历史贡献 |
| 共享主体 | CRM Organization、ERP Customer/Supplier 等专业档案 | 外部系统 ID 与共同主体 ID 字段、映射及审核 | 共同主体识别、别名/更名/合并、渠道与被服务方关系；统一写入责任 |
| 报价、交易订单 | ERPNext Quotation、Sales Order、Item、价格表 | 将可售服务配置为非库存 Item；报价审批、合同/服务关联 | GEO 范围、指标规则和报价影响因素的结构化；不能把一个问句当一个库存品 |
| 合同档案 | ERPNext Contract 的期限、签署、条款、履约事项及单据引用 | 附件、补充约定、服务实例关联 | 服务范围生效版本、目标和考核窗、暂停恢复影响、变更确认及权益处理 |
| 项目与人工任务 | ERPNext Project、Task、Project Template、Timesheet | 项目模板、人员、阶段任务、工时成本；关联 BizBase 服务 | 业务里程碑事实、客户确认、交接、验收、变更影响；采集执行不是人工 Task 的同义词 |
| 媒体供应商与采购 | Supplier、采购订单、Purchase Invoice、Payment Entry | 媒体服务品项、科目、项目或业务维度、审批 | 聚合平台 API、订单明细/回调、回链、超时待确认、防重复下单、退款和业务费用归属 |
| 收款与经营账 | Sales Invoice、Payment Entry、Journal Entry、Cost Center、Accounting Dimension | 科目、税、币种、付款条件、核算维度和对账 | 业务事件至财务单据的映射、跨服务费用分摊、经营口径；中国本地财税接入另评估 |
| 销售贡献与分成 | Sales Person、Sales Team 贡献比例、Sales Partner 佣金字段及报表 | 人员/渠道档案、确认后的简单比例 | 回款/达标/利润触发、运营分成、任职有效期、退款冲回、规则版本与结算快照 |
| GEO 核心数据 | Frappe 提供承载机制，不自带本公司的领域模型 | 自有 DocType、表单、权限、工作流 | 品牌产品、词包、采样计划/证据、两类竞品、事实核验、指标版本、内容版本、发布与引用匹配 |

现成能力的证据：[CRM 组织](https://docs.frappe.io/crm/organization)、[CRM 联系人](https://docs.frappe.io/crm/contact)、[服务 Item](https://docs.frappe.io/erpnext/item)、[Contract](https://docs.frappe.io/erpnext/contract)、[Project](https://docs.frappe.io/erpnext/project)、[采购单据](https://docs.frappe.io/erpnext/purchase-invoice)、[付款单据](https://docs.frappe.io/erpnext/payment-entry)。表中“需要自研”是针对 BizBase 需求的设计判断，不是对所有官方插件作穷尽性否定。

## 3. CRM 与 ERPNext 官方集成能做什么

官方集成需要显式配置，可以同站点或跨站点运行。同站点可从 Deal 打开预填 Quotation；没有 Customer 时可向 CRM Deal 报价；跨站点使用 Prospect。可配置 Deal 达到指定状态时创建 Customer，同站点的 Deal 报价转 Sales Order 也有创建/复用 Customer 路径。联系人和地址随流程关联。商品同步主要面向我方可售产品，ERPNext Item 是其基准，可选反向同步。[官方集成说明](https://docs.frappe.io/crm/erpnext)

固定版本源码确认以上 Customer/Quotation 路径；同时存在以下具体限制：

- Deal 与 Customer 的关联由专用字段记录，不是 CRM Organization 与 Customer 天然同一条记录。
- ERPNext 的创建函数按 `customer_name` 查已有 Customer；联系人按邮箱或手机号查已有记录。它们不是稳定的法人身份识别规则，不能直接承担复杂主体合并。
- 跨站点调用使用配置的 API 用户，其权限语义与同站点当前用户路径不同。
- 启用集成会创建自定义字段、属性设置和表单脚本；该 CRM tag 还可能为 Sales User、Sales Manager 添加 Item 权限。配置前需比较角色权限变化。

来源：[CRM v16.0.4 集成实现](https://github.com/frappe/crm/blob/v16.0.4/crm/fcrm/doctype/erpnext_crm_settings/erpnext_crm_settings.py)、[ERPNext v16.55.0 接收端](https://github.com/frappe/erpnext/blob/v16.55.0/erpnext/crm/frappe_crm_api.py)。

建议先用隔离测试数据验证标准流程，再由 BizBase 在转交易前完成主体匹配；有歧义进入人工核对，不仅凭名称创建/合并。默认关闭商品双向修改，明确谁维护我方服务目录。集成启用不能同时自动授权所有销售修改所有商品。

## 4. 推荐的数据归属

以下为方案建议，不是当前已经配置的状态。

| 数据概念 | 权威维护位置 | 其他应用的角色 |
| --- | --- | --- |
| 跨系统组织身份、名称标识和关系 | BizBase 共同主体登记及身份解析接口 | CRM Organization、ERP Customer/Supplier 等绑定共同 ID；提交身份变更需走同一规则 |
| 销售阶段、跟进、成交预测、商机负责人 | Frappe CRM | BizBase 读取销售事实并衔接诊断、合同和服务，不再建第二套销售流水 |
| 外部联系人基本档案 | 优先复用同站点 `Contact` | 增加共同标识和任职/授权关系；客户确认权限并不由“是联系人”自动获得 |
| 我方销售服务目录与价格 | ERPNext Item / Item Price | CRM Product 用于销售选择；GEO 优化标的另建品牌/产品身份 |
| 交易 Customer、Supplier、账务字段 | ERPNext | BizBase 只关联交易账户；账务地址/税务字段由指定财务维护，不让各端随意回写 |
| 合同文件与签署/交易信息 | 优先复用 ERPNext Contract 及交易单据 | BizBase 保存结构化服务条款与范围版本，关联明确合同/补充约定版本 |
| 服务对象、范围、证据、指标和交付事实 | BizBase 自有模型 | CRM、项目页、客户看板和生成工具按权限读写同一事实 |
| 已确认会计分录及收付款 | ERPNext 或现有财务系统中明确选定的一方 | 业务费用记录与财务单据对账；不在两套系统同时人工维护相同总账 |

共同主体登记只承担跨业务稳定身份、权属关系和身份变更，不能再次复制整份 CRM/ERP 客户表。每个字段应有维护方、变更入口和投影方向。映射记录保存来源系统、对象类型、来源 ID、共同 ID 和确认状态；不能用显示名作为外部连接键。联系人邮箱或手机号相同仅作为匹配线索。

四个容易混用的概念需要明确：

1. ERPNext `Company` 表达需要独立账务的一方，适合我方经营/核算主体；不能把每一个外部客户公司都建为 ERP Company。[Company 定义](https://docs.frappe.io/erpnext/company-setup)
2. ERPNext `Item` 与 CRM `Product` 在销售集成中表达我方卖的商品/服务；客户被优化的产品、型号属于另一类实体。[Item 定义](https://docs.frappe.io/erpnext/item)
3. CRM `Organization` 是 B2B 销售组织视角；ERP `Customer` 是交易角色。一个渠道既可能是 Customer，也可能因收佣金而关联 Supplier；共同组织身份相同不代表角色或授权相同。
4. `Contact`、登录 `User`、内部人员任职分别表达联系人、账号和工作职责；不以客户联系人字段存本方运营负责人。

销售入口统一使用 Frappe CRM 的 `CRM Lead` / `CRM Deal`。ERPNext 自带 `Lead` / `Opportunity` 不并行开展同一销售流程；保留标准模块供依赖使用，通过工作区和角色配置减少入口重复。菜单隐藏只改变可见导航，数据权限还需单独验证。不能删除 ERP CRM 模块，因为 Contract 与集成代码等也位于该模块目录。[Contract 固定模型](https://github.com/frappe/erpnext/blob/v16.55.0/erpnext/crm/doctype/contract/contract.json)

## 5. Project、Contract、财务与分成的准确边界

### Project 承载执行，不定义全部服务

Project 适合人工任务、计划进度、工时和项目成本，可关联 Customer 与 Sales Order。其实际起止日期按关联 Timesheet 计算，因此不能直接用作服务开始或考核起点。建议为服务实例建立 Project 关联，用专门事件记录实际业务里程碑；不要把年度换词范围或品牌事实塞入任务备注。[官方 Project](https://docs.frappe.io/erpnext/project)、[固定版本实现](https://github.com/frappe/erpnext/blob/v16.55.0/erpnext/projects/doctype/project/project.py)

Contract 可保留期限、签署、文本条款、履约事项和单据引用；这并不自动实现 GEO 的词包生效版本、采样条件、分母规则、暂停影响和验收计算。应复用其合同档案能力，再关联 BizBase 服务及条款快照。[Contract 功能](https://docs.frappe.io/erpnext/contract)

### 财务单据与业务费用分别确认

ERPNext 的 Project、Cost Center 和自定义 Accounting Dimension 可帮助费用归属，但需要配置及账务校验。[核算维度](https://docs.frappe.io/erpnext/accounting-dimensions)

建议先确保每次投放有业务费用事实：供应商、订单明细、服务/周期、报价、受理、实发、实际收费、退款及凭证。随后由对账生成或关联财务单据；多次投放可按结算规则汇总，不必每一篇文章都等同一张发票。预充值余额、供应商扣费与正式应付确认也不能混作同一次支出。

本文没有验证中国税务开票、银行接口、当地法定报表或薪酬合规覆盖。ERPNext 的国际通用会计能力不能直接推导这些已经可用；先与现有财务系统对账，是否切换正式账由财务评估。Sales Invoice 也不能直接等同中国税务发票。

### 原生提成字段不是完整激励系统

Sales Person / Sales Team 可记录销售贡献；Sales Partner 可记录渠道佣金。官方说明这类经营数据不会自行形成工资、费用、应付款或支付。实际核算仍需规则与财务衔接。[Sales Person](https://docs.frappe.io/erpnext/sales-person)、[Sales Partner](https://docs.frappe.io/erpnext/sales-partner)

因此，GEO 的销售/运营分成应先保存任职有效期、参与事实、回款、费用与验收，再建立规则版本、计算快照、审批和冲回。简单比例可复用原生字段，达标/回款/利润混合条件应自研。不能把当前 owner 或 Task 完成数直接当作历史奖金归属。

## 6. 其他官方 App 的安装判断

沿用[官方应用评估](2026-11-17-frappe-apps-assessment.md)的固定版本核验，当前不增加安装范围：

- **Insights**：出现原生报表难以满足的分析需求再试评；指标定义与权限范围先确定，BI 不承担主数据统一。
- **Helpdesk**：有正式客户工单/SLA后再接入；其客户对象需映射，不能再产生独立客户源。
- **HRMS**：真正开展员工、考勤、报销、薪酬管理时引入；统一登录或记录运营职责无需先装它。
- **Wiki**：文档发布和维护需要时选用；现有手册与仓库文档可以先保留，SOP 与品牌事实库不是同一种数据。
- **Drive/Suite**：旧独立 Drive 的归档与 Suite 的版本状态见前述报告；没有必要为 GEO 事实附件先引入完整协作套件。

以上为当前方案的适用性判断。若后续决定安装，重新核验候选 release、依赖、同站点权限和资源负载，不将今天的版本快照长期当作最新状态。

## 7. 启用前的小范围验证

1. 同一组织有多个商机，其中一个成交；CRM 与 ERP 引用同一主体，其他商机不被重复迁移。
2. 名称相同但实际不同的两个组织、名称改变的同一组织、联系人同电话但跨组织任职，都不能错误合并或越权。
3. 渠道是签约方，被服务组织是其客户；ERP Customer 指向交易方，服务范围与看板权限指向获准对象。
4. Deal→Quotation→Sales Order→Customer 的重试、已有客户关联和失败补偿通过；没有重复创建或静默改名。
5. 启用集成前后比较角色权限，验证销售可做所需报价，不能超出既定商品/客户范围。
6. 两个应用操作同一服务后，人物、费用与交易关系一致；正式财务结果仍由确定的账务来源维护。

这些是后续实施的验收建议，本轮没有执行这些测试。
