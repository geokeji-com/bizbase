# 移山 ID 登录

站点级登录集成：BizBase 所有入口（`/login`、Desk、ERPNext、CRM、HR 移动端、GEO 运营、Build）都可以用移山 ID 登录。员工在移山 ID 用飞书扫码，在职校验和离职撤销由移山 ID 负责。账号密码登录保留，用于应急。

版本 `0.1.0`。只有站点配置了下文的移山 ID 参数后，登录按钮才会显示；未配置时本 App 不改变任何行为。

## 工作方式

1. 登录页的「通过移山 ID 登录」进入 `/api/method/yishan_id_login.auth.start`。服务端生成 state、nonce 和 PKCE S256，把它们和一个浏览器绑定 cookie 一起暂存 10 分钟，然后跳转到移山 ID，并默认直接进入飞书员工连接器。
2. 移山 ID 回调 `/api/method/yishan_id_login.auth.callback`。服务端核对 state 和浏览器 cookie，用授权码换取令牌，再校验签名（JWKS）、issuer、audience、有效期、nonce、认证时间（默认 2 小时内），以及 access token 的 `client_id`、`yishan.uid`、`yishan.identity_version` 和员工身份。
3. 按 `yishan.uid` 查找「移山 ID 绑定」。只有已启用、并指向已启用用户的绑定才会登录，不按 email 或手机号匹配。Administrator 和 Guest 不能绑定。第一次登录但没有绑定时，系统会登记一条未启用的绑定，等管理员选择用户后启用。
4. 登录后，每个请求都会复查在职状态。确认在职的结果最多缓存 60 秒。移山 ID 明确答复离职或身份版本变化时，立即退出。移山 ID 不可用时，最近一次确认最多沿用 5 分钟，之后退出。access token 到期时，会话同时结束。
5. 移山 ID 的后端通知退出发到 `/api/method/yishan_id_login.auth.backchannel_logout`。服务端校验 logout token 后，删除对应的会话。停用、换绑或删除绑定时，也会立即撤销该移山 ID 的会话。

access token 加密保存在服务端会话中，浏览器只拿到 Frappe 原有的 `sid` cookie。

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

除本机模拟服务外，所有地址必须使用 HTTPS。

```bash
bench --site frontend set-config yishan_id_issuer https://id.geokeji.com/oidc
bench --site frontend set-config yishan_id_client_id <client_id>
bench --site frontend set-config yishan_id_client_secret <client_secret>
bench --site frontend set-config yishan_id_redirect_uri https://<域名>/api/method/yishan_id_login.auth.callback
```

## 绑定员工

在 Desk 打开「移山 ID 绑定」（仅 System Manager 可见）。可以预先新建：填写移山 UID、选择用户并勾选启用。也可以让员工先登录一次，再在自动登记的未启用记录上选择用户并启用。

## 测试

协议层测试不依赖 Frappe，使用本地 ES384 签名的模拟移山 ID，不发出网络请求：

```bash
cd apps/yishan_id_login && ../../env/bin/python -m unittest discover -s yishan_id_login/tests -p 'test_oidc.py' -t .
```

Frappe 集成测试（回调、绑定、会话复查、后端通知退出）：

```bash
bench --site frontend run-tests --app yishan_id_login
```
