# 目录首版本地验收环境

仅用于第 01 轮本地验收，项目为 `bizbase-r01`，站点为 `bizbase-acceptance.localhost`。不复用现有 `bizbase` 项目的数据库、站点卷、账号或 8080 入口。

## 构建与启动

在仓库根目录执行：

```sh
rtk proxy python3 scripts/directory/bootstrap.py build
rtk proxy python3 scripts/directory/bootstrap.py up
rtk proxy python3 scripts/directory/bootstrap.py status
```

构建只复制 App、部署操作脚本和经摘要核对的构建后端 wheel 到临时上下文，不将仓库 `.env`、Git、私有样本或凭据发送给构建器。基础镜像、MariaDB、Redis 均固定摘要；应用标签由构建输入摘要生成。所有应用服务使用同一派生镜像。

本机生成的 ERPNext+CRM 镜像没有可从镜像源下载的 manifest。bootstrap 校验固定 image ID 后为其创建本项目专用别名，构建后再验证基础文件层前缀一致；不会因 registry 镜像源缺少这个私有名字而改用另一个版本。

脚本生成的数据库和 Administrator 凭据位于 `~/.codex/private/bizbase-round01/infra.env`，权限为 600，不打印值。它只供本轮环境初始化；不得借用现有站点凭据。实际构建记录为同目录 `build.json`。

计划入口为 `http://127.0.0.1:8081`。启动脚本检查该端口是否属于本项目，不占用其他项目的监听。数据库和 Redis 不映射宿主端口。调度器默认不启动；worker 只有明确启用 `workers` profile 才运行。

当前基础 Compose 不挂载真实数据。模型安装完成后，真实快照与业务功能按第 01 轮模型及服务阶段接入；登录页可达不代表业务验收通过。

## C 阶段私有数据挂载

模型和原型验证完成后，才执行：

```sh
rtk proxy python3 scripts/directory/bootstrap.py data
```

该入口启用 `compose.data.yaml`：一次性 root 进程以只读 bind 读取两个明确批准的 JSON，校验摘要后复制到独立 private-data 卷，文件属运行用户 1000 且模式 400。只有 backend 以只读方式挂载这个卷；frontend、构建上下文和镜像都没有真实数据。挂载不等于业务启用，目录仍需通过受控管理步骤激活版本和授权。

## 备份与停止

```sh
rtk proxy python3 scripts/directory/bootstrap.py backup
rtk proxy python3 scripts/directory/bootstrap.py stop
```

备份只针对本轮新站点，复制到站点卷之外的私有目录。停止保留全部卷，不使用 `down -v`。恢复须匹配应用镜像、数据库、站点配置与文件，不能只切回旧镜像后宣称撤销了 schema。

需要实际恢复演练时，使用带镜像与摘要清单的检查点：

```sh
rtk proxy python3 scripts/directory/recovery.py backup
rtk proxy python3 scripts/directory/recovery.py verify <检查点ID>
rtk proxy python3 scripts/directory/recovery.py restore <检查点ID>
```

检查点保存在私有目录 `checkpoints/`，包含数据库、站点配置、公私有文件及各文件摘要。恢复要求当前后端镜像 ID 和只读快照摘要与检查点一致，并且本项目的 worker、scheduler 未运行。脚本先备份当前状态，再停止入口、恢复本项目站点、迁移并启动入口；失败时入口保持关闭，保留恢复前检查点。恢复成功后仍须重新执行真实客户目录、独立客户端与权限验收，登录页恢复不代表业务恢复通过。

## 原型与真实页面

可点击原型单独放在 `prototypes/directory/`，使用显式合成场景；原型的数据和控件不进入本验收镜像。实际目录页面只使用获准的历史数据、明确的数据日期及必要操作。
