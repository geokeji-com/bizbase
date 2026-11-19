# 移山 ID

站点级登录集成：BizBase 所有入口（`/login`、Desk、ERPNext、CRM、HR 移动端、GEO 运营、Build）都可以用移山 ID 登录。员工在移山 ID 用飞书扫码，在职校验和离职撤销由移山 ID 负责。账号密码登录保留，用于应急。

版本 `0.1.0`，Frappe 安装名为 `yishan_id_login`。站点配置有效时，登录页和 HR 移动端才会显示移山 ID 登录按钮。

## 工作方式

1. 登录页的「通过移山 ID 登录」打开 `/yishan-id/login`，由 Frappe 转到 `/api/method/yishan_id_login.auth.start`，并传递登录后的站内返回地址。服务端生成 state、nonce 和 PKCE S256，把它们和一个浏览器绑定 cookie 一起暂存 10 分钟，然后跳转到移山 ID，并默认直接进入飞书员工连接器。
2. 移山 ID 回调 `/api/method/yishan_id_login.auth.callback`。服务端核对 state 和浏览器 cookie，用授权码换取令牌，再校验签名（JWKS）、issuer、audience、有效期、nonce、认证时间（默认 2 小时内），以及 access token 的 `client_id`、`yishan.uid`、`yishan.identity_version` 和员工身份。
3. 每次新建会话前，先向移山 ID 确认在职状态，再按 `yishan.uid` 查找「移山 ID 绑定」。只有已启用、并指向已启用用户的绑定才会登录，不按 email 或手机号匹配。Administrator 和 Guest 不能绑定。第一次登录但没有绑定时，系统会登记一条未启用的绑定，等管理员选择用户后启用。
4. 登录后，请求优先使用最近一次在职确认，确认结果最多缓存 60 秒。移山 ID 明确拒绝核验、答复离职或身份版本变化时，结束会话。控制面暂时不可用时，从最后一次成功确认起最多沿用 5 分钟，到期后拒绝请求。access token 到期时，会话同时结束。
5. 移山 ID 的后端通知退出发到 `/api/method/yishan_id_login.auth.backchannel_logout`。服务端校验 logout token 后，删除对应的会话。停用、换绑或删除绑定时，也会立即撤销该移山 ID 的会话。

服务端会话保存 `(iss, sub)`、`yishan.uid`、`yishan.identity_version` 和加密的 access token。浏览器使用 Frappe 原有的 `sid` cookie 维持业务会话。

## 站点配置

在 `sites/frontend/site_config.json` 中设置（不进入 Git）：

| 键 | 必填 | 说明 |
| --- | --- | --- |
| `yishan_id_issuer` | 是 | `https://id.geokeji.com/oidc` |
| `yishan_id_client_id` | 是 | 移山 ID 为 BizBase 登记的 client ID |
| `yishan_id_client_secret` | 机密客户端必填 | 只放站点配置，不写进仓库或日志 |
| `yishan_id_redirect_uri` | 是 | 与移山 ID 登记值完全一致，例如 `https://<域名>/api/method/yishan_id_login.auth.callback` |
| `yishan_id_audience` | 否 | 默认 `<issuer 域名>/yid/v1` |
| `yishan_id_direct_sign_in` | 否 | 默认 `social:yishan-feishu`；设为空字符串时显示移山 ID 的通用登录页 |
| `yishan_id_max_auth_age_seconds` | 否 | 默认 7200 |

本机 DEV 预览使用 `http://127.0.0.1:8080`。DEV 用专用 MCP 密钥调用 `register_dev_service`，以 `get_service_status` 返回的公开 `oidc_client_id` 配置登录。本机 HTTP 回调必须与登记值完全一致，公开客户端省略 `yishan_id_client_secret`。平台无法向开发者机器的回环地址投递后端退出通知，真实投递联调需要从平台可达的 DEV 回调地址。TEST 和 PRODUCTION 由管理员在 Admin「服务」中开启，并使用 HTTPS 回调。

```bash
bench --site frontend set-config yishan_id_issuer https://id.geokeji.com/oidc
bench --site frontend set-config yishan_id_client_id <client_id>
bench --site frontend set-config yishan_id_client_secret <client_secret>
bench --site frontend set-config yishan_id_redirect_uri https://<域名>/api/method/yishan_id_login.auth.callback
```

## 绑定员工

系统管理员可点击 Desk 应用卡片「移山 ID」，也可复制站内入口 `/yishan-id`。Frappe 将入口重定向到 `/desk/yishan-id-binding`，Desk 打开「移山 ID 绑定」列表后，地址栏会显示带模块名的 `/desk/yishan_id_login/yishan-id-binding`。可以预先新建：填写移山 UID、选择用户并勾选启用。也可以让员工先登录一次，再在自动登记的未启用记录上选择用户并启用。

## 测试

协议层测试使用本地 ES384 签名的模拟移山 ID。会话测试在已安装 Frappe 的开发容器内运行，模拟身份核验和时钟。两组测试均不请求真实移山 ID：

```bash
rtk proxy docker exec bizbase-backend-1 env/bin/python -m unittest yishan_id_login.tests.test_oidc yishan_id_login.tests.test_session
```
