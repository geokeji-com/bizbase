# 生产镜像

从仓库根目录运行。Dockerfile 专用忽略文件限制构建上下文；生产站点、数据库配置和管理员密码均不作为输入。

```sh
rtk proxy docker buildx build --platform linux/amd64 --load -t bizbase/prod:16.56.0-release -f deploy/prod/Containerfile .
rtk proxy docker image inspect bizbase/prod:16.56.0-release --format '{{.Os}}/{{.Architecture}} {{.Id}}'
rtk proxy docker run --platform linux/amd64 --rm --network none --entrypoint sh bizbase/prod:16.56.0-release -ec 'ls -1 apps; env/bin/python -c "import frappe, geo_operations, yishan_id_login; print(frappe.__version__, geo_operations.__version__, yishan_id_login.__version__)"'
```

2026-11-18 发布镜像在目标 ECS 原生构建，镜像 ID `sha256:847058ffb8c010b2e787ce6f7877c88d40609dc32008cdf67adba6a7cc537d27`，已在无网络、无生产卷的临时容器中核对三个 App 的版本与静态资源。本次构建使用 `--build-arg REG=docker.m.daocloud.io`，仍使用官方 amd64 摘要。第一阶段从官方预编译发行包取出 Frappe、运行依赖和专属静态资源；最终镜像的基底为独立的 `frappe/base`，不继承 ERPNext 发行包的应用层。框架源码标签对应 `49789a1711d4dde2be9c6888efe35651465f4b64`。镜像中不携带站点的运行凭据。两个自研 App 的版本来自构建时的工作树；发布部署须记录最终镜像 ID，而不只记录可变标签。

不使用外部仓库时，可用 `docker save` 通过 SSH 将镜像传给目标机的 `docker load`，核对两端的 `.Id`、`.Architecture` 和 `.Os`。首次创建站点和后续升级另行处理。
