# 发布文件分享助手

本地验收候选使用已安装 `file_share` 的销售镜像作为基础，只复制 `apps/file_share`，保留生产应用清单。执行正式发布前，通过生产工具核实实际活动镜像的不可变 ID，并以该镜像构建增量候选。本机标签与实际生产镜像不同，不能仅凭标签推断一致。

```sh
rtk proxy python3 scripts/build_share_agent.py --check
rtk proxy docker build --platform linux/amd64 --network none -f deploy/prod/Containerfile.share-agent --build-arg ACTIVE_BASE="$VERIFIED_ACTIVE_BASE" -t "$CANDIDATE" .
```

`File Share Grant` 和 `File Share Operation` 是新增单据，原有 Redis-only 试验终端需要重新授权。按[生产发布流程](OPERATIONS.md)核对分级、备份和隔离恢复，执行迁移。候选应用清单和共享资源检查通过后再切流。

公网验收从主站 `/file-share-setup` 下载清单和安装包，在新用户目录核对 SHA-256 并安装。员工自己完成移山 ID 扫码，在浏览器核对终端及确认码。核对 `whoami` 与绑定账号。管理员在文件分享侧栏「终端授权」禁用一个测试授权，确认该客户端失效、另一已授权客户端仍可用。沿用文件分享生产基线检查现有报告和客户入口。完成后从正式站安装页复制提示词下发。
