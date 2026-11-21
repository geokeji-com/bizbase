# BizBase 公网环境

入口为 `https://bizbase.geokeji.com`，站点同名。ECS 宿主机 Nginx 终止 TLS 并转发到 `127.0.0.1:3180`。Certbot 使用已有的定时器和本站专属 webroot，不在容器内另外签证书。

生产使用 `/opt/bizbase-prod/compose.yaml`，项目名 `bizbase-prod`；不要对其他项目执行 `down` 或主机级 prune。`docker compose ps` 在该目录执行。站点文件和附件在 `/var/lib/bizbase-prod/sites`，进程日志在 `/var/lib/bizbase-prod/logs`。

RDS 数据库 `bizbase` 的业务表只放在 `bizbase_app` schema，不需要 `public` 的 CREATE 权限。共享 Redis 分配 DB 2（缓存）与 DB 4（队列），bench ID 是 `bizbase-prod`。逻辑库隔离键，不隔离内存、连接数和 Pub/Sub；不要更改实例级配置或执行 FLUSHALL。数据库和 Redis 均不由此 Compose 启停。

`/etc/bizbase/connections.ini` 是首次准备站点的输入，修改它不会自动轮换站点凭据。`prepare_host.py` 和 `first_install.sh` 仅供**首次安装**使用，不能用来升级或重置密码。运行中的应用从受限的 `common_site_config.json` 和 `site_config.json` 读取设置，不要粘贴这些文件、cookie、连接串或完整诊断日志。

初始账号为 `Administrator`。管理员在自己的 ECS root 终端查看 `/etc/bizbase/initial-admin-password`，首次登录后在 Desk 改密并妥善保管；改密后初始密码文件和首次登录测试将不再有效。移山 ID 未登记前保留账号密码登录；新版回调及旧站切换顺序见下文「已有站点更名移山 ID」。

升级或录入正式业务数据前，确认 RDS 备份覆盖和可恢复性，并为附件、站点配置（含加密密钥）配置受保护的异机备份和恢复演练。只有数据库快照不能恢复附件与密钥。

当前仓库的管理看板安装标识为 `management_board`，Desk 入口为 `/desk/management-board`。下文「已有站点更名移山 ID」记录 2026-11-20 已完成的迁移窗口，其中的 `bizbase_mgmt` 是该窗口实际安装的标识。`routes_window.sh`、`rehearse_routes.py`、`rehearsal_checks.py` 和 `preserve_geo.py` 与当时的镜像配套，供核对历史迁移使用。

## 发布

日常发布用 `/opt/bizbase-prod/deploy.sh` 做蓝绿切换，不再对运行中的项目执行 `docker compose up`，原地重建容器会让入口 502 数十秒。两套槽位 `bizbase-prod-blue`（3181）和 `bizbase-prod-green`（3182）共用站点目录、数据库与 Redis。脚本先在空闲槽位启动 web 进程，健康检查和冒烟测试通过后改写宿主机 Nginx 的 upstream 并 reload，然后交接 worker 与 scheduler。旧槽位 web 进程保留，可秒级回滚。尚未切换过的原 `bizbase-prod` 项目（3180）视为第一个槽位。

按改动选择方式：

| 类型 | 改动 | 做法 |
| --- | --- | --- |
| A | 仅代码、模板、自定义应用静态文件 | `deploy.sh release IMAGE` |
| B | 只新增 DocType、字段、索引，旧代码可在新结构上运行 | `deploy.sh release IMAGE --migrate`，迁移时旧槽位继续服务 |
| C | 删除、重命名字段或改类型 | 拆成多次 B：先加新结构并双写，迁移数据，最后一次发布再删旧结构 |
| D | 升级 Frappe/ERPNext、新装应用、改共享配置 | 维护窗口，见下文 |

Frappe/ERPNext 资源清单（`assets/assets.json`）与运行中镜像不同，或新旧镜像与持久化 `sites/apps.txt` 三者的应用集合不一致时，普通 `release` 拒绝发布。两个槽位共用 Redis 中的资源清单，只能在维护窗口里换。

