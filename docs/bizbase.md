# BizBase · 业务基础平台

BizBase 是公司的业务基础平台，提供共享数据、通用能力和基础业务应用，支持在平台内开发应用，也支持独立系统通过 API 接入。

## 项目来源

- 仓库：https://github.com/geokeji-com/bizbase
- 上游：https://github.com/frappe/frappe_docker
- 保留 GitHub fork 关系，后续基于上游部署方案定制。

## 版本决策（2026-11-16）

第一版采用 **Frappe 16**。框架使用 `version-16` 稳定系列，不采用 Frappe 17 开发版本。

各 App 按其对 Frappe 16 的兼容性选取版本；App 自身版本号不要求与框架相同。后续部署应记录具体版本、提交和镜像摘要，并验证完整应用组合。

当前继承的 `example.env` 默认 ERPNext 镜像版本为 `v16.55.0`，属于 16 系列。这是上游示例配置，不代表所有 Apps 已选定或安装完成。

## 当前状态

已完成官方部署仓库 fork、项目重命名及框架大版本决策。此前本地试验环境已清理；本仓库尚未完成 BizBase 专属业务开发或实际部署。
