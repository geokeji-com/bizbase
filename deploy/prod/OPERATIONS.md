# BizBase 公网环境

入口为 `https://bizbase.geokeji.com`，站点同名。ECS 宿主机 Nginx 终止 TLS 并转发到 `127.0.0.1:3180`。Certbot 使用已有的定时器和本站专属 webroot，不在容器内另外签证书。

生产使用 `/opt/bizbase-prod/compose.yaml`，项目名 `bizbase-prod`；不要对其他项目执行 `down` 或主机级 prune。`docker compose ps` 在该目录执行。站点文件和附件在 `/var/lib/bizbase-prod/sites`，进程日志在 `/var/lib/bizbase-prod/logs`。

RDS 数据库 `bizbase` 的业务表只放在 `bizbase_app` schema，不需要 `public` 的 CREATE 权限。共享 Redis 分配 DB 2（缓存）与 DB 4（队列），bench ID 是 `bizbase-prod`。逻辑库隔离键，不隔离内存、连接数和 Pub/Sub；不要更改实例级配置或执行 FLUSHALL。数据库和 Redis 均不由此 Compose 启停。

`/etc/bizbase/connections.ini` 是首次准备站点的输入，修改它不会自动轮换站点凭据。`prepare_host.py` 和 `first_install.sh` 仅供**首次安装**使用，不能用来升级或重置密码。运行中的应用从受限的 `common_site_config.json` 和 `site_config.json` 读取设置，不要粘贴这些文件、cookie、连接串或完整诊断日志。

初始账号为 `Administrator`。管理员在自己的 ECS root 终端查看 `/etc/bizbase/initial-admin-password`，首次登录后在 Desk 改密并妥善保管；改密后初始密码文件和首次登录测试将不再有效。移山 ID 未登记前保留账号密码登录；域名登记的回调路径是 `/api/method/yishan_id_login.auth.callback`。

升级或录入正式业务数据前，确认 RDS 备份覆盖和可恢复性，并为附件、站点配置（含加密密钥）配置受保护的异机备份和恢复演练。只有数据库快照不能恢复附件与密钥。

## 已有站点首次加入 ERPNext 与文件分享

1. 在获准的隔离 RDS 测试库演练安装、迁移及恢复。生产维护前记录当前镜像 ID、站点已装应用、Compose 配置和持久卷 `sites/apps.txt`。核对 RDS 恢复点并保留同一检查点的站点配置、密钥及附件备份。
2. 在维护窗口开启站点维护模式，停止本站 worker 和 scheduler，完成一致性备份。将已验证的新镜像设为本站 `BIZBASE_IMAGE`。在宿主机持久化的 `/var/lib/bizbase-prod/sites/apps.txt` 保留原有应用，各追加一行缺失的 `erpnext`、`static_share`。切换 backend 后用 `bench --site bizbase.geokeji.com list-apps` 核对起点。
3. 在新 backend 中仅对缺失应用依次运行 `bench --site bizbase.geokeji.com install-app erpnext` 和 `bench --site bizbase.geokeji.com install-app static_share`。随后执行 `bench --site bizbase.geokeji.com migrate`、`bench --site bizbase.geokeji.com clear-cache`。保留现有用户、绑定和站点配置。
4. 用同一镜像恢复全部五个服务，关闭维护模式。从 HTTPS 入口验证登录、ERPNext 资源、Employee 和分享权限。若迁移失败，在维护模式下恢复同一检查点的数据库、站点文件、应用清单、Compose 配置与旧镜像。

管理入口为 `/file-share`（文件分享）和 `/yishan-id`（移山 ID）。新生成的文件分享链接使用 `/file-share/<ID>`；旧 `/s/<ID>` 及已有 Desk 管理书签继续可用。

## 功能访问统计

在 [Microsoft Clarity 项目](https://clarity.microsoft.com/projects/view/uy7jcuzycs/dashboard) 中查看 `/_usage/` 下各页面的浏览量。`/_usage/file-share/view` 汇总打开分享内容的次数，`/_usage/file-share/list` 汇总进入文件分享列表的次数，`/_usage/desk/form/customer` 汇总打开客户表单的次数。同一个功能下的不同单据共用一个统计 URL。未识别的自定义功能会归入 `other`。

正式站通过第一方导航脚本识别工作台路由。官方 Clarity 脚本只在权限隔离的空白统计页中运行，纯跳转、API 请求及上传文件内部的资源加载不单独计次。这个项目用于比较功能访问量；录屏和热图只会对应空白统计页，独立用户数也不适合用来统计员工人数。

## 移山 ID

发布包含 `managed.py` 的镜像及新版 Compose 时，将 `sync_yishan_id.py` 放在 `/opt/bizbase-prod/`，两个同名 service/timer 单元放在 `/etc/systemd/system/`。由 root 执行 `systemctl daemon-reload`、`systemctl start bizbase-yishan-id.service`、`systemctl enable --now bizbase-yishan-id.timer`，再用新版 Compose 重建应用容器。不要重跑建站脚本。

启用后只需编辑 `/etc/bizbase/connections.ini`（root:root，0600），不需要修改站点 JSON：

```ini
[yishan_id]
client_id =
client_secret =
```

约每分钟通过生产 issuer 的 RFC 7662 introspection 接口以 `client_secret_basic` 校验；服务端需允许本站客户端调用。无键、空值、拒绝或网络故障均不展示移山 ID。定时器停止时，最后成功的结果最多保留 150 秒。可手动运行 `systemctl start bizbase-yishan-id.service` 立即复查。校验不替代员工扫码和回调地址、权限的真实联调。该同步任务不轮换 PG/Redis 配置。