```sh
/opt/bizbase-prod/deploy.sh status
/opt/bizbase-prod/deploy.sh release bizbase/prod:<tag> [--migrate]
/opt/bizbase-prod/deploy.sh rollback [--force]
/opt/bizbase-prod/deploy.sh retire
```

`rollback` 将流量和后台任务切回上一槽位。若当前槽位执行过 migrate，需确认变更属于 B 类后加 `--force`。观察期结束后用 `retire` 回收旧槽位；下次 `release` 也会自动回收。切换后 Nginx 仍会让在途请求在旧槽位上完成，worker 有 120 秒完成当前任务。登录会话存于共享 Redis 与数据库，切换不需要重新登录。

槽位镜像与端口写在 `/opt/bizbase-prod/slots/<槽位>.env`，状态记录在同目录。对当前槽位执行 compose 命令时用 `deploy.sh compose ...`，例如 `deploy.sh compose exec backend bench --site bizbase.geokeji.com list-apps`。

### 一次性接入（已于 2026-11-19 完成）

1. 将新版 `compose.yaml` 和 `deploy.sh` 放到 `/opt/bizbase-prod/`，`chmod 700 deploy.sh`。
2. 创建 `/www/server/panel/vhost/nginx/bizbase-upstream.inc`，内容为 `server 127.0.0.1:3180;`。
3. 在 `bizbase.conf` 顶部加 `upstream bizbase_slot { include /www/server/panel/vhost/nginx/bizbase-upstream.inc; }`，把 `proxy_pass http://127.0.0.1:3180` 改为 `proxy_pass http://bizbase_slot`。upstream 名在整个 http 上下文中唯一，不要和其他站点同名。
4. 将 `bizbase-unavailable.html` 放到 `/var/lib/bizbase-pages/`（宝塔 vhost 目录对 Nginx worker 用户 `www` 不可读）。在 443 server 中加入 `error_page 502 504 /bizbase-unavailable.html;` 和 `location = /bizbase-unavailable.html { root /var/lib/bizbase-pages; internal; }`。宿主机连不上槽位时用户看到「正在更新」提示，不再是 Nginx 默认错误页。503 不拦截，应用维护模式的页面照常透传。
5. `nginx -t` 通过后 `nginx -s reload`，不重建容器，接入本身不中断服务。原配置备份在 `/root/bizbase.conf.bak-20261119-cutover`。用 `deploy.sh status` 确认 active 为 `legacy`、Nginx 指向 3180。
6. 原项目仍在运行旧版 compose，没有健康检查。第一次 `deploy.sh release` 时会启动 blue 并切换。之后再发布时，脚本会自动回收原项目。

### 维护窗口（D 类）

D 类仍使用蓝绿两个槽位和同一个 Nginx upstream；不同点是共享数据库不再向后兼容。因此**旧 web、worker、scheduler 全停后才改数据库**。维护期间入口显示更新提示。新槽先在回环端口独立验收，再切 Nginx。禁止为绕过 `release` 的检查提前改写应用清单，也不要在活动槽上原地换镜像。

2026-11-19 生产盘点：`frappe`、`erpnext`、`geo_operations`、`yishan_id_login`、`static_share`。下节的旧版本 ERPNext 安装流程不适用于这个起点。**本次实际顺序和放行条件见「已有站点更名移山 ID」**。生产前核对实时起点；下列流程设计与本地测试不等于已在 RDS 演练或线上执行。

## 仅供旧版本站点首次加入 ERPNext 与文件分享

