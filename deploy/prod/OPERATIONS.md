# BizBase 公网环境

入口为 `https://bizbase.geokeji.com`，站点同名。ECS 宿主机 Nginx 终止 TLS 并转发到 `127.0.0.1:3180`。Certbot 使用已有的定时器和本站专属 webroot，不在容器内另外签证书。

生产使用 `/opt/bizbase-prod/compose.yaml`，项目名 `bizbase-prod`；不要对其他项目执行 `down` 或主机级 prune。`docker compose ps` 在该目录执行。站点文件和附件在 `/var/lib/bizbase-prod/sites`，进程日志在 `/var/lib/bizbase-prod/logs`。

RDS 数据库 `bizbase` 的业务表只放在 `bizbase_app` schema，不需要 `public` 的 CREATE 权限。共享 Redis 分配 DB 2（缓存）与 DB 4（队列），bench ID 是 `bizbase-prod`。逻辑库隔离键，不隔离内存、连接数和 Pub/Sub；不要更改实例级配置或执行 FLUSHALL。数据库和 Redis 均不由此 Compose 启停。

`/etc/bizbase/connections.ini` 是首次准备站点的输入，修改它不会自动轮换站点凭据。`prepare_host.py` 和 `first_install.sh` 仅供**首次安装**使用，不能用来升级或重置密码。运行中的应用从受限的 `common_site_config.json` 和 `site_config.json` 读取设置，不要粘贴这些文件、cookie、连接串或完整诊断日志。

初始账号为 `Administrator`。管理员在自己的 ECS root 终端查看 `/etc/bizbase/initial-admin-password`，首次登录后在 Desk 改密并妥善保管；改密后初始密码文件和首次登录测试将不再有效。移山 ID 未登记前保留账号密码登录；域名登记的回调路径是 `/api/method/yishan_id_login.auth.callback`。

升级或录入正式业务数据前，确认 RDS 备份覆盖和可恢复性，并为附件、站点配置（含加密密钥）配置受保护的异机备份和恢复演练。只有数据库快照不能恢复附件与密钥。

## 发布

日常发布用 `/opt/bizbase-prod/deploy.sh` 做蓝绿切换，不再对运行中的项目执行 `docker compose up`，原地重建容器会让入口 502 数十秒。两套槽位 `bizbase-prod-blue`（3181）和 `bizbase-prod-green`（3182）共用站点目录、数据库与 Redis。脚本先在空闲槽位启动 web 进程，健康检查和冒烟测试通过后改写宿主机 Nginx 的 upstream 并 reload，然后交接 worker 与 scheduler。旧槽位 web 进程保留，可秒级回滚。尚未切换过的原 `bizbase-prod` 项目（3180）视为第一个槽位。

按改动选择方式：

| 类型 | 改动 | 做法 |
| --- | --- | --- |
| A | 仅代码、模板、自定义应用静态文件 | `deploy.sh release IMAGE` |
| B | 只新增 DocType、字段、索引，旧代码可在新结构上运行 | `deploy.sh release IMAGE --migrate`，迁移时旧槽位继续服务 |
| C | 删除、重命名字段或改类型 | 拆成多次 B：先加新结构并双写，迁移数据，最后一次发布再删旧结构 |
| D | 升级 Frappe/ERPNext、新装应用、改共享配置 | 维护窗口，见下文 |

Frappe/ERPNext 资源清单（`assets/assets.json`）与运行中镜像不同，或镜像比站点 `apps.txt` 多出应用时，脚本拒绝发布。两个槽位共用 Redis 中的资源清单，只能在维护窗口里换。

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

按「已有站点首次加入 ERPNext 与文件分享」的顺序执行，命令改用 `deploy.sh compose`，`BIZBASE_IMAGE` 改写在当前槽位的 env 文件中。若只需短暂禁止写入，可在站点配置同时设置 `maintenance_mode` 和 `allow_reads_during_maintenance`，期间仍可浏览，写入时报维护中。

## 已有站点首次加入 ERPNext 与文件分享

