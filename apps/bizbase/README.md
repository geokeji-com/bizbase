# BizBase App

Frappe 16 的自研业务 App。第一个版本提供本地历史快照目录、显式客户读取权限和审计。

使用仓库 `deploy/local-directory/` 的隔离验收环境。真实快照和凭据保存在仓库外；普通目录用户不能直接读取客户引用或源文件。
