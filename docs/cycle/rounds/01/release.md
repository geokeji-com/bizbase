<!-- ratchet: kind=release status=done by=delegated-agent done_at=2026-11-18T11:41 -->
# 第 1 轮发布记录

> 已撤回（D-012，2026-11-18）：本轮实例和实现已删除，8081 不再提供服务。以下保留发布当时的历史证据；当前状态以[撤回记录](withdrawal.md)为准，命令不可直接用于当前工作树。

发布范围依 D-004、D-011：本地隔离验收版。Agent 自主执行并留证，未宣称生产上线或用户亲自验收。

## 构建产物
<!-- section: build -->

- App 构建提交 `8e5afa86bf23e868056f1f5ff4b6a2d75d6d7e92`；本地运行标签 `bizbase/directory:r01-e7dfd26c5f38-8e5afa86`。
- 镜像 ID `sha256:060cda0ec3ebcfa3072a3126be137b29dc5758e350cc25a5fde10b49137446f4`。该产物完成 3 次完整验收，没有在最终验收后重建。

## 备份
<!-- section: backup -->

- 检查点 `20261118T033558592989Z`：数据库、站点配置、公私有文件、源文件摘要、目录/授权摘要及配套本机凭据；文件位于私有 `bizbase-round01/checkpoints/`、权限 600。
- 恢复前自动另存检查点 `20261118T033738688427Z`。旧 8080 的固定镜像、原容器、原卷保留，未作为本轮恢复目标。

## 迁移
<!-- section: migrate -->

1. 在新站点安装 App，新增 BB Customer Reference、复合唯一索引、角色和关闭状态；空库模型测试通过后才进入 V/C。
2. 固定产物安装标准 Desk Page；migrate 后激活快照、配置独立普通人员与机器身份、显式客户授权。
3. 两次完整迁移、清缓存及幂等 seed 后验收；恢复后第三次先校验原始状态及凭据，跳过 seed 再复验。没有来源库或旧站点迁移。

## 自动检查
<!-- section: tests -->

由 `cycle.py add release` 自动写入，不要手改。

- 命令：`rtk proxy python3 scripts/directory/verify_round01.py`
- 退出码：0
- 提交：fde4384
- 持续集成配置：.github/workflows/core-publish-images.yml, .github/workflows/app-build-image.yml, .github/workflows/docs-publish-site.yml, .github/workflows/core-build-stable.yml, .github/workflows/lint.yml, .github/workflows/build_develop.yml, .github/workflows/core-build-bench.yml, .github/workflows/stale.yml, .github/workflows/core-build-develop.yml, .github/workflows/directory.yml, .github/workflows/core-build-test-images.yml, .github/workflows/build_stable.yml
- 检查时间：2026-11-18T11:39
- 强制跳过的原因：-

```

OK
Restored directory state and credentials verified before mutation
Isolated migrations applied
Frappe integration suite passed
HTTP: 13 check groups passed
Browser: 7 check groups passed
Round 01 full local acceptance passed; private evidence saved
```

## 部署
<!-- section: deploy -->

- `scripts/directory/bootstrap.py` build/up/data；Compose 固定项目 `bizbase-r01`，只开放 127.0.0.1:8081。真实数据只读挂在 backend 的独立卷，未进入镜像。
- 发布时入口 <http://127.0.0.1:8081/desk/bb-directory>，现已撤回；当时登录凭据位于本机私有 login.txt。[当前使用状态](runbook.md)。生产部署不适用：本轮明确为本地验收。

## 安全
<!-- section: security -->

- 新增构建/浏览器依赖审计 0 项；继承运行时 8 条告警、去重 7 项，未声称整体安全通过。限制与未覆盖源码 fork 见[安全记录](security.md)。
- 实际客户名称/ID及现场生成凭据扫描：公开源码和镜像内 App 均无命中。普通人员/机器用户没有 System Manager；原生资源、分享、日志及配置旁路均拒绝。

## 观测
<!-- section: observe -->

- 每次业务读取有请求编号及原生 Integration Request；审计故障日志保留安全请求编号。认证前拒绝由 frontend 访问日志定位。权限变更有 Permission Log。
- 外部告警平台/值班看板不适用：单机内部验收版；手工健康检查、关闭和故障定位见[运维手册](runbook.md)。日志实际保留配置见[验收对应表](verification.md)。

## 上线后核对
<!-- section: verify -->

- 3 次完整本地验收通过：每次 11 项公开快照测试、19 项数据库测试、13 组 HTTP、7 组真实浏览器；原型另有 8 组试用。22 行验收均有[脚本证据映射](verification.md)。
- 恢复后 `business_reverification_required=false`，验证完成于 `2026-11-18T03:39:56Z`；恢复态摘要、原凭据、客户/对象 ID 与版本一致。没有用 seed 修复恢复态后再算通过。
- backend/frontend/websocket 运行，MariaDB/两 Redis healthy，初始化容器退出码 0；私有配置可读；worker/scheduler 未启动。发信及队列消费不适用：本轮同步只读路径，无邮件或后台任务交付。
- 旧 8080 三个核心容器 ID、镜像、挂载及登录入口保持；实际查看桌面与窄屏截图。临时原型 8082 服务已停止。
- [GitHub Actions](https://github.com/geokeji-com/bizbase/actions/runs/44231428088) 在 `1022d7c` 上通过公开合成检查及新增依赖审计；不代替本地私有样本验收。

## 回滚
<!-- section: rollback -->

- 目录关闭：`rtk proxy python3 scripts/directory/state.py directory off`；进程停止：`rtk proxy python3 scripts/directory/bootstrap.py stop`，保留卷。
- 已实际执行 `rtk proxy python3 scripts/directory/recovery.py restore 20261118T033558592989Z`，停止新站点业务进程、一次性容器恢复 DB/config/files、恢复配套凭据，随后第三次全套复验通过。
- 首版没有上一 BizBase 功能版；这里演练的是同一已验收产物的数据与配置恢复，不把它描述为软件降级演练。
