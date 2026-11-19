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

## 排查：移山 ID 登录

正确的回调地址是 `https://bizbase.geokeji.com/api/method/yishan_id_login.auth.callback`，须与 Logto 中该应用登记的 redirect URI **完全一致**（含路径）。`sync_yishan_id.py` 只向本站发布 client 配置，不负责在 Logto 登记回调。

### 现象：`oidc.invalid_redirect_uri`

点击「通过移山 ID 登录」后，`https://id.geokeji.com/oidc/auth` 返回 400，正文含 `oidc.invalid_redirect_uri`。

常见原因是 Logto 应用 `bizbase-production-interactive`（Traditional，client_id `jv5k8bub90r30xnzesepi`）只登记了错误路径 `.../api/method/yishan_id.auth.callback`（缺少 `_login`），而本站实际发送的是 `.../api/method/yishan_id_login.auth.callback`。

处理：在 Logto 该应用的 Redirect URIs 中**增加**正确地址，不必改本站代码或环境变量。旧地址可保留。

验证（不要用 `-L` 跟随跳转）：

```bash
# 1. 读取 Location（其中 redirect_uri 应为 yishan_id_login.auth.callback）
curl -sS -D - -o /dev/null https://bizbase.geokeji.com/api/method/yishan_id_login.auth.start

# 2. 将上一步的 Location 整段作为 $AUTH_URL，请求 Logto
curl -sS -D - -o /tmp/oidc.body -A "Mozilla/5.0" "$AUTH_URL"
```

成功时 `/oidc/auth` 返回 **303**（通常 `Location` 为 `/direct/social/yishan-feishu`，或进入登录页）。失败时仍为 **400**，正文含 `invalid_redirect_uri`。

### 现象：「尚未绑定 BizBase 账号」

OIDC 已成功，但回调页提示移山 ID 尚未绑定 BizBase 账号。登录只按 `yishan.uid` 查找已启用的「移山 ID 绑定」，且该绑定指向的 User 必须已启用；不按邮箱或手机号自动匹配。`Administrator` 与 `Guest` 不能绑定。

常见原因是人员导入后，对应的 User 和「移山 ID 绑定」被关闭（`enabled=0`），或尚未选择用户。

处理（Desk，需 System Manager）：打开「移山 ID 绑定」，为该 `yishan.uid` 选择用户并勾选启用；同时在用户列表中启用该 User，并赋予所需角色（至少能登录 Desk；管理员另加 System Manager）。也可让员工先登录一次，再在自动登记的未启用记录上补全并启用。不要改绑定到 `Administrator`。

### 2026-11-20 处理记录

均为配置与数据变更，**未改应用代码、未合并分支、未重启业务容器**。时间均为 Asia/Shanghai。

1. 回调地址：当日 06:47 在 Logto 应用 `bizbase-production-interactive` 的 `redirectUris` 中增加正确回调，并保留原先的错误路径。备份（不含 secret 列）：移山 ID 宿主机 `/opt/yishan-id/backups/bizbase-interactive-redirect-20261120-064736/`。验证：`/oidc/auth` 由 400 `invalid_redirect_uri` 变为 303。
2. 账号绑定：当日 06:57 启用已有但被关闭的 User 与对应「移山 ID 绑定」，并授予 System Manager、Desk User。备份（口令与 API 密钥已剔除）：BizBase 宿主机 `/root/backups/bizbase-enable-lizecen-20261120-065752/`。处理后该绑定已启用，且 User 已启用。
