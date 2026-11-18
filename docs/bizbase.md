<!-- ratchet: kind=brief status=review -->
# BizBase · 业务基础平台

循环接入说明（2026-11-18）：[整体自然式规划](planning/natural-plan.md)及两项取舍已经用户确认，见 D-003、D-004 和[已应用清单 2](cycle/sheets/decision-sheet-02.md)；按 D-005，该规划作为当前 brief。以下保留前期定位及建议，未逐项接受的模型和数据归属仍是候选。历史实现、调研和口述均为可修正证据。

BizBase 是公司的业务基础平台，提供共享数据、通用能力和基础业务应用，支持在平台内开发应用，也支持独立系统通过 API 接入。

## 已明确的建设目标（2026-11-17）

公司当前开展 GEO 业务，后续可能扩展其他产品或业务线。开发、销售和运营等岗位均可能借助 AI 构建业务系统；BizBase 优先解决这些系统之间的数据隔离问题。

- 允许不同系统提供重复功能、采用不同业务视角，不以统一所有界面或消除重复功能为目标。
- 对共享业务数据统一含义与权威来源，避免各系统独立维护互不关联的数据。
- 向业务应用提供一致的数据访问、权限和基本业务能力。
- ERPNext 和独立 CRM 是平台中的业务应用；安装应用本身不等于完成统一数据与权限底座。

术语见 [项目词汇表](../GLOSSARY.md)。[早期整体方案](business/2026-11-17-bizbase-overall-plan.md)形成于组织仓库盘点前，保留当时的数据归属和分期建议，不作为已确认裁决。当前推进入口见[首轮整体规划](planning/natural-plan.md)及[证据清单](cycle/evidence.md)。[业务梳理与候选模型](business/2026-11-17-geo-service-model.md)仍需以真实样例收敛；尚未实施。

[受控目录最小模型](business/directory-model.md)、[模型图](business/directory-model-views.md)和[清单 3](cycle/sheets/decision-sheet-03.md)曾按 D-007—D-009 获确认，相关目录实现已由 D-012 撤回。D-014 仅授权在原站点创建空 BizBase App，供后续 Build 配置使用，不恢复旧目录实现。

[项目定位与官方应用选择](business/2026-11-17-bizbase-positioning-and-app-selection.md)根据完整业务与 SOP 重新评估原 13 项候选：保留 Frappe、ERPNext、CRM，其中自研 BizBase App 的具体范围现以 D-014 的空壳为准；Insights 后续优先试评，其余按真实需求引入。原生 ERP/CRM API 继续复用，BizBase 补充共同业务规则和 GEO 能力。

## 项目来源

- 仓库：https://github.com/geokeji-com/bizbase
- 上游：https://github.com/frappe/frappe_docker
- 保留 GitHub fork 关系，后续基于上游部署方案定制。

## 版本决策（2026-11-16）

第一版采用 **Frappe 16**。框架使用 `version-16` 稳定系列，不采用 Frappe 17 开发版本。

各 App 按其对 Frappe 16 的兼容性选取版本；App 自身版本号不要求与框架相同。后续部署应记录具体版本、提交和镜像摘要，并验证完整应用组合。

当前继承的 `example.env` 默认 ERPNext 镜像版本为 `v16.55.0`，属于 16 系列。这是上游示例配置，不代表所有 Apps 已选定或安装完成。

## 当前状态

已完成官方部署仓库 fork、项目重命名及框架大版本决策。本地预览使用 Frappe 16.56.0、ERPNext 16.55.0，并通过自定义镜像增加独立 Frappe CRM 16.0.4、Frappe HR 16.54.1；启动方式与维护说明见 [本地 CRM 部署文档](../deploy/local-crm/README.md)。

本地预览不代表生产部署。BizBase 专属业务开发、GEO 业务流程及跨应用数据同步尚未完成。

## 相关调研

[官方应用与 GEO 业务调研（2026-11-17）](research/README.md)记录应用候选、厂商流程及数据模型建议。模型尚待结合公司实际业务确认，未据此安装新增应用或创建生产业务表。
