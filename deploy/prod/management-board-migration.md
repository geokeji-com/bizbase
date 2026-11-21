# 已有 PostgreSQL 站点：管理看板原地更名

仅用于 Frappe 16.56.0 / PG 16 上已经安装 `bizbase_mgmt` 的站。中文仍为「管理看板」；安装 ID、Module Def、Workspace 统一变为 `management_board`，公开 URL 为 `/desk/management-board`。**这是 D 类停写迁移，不是普通镜像切换。不要 uninstall/install 或先用新代码运行 `bench migrate`。** 新建站直接走正常初始化。

## 窗口前

- 保留旧镜像的不可变 ID、旧版部署配置和旧应用源码（本地 bind mount 也要保留），另打新镜像、用不同 tag。核对新旧镜像 `sites/apps.txt` 的集合差异**只有**此次更名，候选镜像能导入新包且含新图标；单纯更名不要顺带卸载其他应用。若发布范围明确包括独立 CRM 退役，则候选清单差异还应有 `-crm`：仅在关联业务、同步和自定义项重新盘点为空、隔离副本已验证完整流程、冻结备份可恢复后，用旧镜像执行 `maintenance old env/bin/python - --site "$SITE" < crm_uninstall_compat.py`，再原地更名、切换新清单并迁移。不要在已经移除 CRM 包的新镜像里运行卸载逻辑。
- 先在**隔离还原副本**完整走一遍本流程。记录迁移前的应用列表/版本、`Block Module.module` 行及所属用户/配置、Workspace.roles、Custom Workspace 的可见性与角色增减、用户默认页和桌面入口。备份和包含授权的基线都按敏感资料保护。
- 确认兼容性：自定义脚本/报表、第三方 hooks、反向代理及集成中的旧路径单独审查。脚本会拒绝部分无法安全解释的工作区 JSON / 站点代码，不会尝试改写任意代码或历史日志。基本工作区必须是旧版标准工作区且限 System Manager；不要靠删除授权行来通过检查。若存在独立站点 `apps.txt` 或站点自维护且包含旧名的 bench `apps.json`，先编制其精确映射及回退，不要用新模板覆盖这些清单。
- 以下示例针对**单站 bench**。共享 `sites/apps.txt` 影响 bench 上所有站点；多站须全部核对、停写并迁移每一个有旧安装身份的站，全部成功后才能切清单。

## 生产

取得维护窗口授权。先确认旧/候选镜像 ID，停身份同步 timer 及外部写入，排空队列。使用该站的 `deploy.sh maintenance begin IMAGE`、`freeze` 停前后端、websocket、调度与 worker。冻结后做一致性检查点（数据库、站点全目录含密钥/附件/清单、主机发布状态），验证可独立恢复后才登记 `checkpoint`。不要把检查点命令当作实际备份。

在发布工具目录运行（下例 `SITE` 和 `TOOLS` 分别为目标站点名和已核验脚本目录）：

```bash
rtk proxy ./deploy.sh maintenance old env/bin/python - --site "$SITE" < "$TOOLS/rename_management_board.py"
rtk proxy ./deploy.sh maintenance manifest
rtk proxy ./deploy.sh maintenance migrate
rtk proxy ./deploy.sh maintenance preview
```

第一步在**旧镜像、旧清单**下执行，不加载新包；单笔数据库事务更改 `installed_apps`（保留顺序）、Installed Application、Module Def、标准及定制工作区和相应引用。权限行、角色增减、子表行沿用原 ID；目标身份或悬空授权冲突即回滚。提交后定向清本站安装缓存；缓存异常保持停写，在相同阶段重跑第一步。已完成状态会核对新身份且不会再次换名。`manifest` 从候选镜像原子切换已有共享 `sites/apps.txt`；`migrate` 由新镜像执行全站迁移与清缓存。

## 本地已有站

先关闭写入口、维护模式置 1、停止 backend/frontend/websocket/worker/scheduler，保留 PG 与 Redis；做同样的可恢复检查点。使用原 Compose 项目名和原数据卷，不要 `down -v`。以下在仓库根目录，`OLD_COMPOSE` 指含**完整旧源码挂载**的原 Compose 配置，`OLD_IMAGE`、`NEW_IMAGE` 是预先核验的不同镜像标记。不要对另一个站点或默认项目名盲跑。

```bash
rtk proxy env BIZBASE_DEV_IMAGE="$OLD_IMAGE" docker compose -f "$OLD_COMPOSE" run --rm --no-deps -T backend env/bin/python - --site frontend < deploy/prod/rename_management_board.py
rtk proxy env BIZBASE_DEV_IMAGE="$NEW_IMAGE" docker compose -f deploy/local-pg/compose.yaml run --rm --no-deps -T backend bash -eu -c 'p=sites/apps.txt; test "$(grep -Fxc bizbase_mgmt "$p")" = 1; ! grep -Fxq management_board "$p" || exit 1; t=$(mktemp sites/.apps.XXXXXX); trap '\''rm -f "$t"'\'' EXIT; cp -p "$p" "$t"; sed "s/^bizbase_mgmt$/management_board/" "$p" > "$t"; mv "$t" "$p"'
rtk proxy env BIZBASE_DEV_IMAGE="$NEW_IMAGE" docker compose -f deploy/local-pg/compose.yaml run --rm --no-deps -T backend bench --site frontend migrate
rtk proxy env BIZBASE_DEV_IMAGE="$NEW_IMAGE" docker compose -f deploy/local-pg/compose.yaml run --rm --no-deps -T backend bench --site frontend clear-cache
```

若清单已切换，不要重复执行替换命令；检查其内容，仅在 DB 与候选一致时继续。验收环境用新镜像与新代码重新创建服务，不要复用旧容器；确认环境隔离后关闭维护模式预览。

## 验收与失败处理

1. `bench --site SITE list-apps` 只出现新身份，其他应用和版本不变；Module Def、Workspace 的 `name/module` 及标准角色一致。将冻结前的禁用模块、用户权限/分享、定制工作区和增减角色按 `旧 → 新` 归一化逐行对照，而非仅比较总数。
2. 管理员检查卡片、默认工作区和保存的桌面入口；直接打开及刷新 `/desk/management-board`。用无权用户及有模块禁用的用户确认看不到看板且不能通过直接地址获得内容。检查其他看板、登录、静态资源。生产在候选端验收通过且获准后再 `maintenance publish`，恢复后台任务/同步并按窗口流程 `accept`。
3. 脚本报错时不切流、不继续初始化；查明冲突后在副本重新演练。数据库已提交或候选 `migrate` 之后，不允许仅切回旧镜像、手改 `installed_apps` 或只还原 `apps.txt`。恢复必须停写，按同一冻结点恢复数据库、站点文件及清单、配置和旧镜像/挂载，再验权和恢复服务；发布后有新写入时另行决策。

**本次可行性验证：** 用独立内部 Docker 网络、临时 PostgreSQL 16、Redis 和 `bizbase/local:pg-routes` 新建 `qa.local`，只安装 Frappe 与旧看板。添加禁用模块、Hidden 定制工作区、removed_roles、侧栏工作区引用、User Permission 与桌面布局；目标名悬空 DocShare 被拒、回滚后旧数据仍在。移除**人为植入的测试冲突**后迁移成功，保持维护状态重跑无变更；切入新包及清单后 `bench migrate`、`clear-cache` 和上述行级检查通过。此验证不是目标站还原演练，也不代表已上线。
