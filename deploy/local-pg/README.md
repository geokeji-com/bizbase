# PostgreSQL 本地开发站

独立 Compose 项目 `bizbase-dev-pg`。站点名 `frontend`，但数据库、缓存、队列、附件和日志均不与旧 MariaDB 项目共用。默认仅监听 `127.0.0.1:8080`。需要并行预览时设 `BIZBASE_DEV_PORT=18080`。只对本文件运行 Compose，不叠加旧的 `pwd.yml`。

1. 安装 Yarn Classic、Node 22.12+ 和支持 named build context 的 Docker BuildKit。先按 [CRM 构建说明](../local-crm/README.md) 准备 `bizbase/erpnext-crm:16.55.0-16.0.4` 基础镜像；不要选带 HR 的镜像。仓库根目录运行 `rtk proxy bash deploy/local-pg/build.sh`。脚本从指定的 Insights 提交和锁文件构建资源，四处 PostgreSQL 兼容改动按源码摘要校验。宿主机编译静态资源，Python 依赖在目标 Linux 容器安装。两个上游源码归档均检查 SHA-256。
2. 为本地开发单独准备两个随机密码文件，保存在仓库外。下列命令不会覆盖已有密钥；外层目录仅当前用户可访问，文件需对容器的 root 组可读：

   ```bash
   rtk proxy bash -ec 'umask 077; d=${BIZBASE_DEV_SECRETS:-$HOME/.local/share/bizbase-dev-pg}; mkdir -p "$d"; chmod 700 "$d"; for k in db_root admin_password; do test -s "$d/$k" || openssl rand -hex 32 > "$d/$k"; chmod 640 "$d/$k"; done'
   ```

3. **已有 `bizbase_mgmt` 站点**先按[管理看板更名手册](../prod/management-board-migration.md)停写、备份、改数据库身份和共享清单；不能直接跑 setup 或另装新 App。首次初始化时只启动数据库和 Redis。重复迁移时先停止本项目的 frontend、backend、worker、scheduler 和 websocket，为全站 migrate 留出内存，再执行以下命令。

   ```bash
   rtk proxy docker compose -f deploy/local-pg/compose.yaml run --rm setup
   rtk proxy docker compose -f deploy/local-pg/compose.yaml up -d
   rtk proxy docker compose -f deploy/local-pg/compose.yaml exec -T backend bench --site frontend list-apps
   rtk proxy docker compose -f deploy/local-pg/compose.yaml exec -T backend env/bin/python - < deploy/local-pg/verify.py
   rtk proxy curl -fsS http://127.0.0.1:8080/api/method/ping
   ```

   新站使用 ERPNext 内置 CRM（销售人员从 ERP 卡片进入）。独立 CRM 仅在待迁移的旧站保留。安装清单为 frappe、ERPNext、移山 ID、文件分享、管理/销售/运营/客户四个看板与 Insights。管理员账号 `Administrator`，密码仅在本机密码文件中查看。业务数据库只在 Compose 网络可达。六个自研应用以源码目录绑定给 bench，Build 标准定义可回写仓库。变更 Python 依赖或静态资源须重建镜像。

### 文件分享的本地域名验收

已有分享的开发站升级前，先核实原报告实际使用的外部地址；如果是默认回环地址，在该站设置 `file_share_primary_origin` 为 `http://127.0.0.1:8080` 再 migrate。不要用生产或新渠道域名代替旧地址。无需碰现有开发站的真实数据库验收可在仓库根运行 `rtk proxy bash deploy/local-pg/share-qa/run.sh`；脚本使用随机项目名、无外部端口的一次性 PG 站点，验证后回收。

无需公网 DNS。准备只在开发机使用的三个名称（例如 `company.localhost`、`channel-a.localhost` 和 `channel-b.localhost`）。名单文件只写一行 `server_name company.localhost channel-a.localhost channel-b.localhost;`。使用含新版内层代理模板的镜像；在本机 Compose override 中按[生产文档的 configs 示例](../prod/OPERATIONS.md#逐个接入文件分享域名多域名版发布后)，把名单只读挂到 **frontend** 的 `/etc/nginx/bizbase-share-domains/allowed.conf`，然后在获准的预览环境中一起加载基础和 override 配置。源码挂载不包含已烘入镜像的 Nginx 模板。未知 Host 由默认虚拟主机返回 404；`localhost` 和 `127.0.0.1` 保留用于本地 Desk 和探活，不代表任一报告自动允许这些域名。

可用 `rtk proxy curl --resolve company.localhost:8080:127.0.0.1 http://company.localhost:8080/file-share/s/<测试ID>` 分别验证三个入口（先将命令中的 `<测试ID>` 换成实际 ID）。只有在 App 中启用且报告已开放的域名才能看到内容。浏览器验收密码、沙箱 Cookie 或员工登录时使用受信任的 HTTPS 或支持相应 Cookie 策略的 loopback 环境；`curl` 打开外壳成功不等于完成浏览器验收。

### 浏览器首次设置

新站首次进入 Desk 会打开设置向导。此开发站使用虚构公司「BizBase 本地测试公司」、人民币、上海时区和标准科目表。新建空卷时通过向导完成本地设置后即可进入两行应用屏。备用旧站的容器与卷仍然保留。需要恢复旧站时先停止本项目，再启动旧 `bizbase` 项目的既有容器。
