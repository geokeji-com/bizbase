# BizBase 公网环境

入口为 `https://bizbase.geokeji.com`，站点同名。ECS 宿主机 Nginx 终止 TLS 并转发到 `127.0.0.1:3180`。Certbot 使用已有的定时器和本站专属 webroot，不在容器内另外签证书。

生产使用 `/opt/bizbase-prod/compose.yaml`，项目名 `bizbase-prod`；不要对其他项目执行 `down` 或主机级 prune。`docker compose ps` 在该目录执行。站点文件和附件在 `/var/lib/bizbase-prod/sites`，进程日志在 `/var/lib/bizbase-prod/logs`。

RDS 数据库 `bizbase` 的业务表只放在 `bizbase_app` schema，不需要 `public` 的 CREATE 权限。共享 Redis 分配 DB 2（缓存）与 DB 4（队列），bench ID 是 `bizbase-prod`。逻辑库隔离键，不隔离内存、连接数和 Pub/Sub；不要更改实例级配置或执行 FLUSHALL。数据库和 Redis 均不由此 Compose 启停。

`/etc/bizbase/connections.ini` 是首次准备站点的输入，修改它不会自动轮换站点凭据。`prepare_host.py` 和 `first_install.sh` 仅供**首次安装**使用，不能用来升级或重置密码。运行中的应用从受限的 `common_site_config.json` 和 `site_config.json` 读取设置，不要粘贴这些文件、cookie、连接串或完整诊断日志。

初始账号为 `Administrator`。管理员在自己的 ECS root 终端查看 `/etc/bizbase/initial-admin-password`，首次登录后在 Desk 改密并妥善保管；改密后初始密码文件和首次登录测试将不再有效。移山 ID 未登记前保留账号密码登录；域名登记的回调路径是 `/api/method/yishan_id_login.auth.callback`。

升级或录入正式业务数据前，确认 RDS 备份覆盖和可恢复性，并为附件、站点配置（含加密密钥）配置受保护的异机备份和恢复演练。只有数据库快照不能恢复附件与密钥。

## 可选：移山 ID 登录

发布包含 `managed.py` 的镜像及新版 Compose 时，将 `sync_yishan_id.py` 放在 `/opt/bizbase-prod/`，两个同名 service/timer 单元放在 `/etc/systemd/system/`。由 root 执行 `systemctl daemon-reload`、`systemctl start bizbase-yishan-id.service`、`systemctl enable --now bizbase-yishan-id.timer`，再用新版 Compose 重建应用容器。不要重跑建站脚本。

启用后只需编辑 `/etc/bizbase/connections.ini`（root:root，0600），不需要修改站点 JSON：

```ini
[yishan_id]
client_id =
client_secret =
```

约每分钟通过生产 issuer 的 RFC 7662 introspection 接口以 `client_secret_basic` 校验；服务端需允许本站客户端调用。无键、空值、拒绝或网络故障均不展示移山 ID。定时器停止时，最后成功的结果最多保留 150 秒。可手动运行 `systemctl start bizbase-yishan-id.service` 立即复查。校验不替代员工扫码和回调地址、权限的真实联调。该同步任务不轮换 PG/Redis 配置。
