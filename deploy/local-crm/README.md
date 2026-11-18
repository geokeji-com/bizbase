# 本地 BizBase + ERPNext + Frappe CRM + Frappe HR 预览

本配置在 `pwd.yml` 的本地演示环境上增加独立 Frappe CRM 和 Frappe HR，共用现有 `bizbase` 站点、数据库和文件卷。它不代表生产部署方案。

## 固定版本

| 组件 | 版本 |
| --- | --- |
| Frappe | 16.56.0，沿用基础镜像 |
| ERPNext | 16.55.0 |
| Frappe CRM | 16.0.4 |
| CRM 提交 | `9ace234fceb3c5e7bd630b74f44ba1779e831abe` |
| Frappe HR | 16.54.1 |
| HR 提交 | `a01032350ba1b799345b862cb122fa408bf6780e` |
| BizBase | 0.0.1，空 App |
| 当前运行镜像 | `bizbase/local:0.0.1` |

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

以上构建 CRM 基础镜像。当前覆盖配置使用含 HR 的镜像，还需执行：

```bash
rtk proxy git clone --depth 1 --branch v16.54.1 https://github.com/frappe/hrms.git \
  "$HOME/.cache/bizbase-hr-build/hrms"
rtk proxy docker build --progress plain -f deploy/local-crm/Containerfile.hr \
  -t bizbase/erpnext-crm-hr:16.55.0-16.0.4-16.54.1 "$HOME/.cache/bizbase-hr-build"
```

HR 此版本要求 Frappe、ERPNext `>=16.50.0,<17.0.0`，当前组合满足。已有源码缓存时无需重新克隆。需要代理时，Git 使用本机 `HTTPS_PROXY`；Docker 构建可增加 `--build-arg HTTP_PROXY=... --build-arg HTTPS_PROXY=...`，地址必须能从 Docker 虚拟机访问。代理不写入运行时配置。

## 启动与访问

在上述 HR 镜像基础上构建 BizBase 镜像（构建上下文仅包含 App 源码）：

```bash
rtk proxy docker build --progress plain -f deploy/local-crm/Containerfile.bizbase \
  -t bizbase/local:0.0.1 apps/bizbase
```

覆盖配置将仓库 `apps/bizbase` 挂载到应用容器同名目录；后端可写，Nginx 只读。该目录不存在时启动失败，不会静默创建空目录覆盖 App。镜像使用 editable Python 安装，因此容器重建后仍能加载挂载的源码。修改 Python 代码后重启相应后端/worker；更改依赖时重新构建镜像。

**安装 CRM / HR / BizBase 后，启动必须同时带上本目录的覆盖文件。单独使用 `pwd.yml` 会恢复为缺少这些 App 代码的上游镜像。此覆盖文件用于本机开发，不作为生产发布配置。**

```bash
docker compose -p bizbase -f pwd.yml -f deploy/local-crm/compose.override.yaml up -d
```

- Frappe HR：<http://127.0.0.1:8080/desk/hr-setup>
- BizBase 空工作区：<http://127.0.0.1:8080/desk/bizbase>
- Build：<http://127.0.0.1:8080/desk/build>
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


## HR 安装及验证（2026-11-18）

用户同意把官方 HR 应用装入现有预览。沿用 `bizbase` / `frontend` / 8080，未新建站点、数据库或业务 App。

- 已构建固定版本镜像、执行 `install-app hrms`、`migrate`、`clear-cache`，恢复维护模式外访问及 scheduler、两个队列 worker。
- 基础 CRM 镜像 ID：`sha256:0ffc5fd8061155bbc89c74361ae65b00eea560c36a7828b4e2d5a9012464ffa2`；HR 镜像 ID：`sha256:414d6388d1eab2e50b41c723fb59cfc30dad85e5a9836ca5e6b7775291d946ee`。
- `pip check`、数据库迁移、`bench doctor` 通过；后台搜索索引及 HR 面试提醒任务成功运行。未创建员工、候选人或业务测试记录。
- 浏览器现有登录会话实测应用首页、HR 工作台、员工列表、新建员工表单、招聘工作区和候选人列表；管理员 HTTP 会话访问 CRM、HR 自助端、HR 工作台、Build 均返回 200。HR JS/CSS/图标资源返回 200。未做工资核算或完整审批流程验收。
- 安装前后：用户 3、公司 1、联系人 1；客户、ERP 线索/商机、销售订单、项目、员工、CRM 线索/商机均为 0。原有 21 个 Custom Field 的完整记录哈希未变；HR 官方安装新增 37 个字段，共 58 个。自定义 DocType 数量维持 0。
- 修正上游 Nginx 模板在固定站点名时重写 Socket.IO Origin 的问题：`nginx.conf.template` 保留原请求 Origin，仍由 Frappe 校验其与 Host 一致，不关闭来源验证。模板通过 frontend 的只读挂载持久化。已验证 localhost 来源通过来源检查，异源仍返回 `Invalid origin`。
- 安装前数据库、站点配置及公私附件备份已复制至 `/Users/aij/.codex/private/bizbase-hr-20261118/backup/`，并检查 gzip/tar/JSON 可读性；SHA256、前后快照和迁移日志位于该私有目录。不纳入 Git，未实际演练恢复。