1. 在获准的隔离 RDS 测试库演练安装、迁移及恢复。生产维护前记录当前镜像 ID、站点已装应用、Compose 配置和持久卷 `sites/apps.txt`。核对 RDS 恢复点并保留同一检查点的站点配置、密钥及附件备份。
2. 在维护窗口开启站点维护模式，停止本站 worker 和 scheduler，完成一致性备份。将已验证的新镜像设为本站 `BIZBASE_IMAGE`。在宿主机持久化的 `/var/lib/bizbase-prod/sites/apps.txt` 保留原有应用，各追加一行缺失的 `erpnext`、`static_share`。切换 backend 后用 `bench --site bizbase.geokeji.com list-apps` 核对起点。
3. 在新 backend 中仅对缺失应用依次运行 `bench --site bizbase.geokeji.com install-app erpnext` 和 `bench --site bizbase.geokeji.com install-app static_share`。随后执行 `bench --site bizbase.geokeji.com migrate`、`bench --site bizbase.geokeji.com clear-cache`。保留现有用户、绑定和站点配置。
4. 用同一镜像恢复全部五个服务，关闭维护模式。从 HTTPS 入口验证登录、ERPNext 资源、Employee 和分享权限。若迁移失败，在维护模式下恢复同一检查点的数据库、站点文件、应用清单、Compose 配置与旧镜像。

管理入口为 `/file-share`（文件分享）和 `/yishan-id`（移山 ID）。多域名版生成 `/file-share/s/<ID>`，原 `/file-share/<ID>` 和更早的 `/s/<ID>` 也必须执行同一份报告的域名、权限和版本校验。

### 逐个接入文件分享域名（多域名版发布后）

已在另一台自有服务器托管域名、只需按路径分流的例子，见[中企动力双机内网接入](cebest-intranet.md)。这种情况保留原 DNS 和公网证书，不套用整站迁移步骤。

以下是运维步骤，不会因管理员登记域名而自动执行。公司/渠道须提供**完整主机名、DNS 联系人、证书签发及续期方式、是否需要员工登录**。对方只需将 A 或 CNAME 指向双方约定的公网入口；仅在整条链路支持 IPv6 时添加 AAAA。不要开放应用容器端口。

1. 管理员先在文件分享 App 的域名管理中登记为待接入。为每个域名准备有效 HTTPS 证书和自动续期；证书私钥不放进应用、Git 或聊天。生产入口为宿主机 Nginx → `bizbase_slot` → 当前槽位的 frontend → 固定的 Frappe site，不为渠道新建 site。
2. 为公司/渠道逐个声明**精确** `server_name`，不使用通配域名。内层 frontend 模板从 `/etc/nginx/bizbase-share-domains/*.conf` 读额外名称。将 root 管理的名单文件只读挂载至两槽位的 frontend，例如在部署用 `compose.yaml` 中增加以下配置；不改 backend、业务数据卷或活动槽位端口。`/etc/bizbase/share-hosts.conf` 内容如 `server_name report.channel-a.example report.channel-b.example;`，不要包含默认主站、`localhost` 或 IP。新增/移除域名后按发布窗口更新各槽，使重建或回退均使用当前名单。

   ```yaml
   services:
     frontend:
       configs:
         - source: share_hosts
           target: /etc/nginx/bizbase-share-domains/allowed.conf
   configs:
     share_hosts:
       file: /etc/bizbase/share-hosts.conf
   ```

