# 任务执行

Server 工作区 `/desk/task-execution`。System Manager 配置能力、Worker、账号和出口；查看服务器写入的任务、执行尝试和原始结果。记录以站点时区的日期时间保存。此 App 不包含平台登录、外部浏览器自动化或真实设备采集程序。

## 配置与使用

1. 在「能力版本」登记操作（`prompt`、`link_check`）、平台、端、版本。键建议采用 `platform-channel-operation-v1`。参数定义是“字段名 → 支持的值数组”，例如 `{"online":[true,false],"thinking":["standard","deep"]}`。这是配置示例，不代表真实平台支持这些选项。每个字段都需传值。不需参数的操作填 `{}`。改变定义需另建版本，旧版本可停用。
2. 为每个 Worker 建立无管理角色、无客户数据权限的 Frappe 用户，使用该用户的应用凭证。管理员在「Worker 管理」关联用户与实际支持的能力版本；一台设备同时持有一个租约。可选绑定账号和网络出口。账号处于 `Needs Verification` 时由授权持有人通过官方流程人工处理，不派发新任务。管理表只存凭据引用，不存密码、验证码或代理密钥。
3. 服务计划通过内部 `task_execution.api.ensure_task(prompt_text, capability, parameters, window_start, window_end, sample_index=0)` 提交。管理员也可调用 POST `task_execution.api.submit(input_text, capability, parameters, window_start, window_end, sample_index=0)` 创建单条测试任务。链接观测的输入是目标 URL。共享按输入、能力版本、参数、完全相同的起止时刻、独立样本序号精确匹配；不会跨不同窗口强行合并。
4. Worker 调用下表中的 POST 接口，地址前缀为 `/api/method/task_execution.api.`，使用 Frappe 认证。账户被移除/停用、租约失效或跨 Worker 的请求均不能提交结果。

| 方法 | 输入 | 结果 |
| --- | --- | --- |
| `claim` | 无 | 返回一条匹配任务（`task`、`attempt`、租约、时窗、输入、平台及参数）；无任务时为空。重复领取自己正在执行的任务会得到同一租约。 |
| `renew` | `task, attempt` | 续租至最多五分钟后，不跨任务时窗。 |
| `complete` | `task, attempt, observed_at, payload` | 返回结果 ID。同一尝试、相同时间、相同结果可重复回传；冲突的回传拒绝。 |
| `fail` | `task, attempt, reason` | 记录失败；时窗内可重领，第三次失败终止。原因不应包含凭据。 |

问句结果例：`{"answer":"原始回答","response_kind":"answer","actual_parameters":{"online":true,"thinking":"deep"},"sources":[{"title":"资料","url":"https://example.test/source"}]}`。拒答用 `refusal`。`sources` 为 `[]` 表示已检查且无信源，未提供时记为 `null`；支持可选的 `share_url`。参数不能核实时不要冒充匹配样本。链接观测例：`{"http_status":404,"final_url":"https://example.test/missing"}`；这也是成功观测。

Server 串行裁定一次领取和一次有效结果。首次领取时间只写一次，重试逐条留痕；完成时间仅在成功、终止失败或过窗时写入。实际观测时间需在本次尝试和采样时窗内。后台每五分钟清理过期任务，Worker 拉取时也会执行有界清理。运行时资源绑定、能力参数矩阵及任务统计均为管理员可见，Worker 只接收执行所需字段。首版不派发发布任务，不计算客户指标，不存截图附件。

纯校验测试：`rtk proxy env PYTHONPATH=apps/task_execution python3 -m unittest discover -s apps/task_execution/tests`。业务归属见 [GEO 应用设计](../../docs/business/geo-apps.md)。