1. 在获准的隔离 RDS 测试库演练安装、迁移及恢复。生产维护前记录当前镜像 ID、站点已装应用、Compose 配置和持久卷 `sites/apps.txt`。核对 RDS 恢复点并保留同一检查点的站点配置、密钥及附件备份。
2. 在维护窗口开启站点维护模式，停止本站 worker 和 scheduler，完成一致性备份。将已验证的新镜像设为本站 `BIZBASE_IMAGE`。在宿主机持久化的 `/var/lib/bizbase-prod/sites/apps.txt` 保留原有应用，各追加一行缺失的 `erpnext`、`static_share`。切换 backend 后用 `bench --site bizbase.geokeji.com list-apps` 核对起点。
3. 在新 backend 中仅对缺失应用依次运行 `bench --site bizbase.geokeji.com install-app erpnext` 和 `bench --site bizbase.geokeji.com install-app static_share`。随后执行 `bench --site bizbase.geokeji.com migrate`、`bench --site bizbase.geokeji.com clear-cache`。保留现有用户、绑定和站点配置。
4. 用同一镜像恢复全部五个服务，关闭维护模式。从 HTTPS 入口验证登录、ERPNext 资源、Employee 和分享权限。若迁移失败，在维护模式下恢复同一检查点的数据库、站点文件、应用清单、Compose 配置与旧镜像。

管理入口为 `/file-share`（文件分享）和 `/yishan-id`（移山 ID）。新生成的文件分享链接使用 `/file-share/<ID>`；旧 `/s/<ID>` 及已有 Desk 管理书签继续可用。

## 功能访问统计

在 [Microsoft Clarity 项目](https://clarity.microsoft.com/projects/view/uy7jcuzycs/dashboard) 中查看 `/_usage/` 下各页面的浏览量。`/_usage/file-share/view` 汇总打开分享内容的次数，`/_usage/file-share/list` 汇总进入文件分享列表的次数，`/_usage/desk/form/customer` 汇总打开客户表单的次数。同一个功能下的不同单据共用一个统计 URL。未识别的自定义功能会归入 `other`。

正式站通过第一方导航脚本识别工作台路由。官方 Clarity 脚本只在权限隔离的空白统计页中运行，纯跳转、API 请求及上传文件内部的资源加载不单独计次。这个项目用于比较功能访问量；录屏和热图只会对应空白统计页，独立用户数也不适合用来统计员工人数。

## 默认邮件

站点管理员可在 `/desk/email-template` 编辑「BizBase · 新用户欢迎」和「BizBase · 重置密码」，在 `/desk/system-settings` 的邮件页选择默认模板。邮箱一次性登录、邀请、安全提醒及其他内置模板随镜像发布。发信时统一在主题中显示「移山科技 数据中台(BizBase)」。HTML 邮件页脚内嵌移山科技官网标志并链接 `https://geokeji.com/`，纯文本页脚保留同一地址。标志取自官网页头 `https://static.geokeji.com/assets/yishan-logo-black.svg?v=2534beb544`，邮件使用其 PNG 版本。

首次启用新版邮件镜像时，在已有站点运行 `bench --site bizbase.geokeji.com execute yishan_id_login.mail_defaults.install` 创建上述两份记录并关闭框架宣传页脚。安装器保留同名模板已有正文。ERPNext 的物料收货及新会计年度通知另用 `env/bin/python /opt/bizbase-mail/localize_erp_mail.py --site bizbase.geokeji.com` 同步标准记录。两个操作都可重跑。使用 `env/bin/python /opt/bizbase-mail/check_mail_defaults.py bizbase.geokeji.com` 可用示例数据验证默认账号邮件，测试在邮件入队前截获内容。若管理员已自行修改内置文案，应相应调整验收断言。

## 移山 ID

发布包含 `managed.py` 的镜像及新版 Compose 时，将 `sync_yishan_id.py` 放在 `/opt/bizbase-prod/`，两个同名 service/timer 单元放在 `/etc/systemd/system/`。由 root 执行 `systemctl daemon-reload`、`systemctl start bizbase-yishan-id.service`、`systemctl enable --now bizbase-yishan-id.timer`，再用新版 Compose 重建应用容器。不要重跑建站脚本。

启用后只需编辑 `/etc/bizbase/connections.ini`（root:root，0600），不需要修改站点 JSON：

```ini
[yishan_id]
client_id =
client_secret =
```

约每分钟通过生产 issuer 的 RFC 7662 introspection 接口以 `client_secret_basic` 校验；服务端需允许本站客户端调用。无键、空值、拒绝或网络故障均不展示移山 ID。定时器停止时，最后成功的结果最多保留 150 秒。可手动运行 `systemctl start bizbase-yishan-id.service` 立即复查。校验不替代员工扫码和回调地址、权限的真实联调。该同步任务不轮换 PG/Redis 配置。
