# 本地 ERPNext + Frappe CRM 预览

本配置在 `pwd.yml` 的本地演示环境上增加独立 Frappe CRM，共用现有 `bizbase` 站点、数据库和文件卷。它不代表生产部署方案。

## 固定版本

| 组件 | 版本 |
| --- | --- |
| Frappe | 16.56.0，沿用基础镜像 |
| ERPNext | 16.55.0 |
| Frappe CRM | 16.0.4 |
| CRM 提交 | `9ace234fceb3c5e7bd630b74f44ba1779e831abe` |
| 本地镜像 | `bizbase/erpnext-crm:16.55.0-16.0.4` |

基础镜像摘要固定在 `Containerfile` 中。CRM 的该版本声明支持 Frappe `>=16.0.0,<17.0.0`；不使用 `develop` 分支。

## 构建

以下命令在项目根目录执行。源码缓存位于仓库外，构建会核对 CRM 提交。

```bash
mkdir -p "$HOME/.cache/bizbase-crm-build"
git clone --depth 1 --branch v16.0.4 https://github.com/frappe/crm.git \
  "$HOME/.cache/bizbase-crm-build/crm"

docker build --progress plain \
  -f deploy/local-crm/Containerfile \
  -t bizbase/erpnext-crm:16.55.0-16.0.4 \
  "$HOME/.cache/bizbase-crm-build"
```

已有源码缓存时无需重新克隆。需要代理时，Git 使用本机 `HTTPS_PROXY`；Docker 构建可增加 `--build-arg HTTP_PROXY=... --build-arg HTTPS_PROXY=...`，地址必须能从 Docker 虚拟机访问。代理不写入运行时配置。

## 启动与访问

**安装 CRM 后，启动必须同时带上本目录的覆盖文件。单独使用 `pwd.yml` 会恢复为不包含 CRM 代码的上游镜像。**

```bash
docker compose -p bizbase -f pwd.yml -f deploy/local-crm/compose.override.yaml up -d
```

- 独立 CRM：<http://localhost:8080/crm>
- ERPNext：<http://localhost:8080/desk>
- ERPNext 原有 CRM：<http://localhost:8080/desk/crm>

使用现有站点账号登录。安装独立 CRM 不自动删除旧 CRM，也不自动配置客户同步、邮件、电话或第三方渠道。

也可在 `/desk` 应用首页点击“客户关系”进入独立 CRM。首次引导中的邮件、数据导入和邀请成员已跳过，可在设置中继续；已关闭可选的使用数据分享。

## 本机验证记录（2026-11-17）

- 已完成镜像构建、Python 依赖检查、站点安装和数据库迁移。
- 已通过现有登录会话打开线索列表、新建线索表单、商机列表及 ERPNext 主页，未创建测试业务记录。
- CRM 设置中可见 ERPNext 集成入口，当前未启用。
- 安装前后公司数量均为 1、用户数量均为 3；原客户、线索、商机、销售订单和项目数量均保持为 0。
- CRM 搜索索引已成功构建；维护模式已关闭，后台任务恢复运行。
- 安装前数据库、配置和文件备份已复制到本机私有目录 `/Users/aij/.codex/private/bizbase-crm-20261117/`，不纳入 Git。

## 首次将 CRM 安装到已有站点

构建镜像仅提供应用代码。已有站点还需要执行一次安装；重启时不需要重复安装。

1. 在原镜像中执行 `bench --site frontend set-maintenance-mode on`，停止 scheduler、queue-long、queue-short；执行 `bench --site frontend backup --with-files`，将备份复制到站点卷以外的私有目录。
2. 使用上述覆盖文件切换 configurator、backend、frontend、websocket 的镜像，确认 configurator 成功退出；安装期间保持后台任务停止。
3. 在新 backend 容器执行：

```bash
docker compose -p bizbase -f pwd.yml -f deploy/local-crm/compose.override.yaml \
  exec -T backend bench --site frontend install-app crm
docker compose -p bizbase -f pwd.yml -f deploy/local-crm/compose.override.yaml \
  exec -T backend bench --site frontend migrate
docker compose -p bizbase -f pwd.yml -f deploy/local-crm/compose.override.yaml \
  exec -T backend bench --site frontend clear-cache
```

4. 重启 backend、websocket，关闭维护模式，再启动后台任务进程，检查已安装应用列表、CRM 页面和 ERPNext 页面。

## 停止与排查

```bash
docker compose -p bizbase -f pwd.yml -f deploy/local-crm/compose.override.yaml stop
docker compose -p bizbase -f pwd.yml -f deploy/local-crm/compose.override.yaml ps -a
docker compose -p bizbase -f pwd.yml -f deploy/local-crm/compose.override.yaml logs --tail 100 backend
```

保留数据库和文件卷；不要使用 `down -v`。安装失败时应先检查日志。恢复安装前状态需要同时恢复安装前的数据库、配置和文件备份，再切回原镜像，不能仅切换镜像。
