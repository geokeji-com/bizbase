# ERPNext 客户与合同在 PostgreSQL 上的兼容性核查

2026-11-18，供 P2 选型。结论：**尚未验证关键业务路径，不能批准生产采用，也没有证据判定不兼容。** 此记录是阶段性证据，不是测试通过报告。

## 已查到的证据

| 层次 | 证据 | 能说明什么 |
|---|---|---|
| 本地框架 | 单独的 PG 16 测试站点 `pgtest.local` 的 `list-apps` 返回 Frappe 16.56.0、GEO 运营和登录集成，未列出 ERPNext。另一个独立 `pgcheck` 环境的 `select version()` 返回 PostgreSQL 16.15；`new-site` 打印 `PostgreSQL support is currently in development and considered experimental.` | 框架有可运行的 PG 路径。两个站点的证据不可混用；镜像里存在 ERPNext 包不代表站点已安装它。 |
| ERPNext 测试覆盖 | [ERPNext v16.55.0 的 PG 测试工作流](https://github.com/frappe/erpnext/blob/v16.55.0/.github/workflows/server-tests-postgres.yml) 第 23 行按 PR 的 `postgres` 标签运行。证据来自已安装镜像中的源文件。 | 上游有 PG 测试入口，不能据此断言此版本、本项目用例已通过。 |
| 业务 SQL | 已安装镜像扫描在 [Customer 控制器](https://github.com/frappe/erpnext/blob/v16.55.0/erpnext/selling/doctype/customer/customer.py#L163) 找到 `SUBSTRING_INDEX` 与 `AS UNSIGNED`，在 [联系人查询](https://github.com/frappe/frappe/blob/v16.56.0/frappe/contacts/doctype/contact/contact.py#L419) 找到 `if(locate(...))`。 | 应覆盖同名客户处理和表单中搜索联系人；关键字命中不等于 PG 路径实际执行该 SQL，也不计作失败。 |
| 托管数据库 | [固定版本的建站代码](https://github.com/frappe/frappe/blob/v16.56.0/frappe/database/postgres/setup_db.py) 涉及建库、角色、数据库所有者及 schema 授权。 | 本地管理员建站不证明 RDS 部署账号能完成同样操作。没有连接真实 RDS。 |

## 仅对项目要用的能力设验收条件

1. 在隔离 PG 站点核对已装应用后，安装 ERPNext 16.55.0，完成公司初始化和一次迁移。必须取得成功退出状态并用 `list-apps` 确认，不能只看安装进度条。
2. 创建两个测试客户，覆盖普通和同名情形；保存联系人、地址及动态关联，再从合同表单按授权身份查到正确客户及联系人。
3. 以客户为合同当事方，保存履约条款和扩展字段，记录签署状态，重新读取并核对字段与明细。以受限用户分别核对允许和不允许的记录，覆盖列表、详情、API 和导出。
4. 再跑迁移，备份恢复到新的隔离站点，核对客户与合同仍可读、权限仍有效。近期不使用的财务、CRM 看板、薪资等不作为 P2 的否决条件；若生产要求同站安装 CRM、HR，则它们的安装与迁移仍须单独通过。
5. 在目标 RDS 大版本的**空白测试库**以拟用部署账号复测初始化、TLS 连接、应用账号读写及备份恢复；不得用已有业务库测试 `new-site`。

以上 1–5 尚无完整通过记录。先前工作流中断；此次 Docker 命令因工具执行审批服务不可用未执行。隔离的 `bizbase-pgcheck-*` 资源此前已创建，当前状态和清理未核实。不要与 `bizbase-pgtest-*` 或 8080 预览资源混用。

**P2 建议措辞：** 优先复用现有平台能力；在目标数据库、应用版本和实际授权条件下验证所需业务路径，验证通过再定为实现依赖。ERPNext Customer、Contract 暂列候选。
