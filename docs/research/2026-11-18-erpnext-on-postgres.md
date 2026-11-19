# ERPNext 客户与合同在 PostgreSQL 上的兼容性核查

**本地 PG 上，Customer 和 Contract 是否满足本项目需要？** 基础建档、签约记录、履约明细和客户/合同隔离通过。合同选联系人及关联资料权限需要绕过，已在隔离站点复测成功。

**这个结论能否外推到阿里云 RDS？** 不能。**RDS 未实测**，本轮没有获授权的空白 RDS 测试库。

**P2 建议：附条件采用。** GEO 运营可复用 ERPNext 的 `Customer` 和 `Contract` 作为主数据与合同底座。生产启用前须把联系人查询、关联资料授权及撤权固化到 GEO 实现，用实际 GEO 角色和服务授权规则复验，并通过目标 RDS 的部署和恢复验收。

实测日期为 2026-11-18 至 2026-11-19（北京时间）。版本固定为 Frappe 16.56.0、ERPNext 16.55.0、PostgreSQL 16.15。所有记录均为虚构测试数据。

## 实测结果

| 项目 | 结论 | 证据 |
| --- | --- | --- |
| 隔离环境、ERPNext 安装 | 通过 | 旧站 `pgcheck.local` 初始只装 Frappe。安装 ERPNext 退出 0，随后 `list-apps` 列出两个固定版本。 |
| 公司、主数据初始化及首次迁移 | 通过 | Setup Wizard 退出 0 并返回 `{"status":"ok"}`。查询确认虚构公司、CNY 和 2026 会计年度存在。首次 `migrate` 退出 0。 |
| 客户建档及同名命名 | 通过 | 采用 `Customer Name` 命名规则。A、B 建档成功，再建两个与 A 显示名称相同的客户，记录 ID 自动追加 `- 1` 和 `- 2`。 |
| 联系人与地址关联 | 通过 | A、B 各造一个 Contact 和 Address，保存为客户主联系人/主地址。重新读取客户字段及两类记录的 Dynamic Link，关系一致。 |
| 合同表单选客户 | 通过 | 受限账号在 Chrome 的真实 Desk 合同表单搜索并选中 A，`party_full_name` 自动回填。 |
| 合同表单选联系人 | 需绕过 | 原生 Contract 无 Contact Link。测试扩展接入 Frappe 的 `contact_query` 后，实际下拉返回 HTTP 500 与 PG 语法错误。改用客户的主联系人限制标准 Link 查询后，受限账号成功选中 A 的联系人。 |
| 合同写入及重新读取 | 通过 | 受限账号建合同 A，保存时为 `Unsigned`，记录签署后提交为 `Active`。REST 重读核对起止日期、签署人和日期、两条履约明细、履约状态及两个测试扩展字段。 |
| Customer / Contract 数据权限 | 通过 | 仅有 A 的 Customer User Permission 时，Desk 列表及 REST 列表只返回 A，Desk 详情及 REST 读取 A 为 200、B 为 403。报表 CSV 导出只含 A，指定 A+B 仍只含 A，指定 B 只含表头。 |
| Contact / Address 数据权限 | 需绕过 | 仅授权 Customer A 时，直接 GET B 的 Contact 为 200，A 的 Address 为 403。增加 A 的 Contact、Address 两条记录级授权及 `Sales User` 后，相关资料 A 为 200、B 为 403，A 的 Desk 详情也显示关联地址和联系人。 |
| 第二次迁移、备份与恢复 | 通过 | 源站再次迁移、`backup --with-files`、创建隔离目标站及 `restore` 均退出 0。恢复了四条客户、两份合同、关联、扩展和授权。目标站重复 HTTP 与表单验收通过。 |
| 阿里云 RDS PostgreSQL | 未测 | 无已授权的空白测试库。 |
| 独立 Frappe CRM、Frappe HR 同站安装和迁移 | 未测 | 本轮的固定版本站点只安装 Frappe 和 ERPNext，尚无 P2 必须与 CRM、HR 同站的要求。 |

## 1. 环境、安装及首次迁移

