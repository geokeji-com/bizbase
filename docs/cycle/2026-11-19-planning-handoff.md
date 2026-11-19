# BizBase 交接 · 第四步交付地图评审

2026-11-19。新窗口从**第四步评审**接手。交付地图已经写好，用户最近一次推进指令是“那就进入第四步吧”，随后要求交接。第五步的首个行动已列出，实施尚未开始。

## 先看哪份材料

| 已走到哪里 | 接手入口 |
|---|---|
| 第一步已定稿。采用官方 ERPNext 独立 App，复用 Customer 和 Contract；共享客户资料授权归 BizBase，GEO 运营负责服务、监测、分析和交付，PG 兼容修复归所属上游组件。 | [D-033](decisions.md#d-033) |
| 第二步成果画面已完成。G1–G14 和横向验收条件给出业务完成标准。第三步已做六轮问答，保留备选方案、反例和待验证事实。 | [成果与验收](../planning/natural-plan.md#第二步完成后是什么样) · [六轮问答](../planning/opportunities.md#六轮自问自答) |
| 第四步已形成八项队列，列出前置条件、可并行项和每项验收证据。当前需要评审这一顺序；前四步确认后，日常循环第五步。 | [第四步交付地图](../planning/delivery-map.md) |

## 新窗口从哪里继续

先读交付地图，重点看“签约交接”是否足够小、销售和运营能否分别验证它。若用户确认进入第五步，首个行动是**用 C1 的一份已签合同，在原 8080 预览完成一次销售到运营的服务交接**。实际步骤和缩小首版范围的备选见[第五步的首个行动](../planning/delivery-map.md#第五步的首个行动)。

- 先核对当前工作树、`frontend` 实装 App、原生客户与合同、普通账号权限。再补本项关系图、交接时序、权限及验收样例。使用原预览的 Desk / Build，D-012 撤回的客户目录实验保持历史留档。
- 成功场景是销售从合同找回服务，运营从负责的服务找到同一合同、被服务组织和标的。后台、API、CLI 和员工 Agent 读到同一服务标识。用另一服务的普通成员和撤权后的旧入口核对拒绝结果，检查联系人、地址和私有附件。
- C1 两份材料的采样频次有差异，当前执行依据与最终考核、结算依据分别记录。C2 是公司自身，仍走普通客户、合同和考核流程。真实问句、合同和凭据只放获准的本地预览或私有目录；两案例材料位于 `~/.codex/private/bizbase-service-v1-20261118/`。

## 环境与未验证事项

- **本地预览**：历史记录为 Compose 项目 `bizbase`、站点 `frontend`、`http://127.0.0.1:8080`，已安装 ERPNext 16.55.0。本次交接时自动审批服务不可用，未取得实时 Git 状态；前一轮也未能运行 `git diff --check` 或复查容器实况。接手先执行 `rtk git status --short --branch`，保留工作树已有改动；准备操作站点时再查 `rtk proxy docker ps --filter label=com.docker.compose.project=bizbase` 和 `rtk proxy docker compose -p bizbase -f pwd.yml -f deploy/local-crm/compose.override.yaml exec -T backend bench --site frontend list-apps`。所有 shell 命令以 `rtk` 开头。
- **PG 隔离实验**：Frappe 16.56.0、ERPNext 16.55.0、PostgreSQL 16.15 已验证建档、合同、迁移及恢复。联系人下拉仅验证了主联系人的绕过方式；服务端归属、实际 GEO 角色下关联资料的授权与撤权仍需验证。阿里云 RDS 尚待获准的空白测试库。[实测范围](../research/2026-11-18-erpnext-on-postgres.md)
- **已上线站点**：据用户反馈，框架、移山 ID 登录 App 与 GEO 运营基础版已上线，真实登录验收等待提供方的 Client ID 和 Secret。本会话没有核实线上 ERPNext 安装状态。生产发布、生产数据迁移、权限扩大、付费投放及写入他人系统沿用 D-004 的授权边界。

新窗口可直接发送：“请读 `docs/cycle/HANDOFF.md`，从 11 月 19 日交接里的第四步交付地图评审继续。”
