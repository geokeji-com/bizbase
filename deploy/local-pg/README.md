# PostgreSQL 本地开发站

独立 Compose 项目 `bizbase-dev-pg`。站点名 `frontend`，但数据库、缓存、队列、附件和日志均不与旧 MariaDB 项目共用。默认仅监听 `127.0.0.1:8080`。需要并行预览时设 `BIZBASE_DEV_PORT=18080`。只对本文件运行 Compose，不叠加旧的 `pwd.yml`。

1. 安装 Yarn Classic、Node 22.12+ 和支持 named build context 的 Docker BuildKit。先按 [CRM 构建说明](../local-crm/README.md) 准备 `bizbase/erpnext-crm:16.55.0-16.0.4` 基础镜像；不要选带 HR 的镜像。仓库根目录运行 `rtk proxy bash deploy/local-pg/build.sh`。脚本从指定的 Insights 提交和锁文件构建资源，四处 PostgreSQL 兼容改动按源码摘要校验。宿主机编译静态资源，Python 依赖在目标 Linux 容器安装。两个上游源码归档均检查 SHA-256。
2. 为本地开发单独准备两个随机密码文件，保存在仓库外。下列命令不会覆盖已有密钥；外层目录仅当前用户可访问，文件需对容器的 root 组可读：

   ```bash
   rtk proxy bash -ec 'umask 077; d=${BIZBASE_DEV_SECRETS:-$HOME/.local/share/bizbase-dev-pg}; mkdir -p "$d"; chmod 700 "$d"; for k in db_root admin_password; do test -s "$d/$k" || openssl rand -hex 32 > "$d/$k"; chmod 640 "$d/$k"; done'
   ```

3. 首次初始化时只启动数据库和 Redis。重复迁移时先停止本项目的 frontend、backend、worker、scheduler 和 websocket，为全站 migrate 留出内存，再执行以下命令。

   ```bash
   rtk proxy docker compose -f deploy/local-pg/compose.yaml run --rm setup
   rtk proxy docker compose -f deploy/local-pg/compose.yaml up -d
   rtk proxy docker compose -f deploy/local-pg/compose.yaml exec -T backend bench --site frontend list-apps
   rtk proxy docker compose -f deploy/local-pg/compose.yaml exec -T backend env/bin/python - < deploy/local-pg/verify.py
   rtk proxy curl -fsS http://127.0.0.1:8080/api/method/ping
   ```

   安装清单为 frappe、ERPNext、CRM、移山 ID、文件分享、管理/销售/运营/客户四个看板与 Insights；没有 HRMS 或 GEO 运营。管理员账号 `Administrator`，密码仅在本机密码文件中查看。业务数据库只在 Compose 网络可达。六个自研应用以源码目录绑定给 bench，Build 标准定义可回写仓库。变更 Python 依赖或静态资源须重建镜像。

4. 新站首次进入 Desk 会打开设置向导。此开发站使用虚构公司「BizBase 本地测试公司」、人民币、上海时区和标准科目表。新建空卷时通过向导完成本地设置后即可进入两行应用屏。备用旧站的容器与卷仍然保留。需要恢复旧站时先停止本项目，再启动旧 `bizbase` 项目的既有容器。