`bizbase-pgcheck-app`、`bizbase-pgcheck-db`、`bizbase-pgcheck-redis` 的 `com.docker.compose.project` 均为 `bizbase-pgcheck`，只加入 `bizbase-pgcheck-net`，无主机端口映射。应用的 sites/logs、数据库数据目录及 Redis 数据目录均为 Docker 卷，应用容器没有宿主源码绑定。`pgcheck.local` 配置为 `db_type=postgres`、`db_host=bizbase-pgcheck-db`、`db_port=5432`。起始 `list-apps` 只有 `frappe 16.56.0 UNVERSIONED`，因此续用该站。测试网页通过同项目的 `bizbase-pgcheck-web` 在独立回环端口提供。

```sh
rtk proxy docker inspect --format '{{.Name}} {{index .Config.Labels "com.docker.compose.project"}} {{json .Mounts}} {{json .HostConfig.PortBindings}}' bizbase-pgcheck-app bizbase-pgcheck-db bizbase-pgcheck-redis
rtk proxy docker exec bizbase-pgcheck-db psql -U postgres -d postgres -Atc 'SELECT version();'
rtk proxy docker exec bizbase-pgcheck-app bench --site pgcheck.local list-apps
rtk proxy docker exec bizbase-pgcheck-app bench --site pgcheck.local install-app erpnext
rtk proxy docker exec bizbase-pgcheck-app bench --site pgcheck.local execute frappe.desk.page.setup_wizard.setup_wizard.setup_complete --kwargs '{"args":{"language":"English","country":"China","timezone":"Asia/Shanghai","currency":"CNY","company_name":"PGCheck Fictional Company","company_abbr":"PGC","fy_start_date":"2026-01-01","fy_end_date":"2026-12-31","chart_of_accounts":"Standard","enable_telemetry":0}}'
rtk proxy docker exec bizbase-pgcheck-app bench --site pgcheck.local migrate
rtk proxy docker exec bizbase-pgcheck-app bench --site pgcheck.local list-apps
```

```text
PostgreSQL 16.15 (Debian 16.15-1.pgdg13+2)
install-app: exit 0, Updating DocTypes for erpnext 100%
setup_complete: exit 0, {"status": "ok"}
migrate #1: exit 0, Executing `after_migrate` hooks...
frappe  16.56.0 UNVERSIONED
erpnext 16.55.0 UNVERSIONED
```

Context7 返回 Frappe `version-16` 的迁移、备份和 User Permission 说明。固定补丁版本的行为以实际运行和镜像内对应源码核对。

## 2. 客户、联系人与合同表单

