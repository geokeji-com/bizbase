# 第 01 轮本地使用与运维

入口：<http://127.0.0.1:8081/desk/bb-directory>。用本机私有 `~/.codex/private/bizbase-round01/login.txt` 中的人员账号登录，点击客户查看优化对象；“刷新”会重新检查授权。原 `localhost:8080` 保留。

页面只有已获准的真实历史样本，日期为 2026-11-02。它不是实时目录或当前在服清单。内部框架沿用 ERPNext/CRM，但本轮未配置 ERP 财务公司；隔离站点已跳过初次设置向导，以便普通目录账号使用自研页面。

## 独立客户端

在仓库根目录执行，结果为当前机器账号获准的数据，含真实客户信息，请勿直接贴入公开 issue：

```sh
rtk proxy python3 scripts/directory/consumer.py --credentials ~/.codex/private/bizbase-round01/client.json
```

客户端只调用 API；自身不读取快照。业务读取接口为 `bizbase.api.directory.list_customers` 和 `list_subjects`。RPC 参数和响应字段见代码；不支持把 actor/user 参数当作代理人员授权。

## 检查、关闭和恢复

```sh
rtk proxy python3 scripts/directory/bootstrap.py status
rtk proxy python3 scripts/directory/state.py directory off
rtk proxy python3 scripts/directory/state.py directory on
rtk proxy python3 scripts/directory/verify_round01.py
```

完整验收会复原本轮测试账号及授权并执行故障测试；不要与人工配置或其他测试并行。它仅适用于固定隔离项目。恢复后的首轮验收会先比对检查点摘要、使用原凭据读取，并跳过 seed。

备份恢复使用 [部署说明](../../../../deploy/local-directory/README.md) 中的 recovery.py。检查点包含数据库、站点配置、公私有文件、来源摘要、目录状态摘要和配套本机凭据。停止保留卷，禁止用 `down -v` 代替停止。

故障定位：页面“请求编号”对应 Integration Request.request_id；管理身份可在原生日志中检索。认证前失败看新 frontend 的访问日志；审计写入失败看 backend 的 `directory_audit_unavailable request_id=...`。只读查看 `bizbase-r01` 的日志，别操作旧 `bizbase` 项目。

已知限制：[安全记录](security.md) 中的基础镜像漏洞尚未处理；只监听本机，不能作为公网生产版本使用。重建依赖本机已存在的固定基础镜像；跨机器重新制作基础镜像不在本轮交付范围。恢复演练的实际结果见发布记录。