3. 用[渠道域名 vhost 样例](share-domain.conf.example)为每个渠道建立独立宿主机 vhost，替换样例域名及证书路径。不要再定义 `bizbase_slot`，不要把 3180/3181/3182 暴露在公网。宿主默认 vhost 应拒绝未配置 Host 和直接 IP，不要把不匹配的请求转进主站。外层覆盖传入的 `Host`、协议与代理头；内层固定 `X-Frappe-Site-Name`，但保留已匹配的外部 Host。密码页、带签名的资源和兼容路径都直达应用，不开启代理缓存，不落盘记录分享 URL。主站现有代理同样应覆盖这些头部。
4. 渠道样例只开放报告与资源，**不会**把 Desk、API、登录和身份回调一并发布到渠道域名。需要内部员工/指定人员访问的自有域名，应使用受信任的公司站点 vhost，保留现有登录、静态资源和回调路径；确认本站认证方式支持该确切域名，单独完成域名登录验收后再选员工权限。不要假定其他域名能沿用主站登录 Cookie，或直接把员工登录开放给渠道。
5. 取得维护授权后，分别检查内外层 `nginx -t`，在发布窗口应用。先核对外网 DNS 和证书链，再用测试报告验收：启用 A/未启用 B 时三个分享路径在 A 能用、在 B 不可用；`c/` 内 HTML、JS、CSS、图片按域名校验；停用 A 后已打开页面的后续资源请求也被拒绝。在各可用入口确认 CSP、`no-store`、密码登录与实际版本；资源响应没有 `Set-Cookie`，分享外壳可以签发 Cookie。确认无误后才把该域名开放给发布人。停用渠道时先在应用停用域名，再清理两层代理、证书及 DNS。

## PG16 schema 备份与恢复演练

将 `pg16_schema.py` 放在 ECS 的 `/opt/bizbase-prod/`，由 root 管理和运行。宿主需有 Python 3.7+、Docker 和本地镜像 `postgres:16-alpine`。`/etc/bizbase/connections.ini` 由 root 持有，权限 `0600`，使用 `prepare_host.py` 约定的 `[postgres]` 连接参数。备份根目录 `/var/backups/bizbase-pg16/` 和每次备份子目录为 `0700`，归档、计数清单和临时凭据为 `0600`。为备份目录预留原归档、演练归档及展开 SQL 的空间，Docker 数据目录还需容纳一份还原库及 WAL。

```sh
rtk proxy sudo python3 -I /opt/bizbase-prod/pg16_schema.py backup
```

从成功输出的目录取最后一级作为 `BACKUP_ID`。冻结时执行 `backup` 后紧接 `verify`，两步都成功再登记检查点。`backup` 以同一个 PG16 只读快照导出 `pg_dump -Fc -n bizbase_app`，记录普通表和分区的逐表精确行数、源端跨 schema 依赖检查结果及归档 SHA-256。`verify` 核对摘要，在全新断网的 PG16 容器内还原原归档，并核对表集合及行数。要在另一台主机复验，将整个编号目录安全复制到该机相同根目录，核对备份时记录的摘要并保持 root 权限；该步骤只需要归档、清单和本地镜像。

```sh
rtk proxy sudo python3 -I /opt/bizbase-prod/pg16_schema.py verify "$BACKUP_ID"
```

回灌前可单独执行离线诊断。它在临时库完成还原、改名和依赖检查。阻断项只输出类别与数量，如 `partial_index`、`expression_index`、`check_constraint`、`unrecognized_default`。对未识别默认值，`default_shape` 另按解析节点、内置类型和内置函数名汇总。已复核的部分唯一索引仅限演练 schema 中 `tabAutomation Trigger Queue` 表的 `unique_dedup_key` 及 PG16 对其已确认谓词的两种精确表达。

```sh
rtk proxy sudo python3 -I /opt/bizbase-prod/pg16_schema.py diagnose "$BACKUP_ID"
```

实际回灌演练时运行下列命令。目标固定为上述连接中 `bizbase` 数据库的 `bizbase_rehearsal`，须事先存在且为空。执行角色 `bizbase_app` 需有该 schema 的所有者权限及数据库 `CREATE` 权限，演练期间应独占目标 schema。脚本再次隔离还原，在临时库执行 `ALTER SCHEMA bizbase_app RENAME TO bizbase_rehearsal`，检查依赖并重新导出演练 schema。目标事务用 `DROP SCHEMA … RESTRICT` 探测空 schema 后回滚到保存点，保留其所有者、授权和注释，再还原对象、核对全部计数后提交。失败以非零状态退出；提交确认时若连接中断，先核对目标状态再重试。

```sh
rtk proxy sudo python3 -I /opt/bizbase-prod/pg16_schema.py rehearse "$BACKUP_ID"
```

