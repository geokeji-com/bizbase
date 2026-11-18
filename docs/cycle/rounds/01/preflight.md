# 第 01 轮工程准备证据

日期：2026-11-18；准备结果，不代表软件已安装或发布。用户确认已记录为 D-007—D-009，G1 通过。

| 核验项 | 结果 | 边界 |
|---|---|---|
| 当前预览 | 现有 bizbase 项目、frontend 站点、8080；仅 sites/logs 挂载 | 本轮不写该站点和原卷 |
| 可用基础镜像 | 本机 ARM64 `bizbase/erpnext-crm@sha256:0ffc5fd8061155bbc89c74361ae65b00eea560c36a7828b4e2d5a9012464ffa2` | 派生 App 镜像尚未构建 |
| 框架组合 | Frappe 16.56.0、ERPNext 16.55.0、CRM 16.0.4 | 新站点仍须实际安装、迁移与回归 |
| 工具 | Bench 5.31.1；Python 3.14.10；Node 24.22.3；Yarn 1.22.22；new-app 支持 --no-git | 新 App 构建后端尚需按生成的 pyproject 锁定；当前无 flit_core/setuptools/build/pytest，不宣称离线可装 |
| 源码与端口 | apps/bizbase/ 不被忽略；8081、8082 当前无监听；未发现 bizbase-r01 容器/卷 | 启动前重新检查端口及资源归属 |
| 最小真实材料 | 从既有 S-01 原始记录提取 2 个客户身份、1 个对象；原始 ID 保留，分类缺失为 null | 仅准备文件，没有安装、导入、激活或授予测试账号权限 |
| 版本计时 | 一页纸单独提交 `c690478` | 这是轮次准备起点，不是发布提交；自然耗时包括审批与试用等待 |

真实材料位于 `~/.codex/private/bizbase-round01/`，目录权限 700，两个 JSON 文件权限 600；`snapshot-s01.json` 为最小目录载荷，`snapshot-s01.manifest.json` 保存原始材料摘要、提取时间和摘录摘要。摘录 SHA-256：`bf4aadc135bccab60529a68e99a0df451290fcf0c87effa311958d4530ea7124`，数据日期 2026-11-02，状态 `prepared_not_activated`。

登记客户仅用于身份及不继承权限的验证；选取的样本不包含它的全部业务对象，不能把摘录中的缺失解释为该客户实际没有对象。正式界面仅说明当前已接入快照范围，不宣称客户业务全量。

读取依据：当前容器安全字段与命令帮助、deploy/local-crm/Containerfile、既有 compose.yaml、.gitignore、私有原始对象映射文件；精确来源权限证据仍见 E-07—E-09。本轮未查询生产，不读取现有凭证，不更改旧账号。
