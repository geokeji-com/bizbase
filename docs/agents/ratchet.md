# BizBase 开发循环

```ratchet
root: docs/cycle
lang: zh-CN
brief: docs/planning/natural-plan.md
domain_model: docs/business/directory-model.md
decisions: docs/cycle/decisions.md
backlog: docs/cycle/backlog.md
decision_prefix: D
glossary: GLOSSARY.md
adr_dir: docs/adr
rounds_dir: docs/cycle/rounds
round_dir_format: {n:02d}
status_file: docs/cycle/STATUS.md
lessons: docs/cycle/lessons.md
stale_words: 待裁决,待确认,待定,TBD
test_cmd: rtk proxy python3 scripts/directory/verify_round01.py
ci_files: .github/workflows/*.yml,.github/workflows/*.yaml
```

按 D-005，已确认的整体规划作为 brief；按 D-006，当前领域模型入口是目录最小模型，并已由 D-007—D-009 获得确认。完整 GEO 候选保留原位置供后续扩展，不把历史建议自动视为用户裁决。
第 01 轮完整验收入口为 scripts/directory/verify_round01.py，包含实际站点迁移、身份准备、数据库、HTTP 与浏览器验证。公开 CI 使用同入口的 --public 合成检查模式；其通过不能替代本地真实样本验收。
仓库盘点的私有细节保留在本机私有目录；项目内仅记录抽象结论和证据编号。

用户在 D-002 明确采用自然式规划：首轮整体完成前四步，入口为 docs/planning/natural-plan.md；第五步的实施行动使用 ratchet。已确认的整体规划直接引用，只评审当轮新增变化，不每轮重做全局规划。
整体规划与实施轮次分别编号；阶段脚本仍按文件真实状态报告，不伪造门禁、发布或确认状态。

第 01 轮特例：用户 D-011 明确确认 readback，并要求中间无需用户介入；按最新用户指令自主完成原型试用、工程修订、验收和复盘，保留独立检查与真实证据。Agent 代为确认的记录标 delegated-agent，不冒充用户亲自试用；此授权不外推到后续轮次或生产范围。