演练导入支持普通表、序列、普通列索引、主键、唯一键和 schema 内外键。跨 schema 依赖、可执行函数、用户触发器、视图、表达式索引及未识别的对象或默认表达式会中止回灌，需按实际对象单独审查。对象按演练账号重建，原备份中的对象所有者及 ACL 保留在原始归档。站点文件、密钥及附件仍按同一冻结检查点单独备份。

## 已有站点更名移山 ID

这是 D 类发布。生产当前使用 `yishan_id_login`。在身份平台追加新回调 `https://bizbase.geokeji.com/api/method/yishan_id.auth.callback`，旧回调保留到生产验收完成。如果平台只允许一个地址，在维护窗口内切换。新后端退出通知路径为 `/api/method/yishan_id.auth.backchannel_logout`。本地 DEV 独立登记 `http://127.0.0.1:8080/api/method/yishan_id.auth.callback`。

以下命令均在 `/opt/bizbase-prod` 执行，`SITE=bizbase.geokeji.com`。每项实际的生产写操作遵守 D-004，独立 RDS 演练、维护停机、备份、卸载、迁移、切流及恢复以各自的授权为准。切流后若需恢复旧版本，恢复点以后的新写入需要单独处置。

1. **演练和窗口准备。** 在获准的隔离数据库上用生产同版本旧代码和最终 `linux/amd64` 镜像跑完整顺序，并验证备份可恢复。对照新旧 app、DocType、Module Def、默认入口、模块禁用数及绑定数；记录分享数、访问日志数、版本数、附件数和校验样本。演练文件分享的历史链接、私有打开、旧密码及拒绝访问，不只做 HTTP ping。演练 `bench --site "$SITE" uninstall-app geo_operations --dry-run`，核对其 DocType、Workspace、自定义字段、真实数据及跨应用依赖；发现业务数据就暂停卸载，先决定归属。准备 RDS 和站点**同一时间点**的恢复操作及耗时，包含加密密钥、附件、公私文件、持久化 `apps.txt`、队列处理方案、部署目录、`slots` 状态和宿主 Nginx upstream。不得用其他项目的 Redis 清库来代替恢复。确认宿主已装带 `maintenance` 子命令的新版脚本；最终镜像在 ECS 本地已核对 ID，两个改名脚本与演练版本一致。
2. **预备与冻结。** `./deploy.sh status` 核对 active、previous、端口及 Nginx。如果存在上一回滚槽，先决定是否获准 `retire`；`begin` 不会自动删除它。确认无意外旧容器或站外写入者。执行 `./deploy.sh maintenance begin "$IMAGE"`，记录新旧镜像 ID；此时尚未停服。获准窗口后暂停 `bizbase-yishan-id.timer`，等当前 service 结束；确认本站队列无未完成/待执行的旧应用任务，不处理外部项目的队列。`./deploy.sh maintenance freeze` 开启维护模式并停止旧槽的全部五个服务。此后旧槽入口不可用，这是预期的维护状态。
3. **取得一致性检查点。** 在两个槽位都不写共享数据时，按已演练的 RDS/站点文件备份方案取同一检查点并核验可恢复性。逻辑备份使用与 RDS 服务端大版本匹配的 `pg_dump`/`pg_restore`；本地发现较新版 `pg_dump` 生成的 `SET transaction_timeout` 在 PG16 无法还原，必须以实际还原和数据核对为准。执行 `./deploy.sh maintenance checkpoint <检查点工单号>` 记录对应备份并创建空闲槽的 backend 容器但不启动服务。该命令**不会备份或验证 RDS**。用 `./deploy.sh status` 查看阶段；窗口打开后普通 `release`、`rollback`（含 `--force`）、`retire`、`compose` 均被拒绝。
4. **旧镜像迁移。** 获准后，在冻结状态用 `./deploy.sh maintenance old bench --site "$SITE" uninstall-app geo_operations --yes` 卸载已确认的空模块。然后在**同一旧镜像**中先迁移身份，再立即执行文件分享迁移。后者直接操作 PostgreSQL，不依赖已改名的模块；**两条命令之间不要运行加载 hooks 的 bench 命令**。两个脚本均需在相同上游版本演练通过：

   ```sh
   ./deploy.sh maintenance old env/bin/python - --site "$SITE" < rename_yishan_id.py
   ./deploy.sh maintenance old env/bin/python - --site "$SITE" < rename_file_share.py
   ```

