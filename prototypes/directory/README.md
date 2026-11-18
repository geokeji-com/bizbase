# 客户目录交互原型

本目录仅用于第 01 轮 V 阶段的交互验证，不能部署到正式页面。所有夹具均为合成数据；不读取私有快照，不请求接口，不使用账号、凭据或浏览器持久化存储。

`index.html`、`styles.css`、`app.js` 为原生静态文件。由本轮主 Agent 在 `127.0.0.1:8082` 启动静态服务并实际试用，原型作者不另启服务。

## 场景与操作

- 正常：选择“合成客户 A”，查看两个合成对象、历史快照、数据日期、来源及版本；缺失分类显示“未知”。
- 无结果：场景切换器设置“查询无结果”，或自行搜索不存在的客户/对象；“清除查询”恢复。
- 零对象：选择“合成客户 B”，显示“无匹配对象”及当前快照没有对象的说明。
- 加载：选择“延迟加载（2 秒）”；可在等待中选择其他客户，旧请求不会覆盖新选择。加载会自动结束。
- 来源失败：目录内容及元数据隐藏；点击“重试”后经过加载恢复，不把故障解释为空结果。
- 无权限：不展示客户与对象；“重新检查”仍保持拒绝，只有显式切换原型场景才恢复。
- 关闭/启用：仅原型工具栏提供“模拟停用目录”与“模拟启用目录”，显示操作结果；停用时不展示客户与对象。

## 稳定测试标识

使用 `[data-testid="…"]` 选择器。

| 标识 | 用途 |
| --- | --- |
| `prototype-toolbar` / `scenario-select` | 合成范围与原型场景工具栏 |
| `reset-prototype` / `directory-toggle` | 重置、模拟启停 |
| `action-notice` | 模拟启停、重试成功反馈 |
| `refresh-directory` | 刷新 |
| `snapshot-meta` / `snapshot-mode` | 快照元数据及历史模式 |
| `data-as-of` / `directory-version` / `source-system` | 日期、版本、来源 |
| `customer-search` / `customer-list` | 客户搜索、列表 |
| `customer-a` / `customer-b` | 两个合成客户选择 |
| `selected-customer-name` / `selected-customer-id` | 当前客户 |
| `back-to-customers` | 清除客户选择并回到选择状态 |
| `subject-search` / `subjects-table` / `subject-row` | 对象搜索及表格 |
| `unknown-type` | 缺失分类的“未知”值 |
| `no-matching-subjects` / `zero-subjects` | 对象查询无结果、客户零对象 |
| `clear-customer-search` / `clear-subject-search` | 清除查询 |
| `loading-state` / `loading-directory` | 加载状态 |
| `source-error` / `retry-source` | 来源故障、重试 |
| `forbidden` / `check-permission` | 无权限、重新检查 |
| `disabled` | 功能关闭 |

场景选项值：`normal`、`no-results`、`zero-subjects`、`loading`、`source-error`、`forbidden`、`disabled`。

验证边界：原型只能验证交互与视觉，不证明真实来源已接入、权限已执行或审计已持久化。
