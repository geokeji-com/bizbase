---
name: bizbase-share
description: 在 BizBase 以员工本人身份查询文件分享、上传 HTML/ZIP 草稿、发布或回退指定域名的报告版本、关闭分享入口时使用。
---

# BizBase 文件分享

<!-- bizbase-command -->
使用 `bizbase --json …`。从源码运行时将 `bizbase` 换成 `./tools/bizbase`。通过 `BIZBASE_SITE` 或全局参数 `--site` 选择员工指定的站点。
<!-- /bizbase-command -->

1. 运行 `bizbase --json whoami`，核对 `data.user`。需要授权时让员工运行 `bizbase login`，在浏览器核对账号和授权信息。凭证由 CLI 保存。
2. 查报告用 `share list`、`share show ID`。用 `share domains` 取得可发布的域名标识。版本号只在该报告内有效。
3. 根据员工的请求执行下表中的动作。为每个写动作生成一个 UUID 并传 `--request-id UUID`。网络超时后用原 UUID 和完全相同的参数重试。每个新动作使用新的 UUID。

| 意图 | `bizbase --json` 后接的命令 | 完成条件 |
| --- | --- | --- |
| 上传草稿 | `share upload FILE --title TITLE`，续传用 `share upload FILE --report ID` | 得到 `data.share_id` 和 `data.version`。只要求上传时，到此结束。 |
| 发布或回退 | `share publish ID --domain HOST --version N --access MODE` | 核对返回的域名、版本、范围和链接。已开启入口更新或回退时，用 `--keep-access` 替代 `--access MODE` 以保留原授权和密码。 |
| 关闭入口 | `share close ID --domain HOST` | 用 `share show ID` 核对该域名的 `enabled`。 |

发布前取得员工指定的域名与查看范围。`internal` 供在职员工查看，`specified` 用重复的 `--user` 或 `--role` 指定对象，`password` 由员工在终端交互输入或用 `--password-stdin` 从受控来源提供，`public` 允许任何持链接者读取。未指定范围时可先存草稿。入口密码始终由员工或受控输入源直接交给 CLI。

以退出码和 JSON 中的 `success` 判断结果。发布成功时向员工返回报告 ID、域名、版本、查看范围和 `data.url`。若查询被拒绝，说明当前账号及被拒绝的动作。