5. **候选槽迁移。** `./deploy.sh maintenance manifest` 将新镜像的 `sites/apps.txt` 原子写入持久目录。此后脚本不再允许运行旧代码。新镜像应有 `frappe erpnext yishan_id file_share crm insights bizbase_mgmt sales_board ops_board customer_board`，没有 HRMS、`geo_operations` 或两个旧安装名。先用 `./deploy.sh maintenance new bench --site "$SITE" list-apps` 核对两个保留数据的应用已改名；勿用卸载重装代替改名。用 `./deploy.sh maintenance new bench --site "$SITE" install-app <应用>` 对缺少的 `crm`、`insights`、`bizbase_mgmt`、`sales_board`、`ops_board`、`customer_board` 逐个安装。执行 `./deploy.sh maintenance migrate`：脚本校验数据库为 PG、已装集合与新镜像/站点清单一致，执行并复核 `migrate` 与本站 `clear-cache`。若失败，旧槽保持停服；不要尝试直接重启旧槽。更新身份同步脚本/配置后再恢复 timer，手动配置的站点也要更新 `yishan_id_redirect_uri`。
6. **回环端口验收。** `./deploy.sh maintenance preview` 关闭站点维护模式，只启动候选槽的 backend、websocket、frontend，先经回环端口验活。Nginx 此时仍指向已停的旧槽，worker、scheduler 尚未启动。运维人员从受保护的回环访问或 SSH 本地转发测试候选（不要对公网开放 3181/3182）。用真实浏览器验收管理员桌面的十个入口、四看板、移山 ID 与文件分享的最终地址、表单深链、旧链接重定向、权限拒绝和记录/附件数量；通过 Insights 内置 Site DB 执行只读查询。普通登录页、静态资源和 `/api/method/ping` 仅是最低冒烟，不代替业务验收。
7. **独立授权切流。** `./deploy.sh maintenance publish` 将 Nginx 指向已验收的候选槽，检查公网入口后启动候选后台任务。公网检查失败时脚本停止候选入口和作业，**绝不自动回切旧代码**；修复后可在 `publishing` 阶段重新执行 `publish`。通过真实 HTTPS 入口验收 Desk、文件分享、绑定/模块禁用数、扫码登录与后端退出；核对定时器校验成功。生产验证全部通过后执行 `./deploy.sh maintenance accept`：归档窗口记录，不把旧槽登记成 `previous`，故即使 `rollback --force` 也不能退回更名前的代码。最后撤销旧回调。状态目录 `slots/completed-D.*/record` 记录当次旧/新槽及精确镜像 ID。

**故障恢复。** `freeze` 后先保持维护，不要用 A/B 的 `rollback`，也不要删 `slots/maintenance` 解除保护。新版本已经对外开放时，先记下开放后的写入、作业和附件，再获准停机隔离。窗口尚未 accept 时执行 `./deploy.sh maintenance isolate` 停止两个槽位所有本站服务；若窗口已归档则按归档的项目名定向停止对应进程，并保持流量隔离。常规优先在新槽查明原因，避免丢失新增数据。确需回旧时，**先**获准恢复/核对一致性检查点的 RDS、站点文件、配置和队列，使用原镜像在隔离入口核验旧清单、绑定、分享、附件和访问权限；核对提供方旧回调、同步脚本与 timer。再恢复该检查点的槽位状态、镜像及 upstream，验收旧站后才重新接流与启用后台作业。恢复数据库、单独放行旧流量、合并新写入均非发布脚本自动操作，也不得把当前检查点当成入站授权。

