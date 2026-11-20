# 中企动力：在原报告站增加 BizBase 分享入口

适用场景：两台都是自有服务器。公网域名 `proposal.cebest.com` 继续由原报告服务器 `172.28.237.156` 终止 HTTPS；只有 `/file-share/s/` 转发到 BizBase 服务器 `172.28.237.157`。原站 `/r/`、`/client-report/`、首页和 PHP 等规则不改。此配置用于公开和密码分享，不提供员工登录。以下是待部署示例，不是现网端口或证书盘点结果。

## 准备（先做 .157，再做 .156）

- BizBase 多域名版须已部署并完成迁移；在两个槽位的 frontend 内层允许名单中加入 `server_name proposal.cebest.com;`，方式见[运维说明](OPERATIONS.md#逐个接入文件分享域名多域名版发布后)。配置中的 `bizbase_slot` 使用宿主机现有的活动槽位 upstream，不重定义、不跨机连接 318x。
- 以下建议在 .157 专用内网端口 **18443** 提供 HTTPS，先确认端口空闲；若改端口，两端一致。安全组/防火墙只允许 .156 访问 .157 的这个端口，其他内网主机和公网都不开放。确认无 SNAT，或按实际核实的源地址收窄名单。
- 下文用 `bizbase.geokeji.com` 作为**内网 TLS 证书名**，前提是 .157 有对应有效证书和完整链；否则换成已有受信任的回源证书名。它不决定报告权限。HTTP `Host` 始终固定为 **`proposal.cebest.com`**。私钥留在各自机器。

## 1. BizBase 服务器 .157：宿主机 Nginx 新增独立内网 server

放在已有 `bizbase_slot` upstream 的同一个 `http` 配置上下文中。替换证书占位路径，使用与内网监听相匹配的证书。不要改公网主站 vhost。

```nginx
server {
    listen 172.28.237.157:18443 ssl;
    server_name proposal.cebest.com;
    ssl_certificate     /REPLACE/bizbase.geokeji.com/fullchain.pem;
    ssl_certificate_key /REPLACE/bizbase.geokeji.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    allow 172.28.237.156;
    deny all;
    # 此监听的来源 ACL 针对实际 TCP 对端，不要继承会把对端改成访客 IP 的 real_ip 信任规则。
    if ($host != proposal.cebest.com) { return 404; }
    access_log off;

    location ~ "^/file-share/s/[A-Za-z0-9]{10}(?:/|$)" {
        limit_except GET POST { deny all; }  # GET 包含 HEAD；POST 用于提交口令
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host proposal.cebest.com;
        proxy_set_header X-Forwarded-Proto https;
        # .156 覆盖该头；不要追加客户端自报的转发链。
        proxy_set_header X-Forwarded-For $http_x_real_ip;
        proxy_set_header X-Real-IP $http_x_real_ip;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-Host "";
        proxy_set_header X-Frappe-Site-Name "";
        proxy_set_header Authorization "";
        proxy_cache off;
        proxy_redirect off;
        proxy_pass http://bizbase_slot;
    }
    location / { return 404; }
}
```

## 2. 原报告服务器 .156：只增加一个 location

以下片段加入现有 `proposal.cebest.com` 的 **443 HTTPS `server` 块内部**。不要替换整份文件。`^~` 让报告 JS/CSS/图片不落入原站的静态文件缓存；不要沿用 `/r/` 的仅 GET 或清空所有 Cookie 的设置。下面 CA 文件为常见 Debian 路径，部署前核实本机实际 CA 包，不能关闭证书验证代替。

```nginx
location ^~ /file-share/s/ {
    if ($host != proposal.cebest.com) { return 404; }
    limit_except GET POST { deny all; }
    access_log off;
    proxy_cache off;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host proposal.cebest.com;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host "";
    proxy_set_header Forwarded "";
    proxy_set_header X-Frappe-Site-Name "";
    proxy_set_header Authorization "";

    # 仅转发本应用的口令票据与资产 Cookie，不传递 PHP/Desk 的登录会话。
    # 报告口令 Cookie 由应用按报告路径设置，资产 Cookie 按本次内容目录设置。
    set $bb_pwd_cookie "";
    if ($http_cookie ~ "(?:^|; *)(ss_[A-Za-z0-9]{10}=[a-z0-9]+[.][A-Za-z0-9_-]{32})(?:;|$)") {
        set $bb_pwd_cookie "$1; ";
    }
    proxy_set_header Cookie "${bb_pwd_cookie}ss_asset=$cookie_ss_asset";
    # 外壳/口令响应需能设置 Cookie；若上游另发根路径 Guest Cookie，不覆盖原站根会话。
    proxy_cookie_path ~^/$ /file-share/s/;

    proxy_ssl_server_name on;
    proxy_ssl_name bizbase.geokeji.com;
    proxy_ssl_verify on;
    proxy_ssl_verify_depth 4;
    proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;
    proxy_connect_timeout 5s;
    proxy_read_timeout 60s;
    proxy_redirect off;
    proxy_pass https://172.28.237.157:18443;  # 无尾斜杠，保留完整 URI
}
```

## 验收与回退

两端用各自实际运行的 Nginx 二进制检查 `nginx -t`。先验证 .156 到 .157 的内网 TLS 证书链及主机名，再在发布窗口加载配置。用一份合成口令报告验收：错误口令不可看、正确口令加载 HTML/JS/图片；同域名未开放的报告返回 404；关闭入口后原资源 URL 失效；访问记录显示 `proposal.cebest.com` 和交付版本。回归原 `/r/`、`/client-report/`、首页仍正常。未完成测试不要用于客户报告，不要用真实口令或签名资源地址作日志样例。

回退只需先停用报告的中企动力入口，再撤下本次添加的 .156 location 和 .157 私网监听、收回端口准入；不改 DNS、不动旧报告规则。
