# 通过 CLI 和 Agent 管理文件分享

适用于已安装本版 `file_share` 并完成迁移的站点。从文件分享列表的菜单选择「安装文件分享助手」，或打开本站 `/file-share-setup`。点击「复制安装提示词」发给同事，同事再交给自己电脑上的 Agent。安装页面提供同站下载、校验、更新和登录指引。当前用户安装需要 Python 3.9 或以上版本。

## 员工首次授权

CLI 打开浏览器后，员工选择「通过移山 ID 登录」。首次登录会登记待绑定的移山 UID。管理员在「移山 ID 绑定」核对 UID、选择员工的 BizBase 系统账号并启用。员工重新运行登录，核对八位确认码和终端名称后授权。CLI 通过 `whoami` 输出本人账号。员工可用 `logout` 撤销当前终端授权。授权最多 8 小时，浏览器原会话失效时同时终止。

## 管理员下发与禁用

- **下发工具**　在文件分享菜单复制安装提示词即可分发。员工凭证由本站在员工确认终端后签发。
- **单台终端**　在文件分享侧栏「终端授权」（`/desk/file-share-grant`）打开对应员工与终端的记录，点击「禁用此终端」。员工可查看及禁用自己的授权，系统管理员可管理全部授权。
- **员工账号**　在「移山 ID 绑定」（`/yishan-id`）停用对应绑定，移山 ID 登录和相应会话随之停用。要停用该用户的所有登录方式，在「用户」中停用 BizBase 账号。

安装后的命令为 `bizbase`，安装器还会提供可直接运行的绝对路径命令。源码开发使用 `./tools/bizbase --site 站点地址`，或设置 `BIZBASE_SITE` 后运行以下示例。

## 从草稿发布到一个域名

```sh
./tools/bizbase --json share upload report.html --title '季度报告'
./tools/bizbase --json share publish REPORT_ID --version 1 --domain DOMAIN --access internal
./tools/bizbase --json share upload report-v2.zip --report REPORT_ID
./tools/bizbase --json share publish REPORT_ID --version 2 --domain DOMAIN --keep-access
./tools/bizbase --json share show REPORT_ID
./tools/bizbase --json share close REPORT_ID --domain DOMAIN
```

将 `REPORT_ID` 换成上传响应的 `data.share_id`，将 `DOMAIN` 换成已启用域名的 `name`。每次上传只增加草稿版本。发布固定指定域名的版本，返回客户链接。用历史版本号调用同一命令即可回退。另一个域名可以独立发布该报告的不同版本。`current_version` 是 Desk 的全报告默认版本，按域名核对实际交付版本请看 `entries`。

首次发布必须显式选择 `--access`。更新或回退已开启的入口时，可用 `--keep-access` 保留原权限和密码。`internal` 只允许在职员工；`specified` 可重复使用 `--user` 和 `--role`；`password` 在终端提示输入口令，自动化可通过 `--password-stdin` 从受控输入读取；`public` 允许任何持链接者访问。关闭入口影响后续读取，收件人已保存的副本仍在其设备上。

对于可能重试的写入，调用前生成 UUID，在相同命令末尾加 `--request-id UUID`。同一员工用相同 UUID 重试相同请求会获得原结果。新版本或不同设置使用新的 UUID。CLI 输出 `success`、`data` 或 `error`，失败时返回非零退出码。

## HTTP 契约

员工授权后由 CLI 以 `POST /api/method/file_share.api.<方法>` 调用，凭证通过 `X-BizBase-Share-Token` 请求头发送；接口同时支持已登录的员工站点会话（遵循 Frappe 的 CSRF 规则）。成功结果在 Frappe 的 `message` 中。CLI 将其映射为 `data`。这些方法只处理调用员工自己的报告。

| 方法 | 请求参数 | 结果 |
| --- | --- | --- |
| `whoami` | 无 | `user` |
| `domains` | 无 | 已启用域名的 `name`、`display_name`、`origin` |
| `list_reports` | `start`、`limit` | 本人报告摘要 |
| `get_report` | `share_id` | 摘要、历史版本、各域名入口 |
| `upload` | Multipart：`request_id`、二进制 `file`、新报告 `title` 或已有报告 `share_id` | 报告 ID 和新增版本 |
| `publish` | JSON：`request_id`、`share_id`、`domain`、`version`、`access_mode`，按范围填写 `users` / `roles` 数组或 `password` | 该域名的版本、查看范围和链接 |
| `close` | JSON：`request_id`、`share_id`、`domain` | 关闭操作回执 |

HTTP `access_mode` 使用 `Internal`、`Specified`、`Password`、`Public`。对已经开启的入口，`Keep` 保留原授权，仅切换版本，对应 CLI 的 `--keep-access`。`File Share Operation` 记录 API 写操作，可凭请求 ID 核对员工和操作结果。收件人访问报告的记录继续保存在「访问记录」。
