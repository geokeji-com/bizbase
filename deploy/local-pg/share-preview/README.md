# 员工文件分享预览

启动或迁移本项目的专属回环预览站：

```sh
rtk proxy bash deploy/local-pg/share-preview/start.sh
```

打开 [安装页](http://127.0.0.1:18081/file-share-setup) 复制提示词，可在本机体验下载、安装、登录及终端管理。预览员工账号为 `share-preview@example.test`，密码在当前系统用户的 `~/.local/share/bizbase-share-preview/employee_password` 中。管理员账号为 `Administrator`，密码在同目录 `admin_password` 中。只将密码填入浏览器。此预览使用合成员工和站点密码，移山 ID 真实扫码需要已在身份平台登记的站点。

Compose 项目名为 `bizbase-share-preview`，监听 `127.0.0.1:18081`，将数据保留在独立卷。若需暂停，运行 `rtk proxy docker compose -p bizbase-share-preview -f deploy/local-pg/compose.yaml stop`。再次运行启动脚本可继续体验。