## 功能访问统计

在 [Microsoft Clarity 项目](https://clarity.microsoft.com/projects/view/uy7jcuzycs/dashboard) 中查看 `/_usage/` 下各页面的浏览量。`/_usage/file-share/view` 汇总打开分享内容的次数，`/_usage/file-share/list` 汇总进入文件分享列表的次数，`/_usage/desk/form/customer` 汇总打开客户表单的次数。同一个功能下的不同单据共用一个统计 URL。未识别的自定义功能会归入 `other`。

正式站通过第一方导航脚本识别工作台路由。官方 Clarity 脚本只在权限隔离的空白统计页中运行，纯跳转、API 请求及上传文件内部的资源加载不单独计次。这个项目用于比较功能访问量；录屏和热图只会对应空白统计页，独立用户数也不适合用来统计员工人数。

## CRM 同站转换

本地 PostgreSQL 演练以虚构记录验证了 CRM Lead → CRM Deal → ERPNext Customer。使用该流程需要在 ERPNext 的 CRM Settings 启用 Frappe CRM 数据同步，并在 CRM 的 ERPNext CRM Settings 启用同站集成。CRM 16.0.4 保存该设置时会创建关联字段，并向 Sales User、Sales Manager 配置 Item 写入、创建、删除、分享及导出等权限。生产启用前须按 D-004 单独确认角色范围，安装应用不会自动启用该设置。

## 默认邮件

站点管理员可在 `/desk/email-template` 编辑「BizBase · 新用户欢迎」和「BizBase · 重置密码」，在 `/desk/system-settings` 的邮件页选择默认模板。邮箱一次性登录、邀请、安全提醒及其他内置模板随镜像发布。发信时统一在主题中显示「移山科技 数据中台(BizBase)」。HTML 邮件页脚内嵌移山科技官网标志并链接 `https://geokeji.com/`，纯文本页脚保留同一地址。标志取自官网页头 `https://static.geokeji.com/assets/yishan-logo-black.svg?v=2534beb544`，邮件使用其 PNG 版本。

首次启用新版邮件镜像时，在已有站点运行 `bench --site bizbase.geokeji.com execute yishan_id.mail_defaults.install` 创建上述两份记录并关闭框架宣传页脚。安装器保留同名模板已有正文。ERPNext 的物料收货及新会计年度通知另用 `env/bin/python /opt/bizbase-mail/localize_erp_mail.py --site bizbase.geokeji.com` 同步标准记录。两个操作都可重跑。使用 `env/bin/python /opt/bizbase-mail/check_mail_defaults.py bizbase.geokeji.com` 可用示例数据验证默认账号邮件，测试在邮件入队前截获内容。若管理员已自行修改内置文案，应相应调整验收断言。

## 移山 ID

发布包含 `managed.py` 的镜像及新版 Compose 时，将 `sync_yishan_id.py` 放在 `/opt/bizbase-prod/`，两个同名 service/timer 单元放在 `/etc/systemd/system/`。由 root 执行 `systemctl daemon-reload`、`systemctl start bizbase-yishan-id.service`、`systemctl enable --now bizbase-yishan-id.timer`，再用新版 Compose 重建应用容器。不要重跑建站脚本。

启用后只需编辑 `/etc/bizbase/connections.ini`（root:root，0600），不需要修改站点 JSON：

```ini
[yishan_id]
client_id =
client_secret =
```

约每分钟通过生产 issuer 的 RFC 7662 introspection 接口以 `client_secret_basic` 校验；服务端需允许本站客户端调用。无键、空值、拒绝或网络故障均不展示移山 ID。定时器停止时，最后成功的结果最多保留 150 秒。可手动运行 `systemctl start bizbase-yishan-id.service` 立即复查。校验不替代员工扫码和回调地址、权限的真实联调。该同步任务不轮换 PG/Redis 配置。