已有站点首次安装 HR 时，沿用上面的备份及维护流程，在镜像切换后运行 `bench --site frontend install-app hrms` 和 `bench --site frontend migrate`。只重启已安装站点无需再次安装。

恢复安装前状态必须同时恢复安装前数据库、站点配置、公私附件，再切回 `bizbase/erpnext-crm:16.55.0-16.0.4`；保留原数据库和站点卷，不使用 `down -v`。当前无恢复需要。

员工数据、假期政策、审批角色、薪资及国内税社保规则尚未配置；官方界面部分文案仍为英文。本次仅安装并验证基础可用性。

## 空 BizBase App 与 Build（2026-11-18，D-014）

沿用原 `bizbase` Compose 项目、`frontend` 站点及数据卷。App 源码见 [apps/bizbase](../../apps/bizbase/README.md)，仅提供 `BizBase` 标准模块和空工作区；不包含已撤回的客户目录实现，不接入生产。

首次安装：先按上文完成备份并停止 scheduler/worker，再切换应用镜像；无需重建数据库或 Redis。执行：

```bash
rtk proxy docker exec bizbase-backend-1 bench --site frontend install-app bizbase
rtk proxy docker exec bizbase-backend-1 bench --site frontend migrate
rtk proxy docker exec bizbase-backend-1 bench --site frontend set-config developer_mode 1
rtk proxy docker exec bizbase-backend-1 bench --site frontend clear-cache
```

随后重启后端、WebSocket，关闭维护模式并启动 scheduler/worker。开发模式仅设在本站点配置中，不修改镜像的全局默认。不要把本配置用于对外生产站点。

在 Build 新建 DocType 时，确认 `Custom` 未勾选并选择 `BizBase` 模块，标准定义才会进入仓库的 App 目录。站点级自定义配置需明确选择导出方式，详见 App README。源码变更需要检查、提交、推送，界面保存不等于自动提交 Git。

安装前的私有备份、数据摘要及验证记录位于 `/Users/aij/.codex/private/bizbase-empty-app-20261118/`，不进入 Git。恢复时须使用同一检查点的数据库、配置与附件，并恢复本次安装前的 HR 镜像及覆盖配置；不可只切回镜像。未进行恢复演练。

本次验证结果：

- `list-apps` 包含 `bizbase 0.0.1` 和原四个 App；迁移、`pip check`、`bench doctor` 通过，两个 worker 在线，维护模式已关闭。
- 保存标准工作区成功写回本机 `apps/bizbase/bizbase/bizbase/workspace/bizbase/bizbase.json`。重新创建应用容器后，App 可加载、开发模式保留、源码挂载可写、图标 HTTP 200、ping 返回 pong。
- 浏览器现有登录会话验证应用首页的 BizBase 入口、空工作区，以及 Build 新建 DocType 弹窗中的 BizBase 模块候选；未提交测试 DocType。App 中业务 DocType 为 0。
- 原用户 3、公司 1、联系人 1；客户、ERP/CRM 线索与商机、销售订单、项目、员工仍为 0。58 个 Custom Field 和 197 个 Property Setter 的完整记录摘要保持不变；数据库和 Redis 容器 ID 未变。
- 空工作区和 App 入口限 System Manager；已检查 Administrator 可见、Guest 不可见。后续业务数据权限尚未配置或验收。
- 原 HR 备份子目录 `sites/frontend/private/backups/pre-hr-20261118` 导致 Frappe 备份清理函数报 `IsADirectoryError`。已保留并移到 `sites/frontend/private/pre-hr-20261118`；新备份成功复制到宿主机私有目录并验证 gzip/tar/JSON 可读性。
