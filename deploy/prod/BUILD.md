# 生产镜像

仓库根目录构建固定摘要的官方 linux/amd64 发行包，保留 Frappe 16.56.0、ERPNext 16.55.0 和原版静态资源，加入 GEO 运营、移山 ID 登录和分享。镜像内置已在预览验收的分享路径 Nginx 模板。Dockerfile 专用忽略文件限制构建上下文。

```sh
rtk proxy docker buildx build --platform linux/amd64 --load -t bizbase/prod:erpnext-share-candidate -f deploy/prod/Containerfile .
rtk proxy docker image inspect bizbase/prod:erpnext-share-candidate --format '{{.Os}}/{{.Architecture}} {{.Id}}'
rtk proxy docker run --platform linux/amd64 --rm --network none --entrypoint sh bizbase/prod:erpnext-share-candidate -ec 'env/bin/pip check && env/bin/python -m unittest static_share.tests.test_core static_share.tests.test_policy yishan_id_login.tests.test_oidc yishan_id_login.tests.test_session'
```

发布时记录确切镜像 ID 和 Git 提交，生产五个进程使用同一镜像。可以用 `docker save` 和 `docker load` 转移镜像并核对两端 ID。持久站点的应用安装顺序见[生产运维](OPERATIONS.md)。