客户记录 ID 分别是 `PGCheck Fictional Alpha`、`PGCheck Fictional Beta`、`PGCheck Fictional Alpha - 1`、`PGCheck Fictional Alpha - 2`，A 及其两个同名记录的显示名称均为 `PGCheck Fictional Alpha`。实际生效的是 Customer 控制器的 PostgreSQL 命名分支。 [ERPNext v16.55.0 Customer 控制器](https://github.com/frappe/erpnext/blob/v16.55.0/erpnext/selling/doctype/customer/customer.py)

首个业务失败操作是在合同表单的测试 Contact Link 下拉中，选择客户 A 后输入 `PGCheck`。浏览器通过 `frappe.desk.search.search_link` 调用 `frappe.contacts.doctype.contact.contact.contact_query`，返回 HTTP 500 和 `SyntaxError`。用同一受限用户调用相同查询路径的 `search_widget`，退出 1，得到原始 PostgreSQL 错误。受影响的路径是接入该查询的客户关联联系人下拉。 [Frappe v16.56.0 Contact 查询](https://github.com/frappe/frappe/blob/v16.56.0/frappe/contacts/doctype/contact/contact.py#L398)

```text
psycopg2.errors.SyntaxError: LIMIT #,# syntax is not supported
LINE 15:   limit '0', '10'
           ^
HINT:  Use separate LIMIT and OFFSET clauses.
SQLSTATE 42601
```

已复测的绕过方式是在 Contract 增加 `custom_pgcheck_contact`（Link → Contact），用站点 Client Script 读取所选客户的 `customer_primary_contact`，以该 ID 过滤标准 Link 查询。实际界面在源站及恢复站均返回 HTTP 200，并选中 `PGCheck Contact A-PGCheck Fictional Alpha`。当前脚本只覆盖新建合同或更改客户后选择**主联系人**。任意关联联系人、多签署人和后端写入时校验联系人归属未测。

受限账号将 A 合同 `CON-2026-00002` 保存为 `Unsigned`，填写签署信息后以同一账号提交。重读结果如下。

```text
party_type=Customer  party_name=PGCheck Fictional Alpha
start_date=2026-11-18  end_date=2027-02-17
docstatus=1  is_signed=1  status=Active
signee=Fictional Signer A  signed_on=2026-11-19 10:00:00
signed_by_company=pgcheck-operator@example.invalid
fulfilment_status=Partially Fulfilled
fulfilment_terms=[["Fictional kickoff",1],["Fictional first report",0]]
custom_pgcheck_contact=PGCheck Contact A-PGCheck Fictional Alpha
custom_pgcheck_reference=GEO-EXAMPLE-A
```

## 3. 受限用户与导出

实际登录的是 `pgcheck-operator@example.invalid`，起初有 `Sales Manager`、`Sales Master Manager` 和一条针对客户 A 的 Customer User Permission。B 的客户和合同由管理身份确认存在，B 合同为 `CON-2026-00001`。Desk、REST 及 CSV 由普通账号的 HTTP 会话验证。

| 入口 | A | B |
| --- | --- | --- |
| Desk 列表 `frappe.desk.reportview.get` | HTTP 200，返回记录 | 列表中无 B |
| Desk 详情 `frappe.desk.form.load.getdoc` | HTTP 200 | HTTP 403 `PermissionError` |
| REST `/api/resource/{doctype}` | HTTP 200，返回记录 | 列表中无 B |
| REST `/api/resource/{doctype}/{name}` | HTTP 200 | HTTP 403 `PermissionError` |
| CSV `frappe.desk.reportview.export_query` | 全部或指定 A+B 均只含 A | 指定 B 时 HTTP 200，仅返回表头 |

Contact 及 Address 需要单独验证。首次 `GET /api/resource/Contact/PGCheck%20Contact%20B-PGCheck%20Fictional%20Beta` 返回 HTTP 200，数据含 `links=[["Customer","PGCheck Fictional Beta"]]`（从子表提取的字段）。同时 `GET /api/resource/Address/PGCheck%20Address%20A-Billing` 返回 HTTP 403 `PermissionError`，A 的 Desk 客户详情没有地址行。测试站给同一账号加上原生 `Sales User`，并用 User Permission 显式允许 A 的 Contact 和 Address。复测时 A 的关联资料均为 200、B 均为 403。再次迁移和恢复后，同样结果仍成立。

此配置实证覆盖两组记录。真实 GEO 角色、按服务成员授权、多客户/多方合同和授权随建档、变更及撤权同步均未测；试验使用的原生销售角色只用于验证。本轮 CSV 覆盖 Desk 报表的同步导出。

## 4. 迁移、备份和恢复

本地恢复站 `pgcheck-restore.local` 使用同一隔离 PG 服务的独立数据库 `pgcheck_restore_20261119`。建站之前核实目标站目录不存在、目标数据库查询计数为 0。命令中的 `PGCHECK_ROOT_PASSWORD` 为隔离 PG 管理账号口令，`PGCHECK_ADMIN_PASSWORD` 为新站的测试管理员口令。

```sh
rtk proxy docker exec bizbase-pgcheck-app bench --site pgcheck.local migrate
rtk proxy docker exec bizbase-pgcheck-app bench --site pgcheck.local backup --with-files
rtk proxy docker exec bizbase-pgcheck-app bench new-site pgcheck-restore.local --db-type postgres --db-host bizbase-pgcheck-db --db-port 5432 --db-name pgcheck_restore_20261119 --db-root-username postgres --db-root-password "$PGCHECK_ROOT_PASSWORD" --admin-password "$PGCHECK_ADMIN_PASSWORD"
rtk proxy docker exec bizbase-pgcheck-app bench --site pgcheck-restore.local restore \
  /home/frappe/frappe-bench/sites/pgcheck.local/private/backups/20261119_000823-pgcheck_local-database.sql.gz \
  --with-public-files /home/frappe/frappe-bench/sites/pgcheck.local/private/backups/20261119_000823-pgcheck_local-files.tar \
  --with-private-files /home/frappe/frappe-bench/sites/pgcheck.local/private/backups/20261119_000823-pgcheck_local-private-files.tar \
  --db-root-username postgres --db-root-password "$PGCHECK_ROOT_PASSWORD"
rtk proxy docker exec bizbase-pgcheck-app bench --site pgcheck-restore.local list-apps
```

```text
migrate #2: exit 0, Executing `after_migrate` hooks...
backup: exit 0, Backup for Site pgcheck.local has been successfully completed with files
new-site pgcheck-restore.local: exit 0
Note: PostgreSQL support is currently in development and considered experimental.
restore: exit 0, Site pgcheck-restore.local has been restored with files
frappe  16.56.0 UNVERSIONED
erpnext 16.55.0 UNVERSIONED
SITE pgcheck-restore.local pgcheck_restore_20261119 16.15
GRANTS ['Address', 'Contact', 'Customer'] custom field and client script exist
```

恢复站重读确认四个客户 ID、A/B 的 Contact 和 Address 关联、两份合同与对应当事方、A 的签署及履约字段。以相同普通账号登录后，再次通过第 3 节的列表、详情、REST、CSV 检查，也从新建合同表单再次选中 A 和 A 的主联系人。备份包含公共与私有文件归档，本轮没有创建附件。

## 5. 阿里云 RDS PostgreSQL

**未测。** 本轮本地 PG 以隔离容器的 `postgres` 账号初始化。目标 RDS 需在获授权的空白测试库上，用拟部署账号验证建库建角色、数据库所有者及 schema 授权，再用拟运行的应用账号验证 TLS、实际读写、迁移和恢复。现有业务库不用于 `new-site`。Frappe 固定版本的建站代码确实涉及建角色、数据库所有权及 schema 授权。 [Frappe v16.56.0 PostgreSQL 建站代码](https://github.com/frappe/frappe/blob/v16.56.0/frappe/database/postgres/setup_db.py)

## 复核脚本及范围

本机复核脚本和日志目录为 `/Users/aij/.codex/private/bizbase-pgcheck-20261118`。以下命令在已保留的源站和恢复站上可重复执行读取检查。浏览器测试容器停止后，可重新启动并用 `docker port` 查询回环端口。脚本从隔离应用容器读取临时测试账号配置。

```sh
rtk proxy docker exec -i bizbase-pgcheck-app env/bin/python - < /Users/aij/.codex/private/bizbase-pgcheck-20261118/probe.py
rtk proxy docker exec -i bizbase-pgcheck-app env/bin/python - < /Users/aij/.codex/private/bizbase-pgcheck-20261118/verify-both.py
rtk proxy docker start bizbase-pgcheck-web
rtk proxy docker port bizbase-pgcheck-web 8000/tcp
rtk proxy node /Users/aij/.codex/private/bizbase-pgcheck-20261118/permissions.cjs "$PGCHECK_PORT" pgcheck.local CON-2026-00002
rtk proxy node /Users/aij/.codex/private/bizbase-pgcheck-20261118/permissions.cjs "$PGCHECK_PORT" pgcheck-restore.local CON-2026-00002
rtk proxy node /Users/aij/.codex/private/bizbase-pgcheck-20261118/form.cjs "$PGCHECK_PORT" pgcheck-restore.local restore-search
```

`probe.py` 预期退出 1 并复现第 2 节 SQL 错误，其余检查退出 0。保留 `fixtures.py`、`primary-contact.py` 与 `related-grants.py` 作为测试数据和配置的创建记录。它们用于新建测试场景，重跑会尝试重复写入。

上一轮 Docker 命令受审批执行环境阻塞，当时没有业务通过或失败的记录。此前独立的 `bizbase-pgtest-*` 及其 App 证据未用于本轮验收。8080 预览继续运行。库存、薪资、完整财务、上线站点及移山 ID 登录不在本次验收范围。
