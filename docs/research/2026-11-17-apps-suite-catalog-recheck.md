# Drive、Suite 与原 13 项之外的官方应用复核

复核日期：2026-11-17。结合已明确的 GEO 服务链、运营手册和补充 SOP，复核原清单中的 Drive / Suite，并补查少数相关官方项目。本文只做选型，不安装应用、不修改运行服务、不迁移数据。

## 结论

- **独立 Drive：不建议新安装。** 官方已将产品并入 Suite，并归档独立仓库。
- **Suite：当前不建议安装到 BizBase 业务 Site。** 官方仍标 WIP，尚未取得可推荐的稳定 release 证据；它解决完整办公协作套件问题，明显超出当前共享业务数据底座的必要范围。
- 原 13 项之外，**没有发现当前必须补装的官方 App**。Print Designer 应优先改用 Frappe 16 内置编辑器；Studio 暂只值得隔离试验；Webshop 与当前销售模式不匹配；Telephony / Payments 应按所选业务 App 的实际依赖和真实集成需求引入。

## 原清单中的两项

| App | 官方事实 | 当前建议及业务理由 |
| --- | --- | --- |
| 独立 Drive | 官方仓库在 2026-11-10 归档，说明已并入 Suite。[仓库状态](https://github.com/frappe/drive) | **不新装。** 客户资料、截图、报告和投放回链需要可追溯的文件关联与权限，但不因此要求部署一个已归档的网盘产品。先在 BizBase 定义文件对应客户、服务、版本与证据的关系，存储按规模选择；文件管理界面可后续独立评估。 |
| Suite | 官方仓库描述仍含 WIP；本次 `releases/latest` 请求返回 404，不能据此认定已有适合生产的稳定版。[仓库](https://github.com/frappe/suite)、[release API](https://api.github.com/repos/frappe/suite/releases/latest) | **当前不装，后续按办公协作替换需求评估。** 公司眼前的问题是共享业务事实、权限与 GEO 规则；安装办公套件不会自动统一客户、服务、问句与成本。若以后明确要自托管网盘、文档、表格、演示、会议和邮件，再独立规划。 |

Suite 本次核验的源码位置是 `292c41ca407039be202a239f6a5d4e69629d9a6f`。它包含 Drive、Writer、Sheets、Slides、Meet、Mail、Calendar 七个产品。官方明确其模块和 DocType 与对应独立 App 冲突，因此不能与这些独立 App 直接共装；该声明**不等于 Suite 与 ERPNext / CRM 有已知冲突**。[固定源码说明](https://github.com/frappe/suite/blob/292c41ca407039be202a239f6a5d4e69629d9a6f/README.md)

依赖声明包含 `frappe >=16.0.0,<18.0.0`、Python `>=3.14,<3.15` 和 `ffmpeg`。会议和协同编辑涉及独立服务；邮件需要 JMAP 服务，账户及域名管理另有 Suite Cloud 体系。仅版本范围相符不足以证明整个应用组合通过验收，资源也不能按普通静态页面估计。[依赖声明](https://github.com/frappe/suite/blob/292c41ca407039be202a239f6a5d4e69629d9a6f/pyproject.toml)、[架构说明](https://github.com/frappe/suite/blob/292c41ca407039be202a239f6a5d4e69629d9a6f/README.md)

## 原 13 项以外值得说明的项目

下列项目是本次补充核对，不把它们混入原 13 项，也不作为新增安装清单。

| 项目 | 与 GEO 的可能关系 | 建议与边界 |
| --- | --- | --- |
| Print Designer | 报价、合同附件、服务确认单、报告打印版式 | **不另装。** 官方 README 宣告不再维护，并建议使用 Frappe 16 起内置的 Print Format Editor。已有打印能力值得用于业务单据，但不能代替 GEO 指标计算、历史报告快照或客户看板。[项目说明](https://github.com/frappe/print_designer/blob/70e40eae9d4c70dcc6d9d29b150327004419b64a/README.md)、[内置编辑器文档](https://docs.frappe.io/framework/user/en/printing/print-format-editor) |
| Studio | 可视化构建业务界面、连接 Frappe 数据源，支持 AI 辅助生成页面 | **暂不放进业务 Site，可独立试验。** 与人人搭应用的方向相关，但官方明确处于早期开发、存在破坏性变化与未完成功能，暂不建议生产使用。统一数据与权限应由 BizBase 后端提供，不能依赖界面生成工具保证。[固定源码说明](https://github.com/frappe/studio/blob/5b9d70a5582ed55058f8d4962a7c9b7d3c3d8489/README.md) |
| Webshop | 在线商品目录、购物车、下单和支付 | **当前不装。** 当前官网主要用于内容信源与获客，GEO 服务要经过诊断、协商范围和签约，不是已明确的标准商品自助购买流程。将来出现标准套餐自助下单再评估。[官方功能说明](https://github.com/frappe/webshop/blob/develop/README.md) |
| Telephony | 电话日志、来去电及与业务单据关联 | **不为现有 400 线索单独安装；按依赖或明确通话供应商需求引入。** 当前官方 README 明确列出 Twilio、Exotel，不能宣称安装后就自动接入中国 400、活码、抖音或小红书。当前电话供应商是否可接、回调格式与线索归属仍要实际核验。[官方接口范围](https://github.com/frappe/telephony/blob/9447577500a25d242088398157b72c654fa34b20/README.md) |
| Payments | 支付网关、付款链接与 Web Form 收款 | **不为分成或投放成本而安装；按依赖或收款需求引入。** 官方说明涵盖支付网关及网页收款；它并不因此提供本公司的销售/运营提成、贡献归属、投放费用分摊和供应商结算规则。若 Learning 等选定版本要求该 App，可作为技术依赖安装，是否启用在线支付另行决定。[官方能力说明](https://github.com/frappe/payments/blob/develop/README.md) |

官方产品目录还包含 Lending、Cloud、Press 等项目，但当前没有贷款业务或自营多租户托管平台需求，故不扩展选型范围。Frappe UI、Charts、Gantt 等属于开发工具或库，不应混为每个业务 Site 都需要安装的业务 App。[官方产品目录](https://frappe.io/products)

## 证据范围与差异

- 来源为官方产品目录、`frappe` 组织仓库、固定 commit 的 README / 依赖声明及官方文档。
- Drive 的 GitHub 归档状态与说明一致。Print Designer 的 README 已宣告归档及停止维护，但本次 GitHub 仓库 API 的 `archived` 字段仍为 `false`；本文据维护说明给出不新装建议，不把两个状态混写成已一致。
- Suite 的 `releases/latest` 返回 404 只表示本次没有取得 latest release，不能推出没有任何 tag、没有开发进展或所有功能不可用。
- GitHub 匿名 API 在进一步查询候选 release 时触发额度限制。本次通过可正常访问的官方源码和 `git ls-remote` 固定 Print Designer / Studio 的分支提交，未猜测它们的最新发布版本。
- 本次未验证上述新增应用与本地 Frappe 16.56.0、ERPNext 16.55.0、CRM 16.0.4 的组合安装，也未实测打印版式、邮件、视频会议、电话或支付链路。原仓库的安装与迁移命令仅作为说明阅读，未执行。
