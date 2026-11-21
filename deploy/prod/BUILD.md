# 生产候选镜像

从仓库根目录构建 `linux/amd64`。本地 PG 和生产共用应用安装层与兼容补丁，生产最后一层加入邮件本地化。CRM 浏览器资源取自本机已验收的 `bizbase/erpnext-crm:16.55.0-16.0.4`，构建时核对源码提交 `9ace234fceb3c5e7bd630b74f44ba1779e831abe`。Python 依赖在固定的 amd64 ERPNext 镜像里安装。`INSIGHTS_SOURCE` 指向 Insights 3.50.1（`4cdc09e0ec15edfaefb2a9d180efd1b6b552394e`）的应用目录，包含与该提交匹配的前端产物。静态资源的构建步骤见[本地 PG 构建脚本](../local-pg/build.sh)。也可从已验证的本地最终镜像提取同一份应用作为 `INSIGHTS_SOURCE`。

```sh
# 下面的临时目录只提取应用文件。镜像内的站点配置和数据卷不进入构建上下文。
rtk proxy bash -ec 'd=$(mktemp -d); docker run --rm --pull=never --network none --entrypoint tar bizbase/local:postgres-16 -C apps/insights --exclude=__pycache__ -cf - insights pyproject.toml README.md | tar -xf - -C "$d"; test -s "$d/insights/www/_insights.html"; echo "$d"'
# 将上一条输出的目录设为 INSIGHTS_SOURCE。
rtk proxy docker buildx build --platform linux/amd64 --load \
  --target crm -f deploy/prod/Containerfile -t bizbase/erpnext-crm:16.55.0-16.0.4-amd64 .
rtk proxy docker buildx build --platform linux/amd64 --load \
  --build-arg CRM_IMAGE=bizbase/erpnext-crm:16.55.0-16.0.4-amd64 \
  --build-context insights="$INSIGHTS_SOURCE" -f deploy/local-pg/Containerfile \
  -t bizbase/platform:pg-amd64 .
rtk proxy docker buildx build --platform linux/amd64 --load \
  -t bizbase/prod:pg-candidate -f deploy/prod/Containerfile .
rtk proxy docker image inspect bizbase/prod:pg-candidate --format '{{.Os}}/{{.Architecture}} {{.Id}}'
rtk proxy docker run --platform linux/amd64 --rm --network none --entrypoint sh bizbase/prod:pg-candidate -ec 'test ! -d apps/crm && ! grep -Fxq crm sites/apps.txt && env/bin/python -m unittest file_share.tests.test_core file_share.tests.test_policy yishan_id.tests.test_oidc yishan_id.tests.test_session'
```

发布记录应包含实际通过验收的镜像 ID、Git 提交及 PG 演练结果。现有生产站点更改安装清单需要维护窗口，步骤见[生产运维](OPERATIONS.md)。
