# 文件分享

员工在 Desk 发布 HTML 报告或 ZIP 静态站点，收件人用固定的 `/file-share/<10 位分享 ID>` 打开当前版本。应用依赖 Frappe v16 和 ERPNext 的 Employee。

## 发布与更新

1. 打开 Desk 应用「文件分享」或 `/file-share`，新建分享并填写标题。发布账号须为已启用的 `System User`。使用公司移山 ID 登录时，系统核对当前会话的在职核验有效期和启用的账号绑定。使用本站密码登录时，账号须关联状态为 `Active` 的 Employee。
2. 点击「选择报告文件」，选择自己的 `.html`、`.htm` 或 `.zip`。ZIP 推荐在根目录放 `index.html`，使用相对路径引用包内经典 JS、CSS 和图片。也支持唯一顶层目录内的 `index.html`，或根目录中唯一的 HTML。上传器使用私有 File，服务器同时检查文件所有者、私有标记和本地实际路径。
3. 选择查看范围并保存。点击「复制分享链接」，得到含当前域名和端口的完整地址。分享给收件人时使用这个地址。
4. 点击「上传新版本」替换内容。保存已有版本号可回退，也可由在职作者打开 `/file-share/<ID>?v=<版本号>` 预览历史。更新和回退保留同一分享链接，切换为 `Disabled` 后外壳与资产都停止服务。版本来源、入口、大小、上传人和时间由服务端生成。

| 查看范围 | 打开分享链接的条件 |
| --- | --- |
| Internal（默认） | 已登录且具备上述在职员工身份 |
| Specified | 在职作者，或在允许用户、允许角色中匹配的在职员工 |
| Password | 访客输入分享口令，或由已登录的在职作者打开 |
| Public | 持链接的任何人均可打开当前版本 |

员工可管理自己的分享、查看对应访问记录。System Manager 可管理分享与审计记录。在职绑定缺失的管理员在管理表单中可停用或删除已有分享。管理角色本身不授予指定人员入口、免密入口或历史预览权限。

`/file-share` 跳转到原生列表 `/desk/static-share`，原有列表书签和 `/desk/static-share/<ID>` 表单深链继续可用。已发送的 `/s/<ID>`、历史版本参数与旧资源地址沿用原来的授权与有效期。已通过旧链接输入的密码仍对该旧入口有效。站点迁移会更新已有记录的分享链接，复制按钮随即使用新地址。

## 浏览器与撤权

分享外壳使用 `sandbox="allow-scripts"`。每份内容响应也发送 CSP sandbox，按本次分享的版本目录限制脚本、样式、图片与媒体，并禁止表单、嵌套框架、Fetch 与 WebSocket。直接打开内容 URL 同样受限。包内使用经典 `<script src="…">`、相对 CSS、内联脚本和样式。需要外部 CDN、登录态、模块加载器或 API 请求的应用应先导出为自包含的静态包。

每个受限资产请求同时校验带有效期的路径与独立的 HttpOnly Cookie。Cookie 仅发往本次内容路径，使用 `Secure; SameSite=None`，以便沙箱中的相对 JS/CSS 也能通过校验。部署需使用 HTTPS，本地可用可信 loopback 地址。阻止这类 Cookie 的浏览器会拒绝受限资源。员工授权逐次检查原始登录会话、账号、在职身份与当前访问规则，退出登录、停用账号、离职或移除授权后，后续受限请求即被拒绝。页面授权有效期 30 分钟，过期后重新打开固定链接。

密码页使用 Frappe `Password` 字段。口令在 `__Auth` 表用站点密钥可逆加密，服务器解密后比较。请使用单独生成的分享口令。通过后记住该分享最多 7 天，同一分享及来源 IP 连错 10 次后限流 15 分钟。更换口令、查看范围、允许名单、状态或当前版本会使旧访问凭证失效。已下载、截图或另存的内容仍在收件人手中。

## 存储与接入

原始上传位于站点 `private/files`，发布副本位于 `private/files/.static_share/<ID>/<版本>`，由标准私有文件备份覆盖。备份恢复时同时保留数据库、私有文件和站点加密密钥。Desk 的文档变更记录和 `Static Share Access Log` 分别用于查看修改和外壳访问结果。日志保留分享 ID，删除分享后仍可追溯。

反向代理需保留原始 Host、端口、协议，把 `/file-share`、整个 `/file-share/` 与 `/s/`（含 `.html`、`.css`、`.js`）交给 Frappe，保留 CSP 与 `no-store`。仅在 `/file-share/<ID>/c/` 与 `/s/<ID>/c/` 子路径屏蔽上游 `Set-Cookie`，以免无登录 Cookie 的资源请求改变 Desk 会话。禁止直接提供 `/private/files/.static_share/`。本地配置见[部署说明](../../deploy/local-crm/README.md)。

## 无站点回归

在本 App 目录运行归档与签名测试。权限回归在安装了 Frappe 与本 App 的 bench Python 下运行，无需连接站点。

```sh
rtk proxy python3 -m unittest static_share.tests.test_core
rtk proxy docker exec bizbase-backend-1 env/bin/python -m unittest static_share.tests.test_policy
```
