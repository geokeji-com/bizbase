"""Command line for employee-delegated file sharing."""

import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import uuid


class InputError(ValueError):
    pass


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("版本号和条数必须大于零")
    return number


def parser():
    root = argparse.ArgumentParser(prog="bizbase", description="以员工身份管理 BizBase 文件分享")
    root.add_argument("--site", default=os.environ.get("BIZBASE_SITE"), help="BizBase 站点源地址，或设置 BIZBASE_SITE")
    root.add_argument("--json", action="store_true", help="输出单行 JSON")
    actions = root.add_subparsers(dest="command", required=True)
    for cmd, help_text in [("login", "在浏览器授权"), ("logout", "撤销本机授权"), ("whoami", "核对已授权员工身份")]:
        actions.add_parser(cmd, help=help_text)
    share = actions.add_parser("share", help="查询、上传、发布或关闭文件分享")
    actions = share.add_subparsers(dest="action", required=True)
    actions.add_parser("domains", help="列出已启用的域名")
    listing = actions.add_parser("list", help="列出本人报告")
    listing.add_argument("--limit", type=positive, default=20)
    listing.add_argument("--offset", type=int, default=0)
    show = actions.add_parser("show", help="查询历史版本和各域名入口")
    show.add_argument("report")
    upload = actions.add_parser("upload", help="上传 HTML 或 ZIP 为草稿")
    upload.add_argument("file", type=Path)
    target = upload.add_mutually_exclusive_group(required=True)
    target.add_argument("--title", help="创建报告时设置标题")
    target.add_argument("--report", help="为已有报告上传新版本")
    publish = actions.add_parser("publish", help="在指定域名发布或切回某一版")
    publish.add_argument("report")
    publish.add_argument("--version", type=positive, required=True)
    publish.add_argument("--domain", required=True, help="使用 share domains 返回的域名标识")
    policy = publish.add_mutually_exclusive_group(required=True)
    policy.add_argument("--access", choices=("internal", "specified", "password", "public"))
    policy.add_argument("--keep-access", dest="access", action="store_const", const="keep", help="切换已开启入口的版本并保留现有权限")
    publish.add_argument("--user", action="append", default=[], help="指定用户，可重复")
    publish.add_argument("--role", action="append", default=[], help="指定角色，可重复")
    publish.add_argument("--password-stdin", action="store_true", help="从标准输入读取一行入口密码")
    close = actions.add_parser("close", help="关闭指定域名的入口")
    close.add_argument("report")
    close.add_argument("--domain", required=True)
    for write in (upload, publish, close):
        write.add_argument("--request-id", type=uuid.UUID, help="请求的 UUID，重试同一操作时复用")
    return root


def audience(args):
    if args.access != "specified" and (args.user or args.role):
        raise InputError("--user 和 --role 仅用于 specified")
    if args.access == "specified" and not (args.user or args.role):
        raise InputError("specified 需要至少一个 --user 或 --role")
    if args.password_stdin and args.access != "password":
        raise InputError("--password-stdin 仅用于 password")
    if args.access == "password":
        if args.password_stdin:
            secret = sys.stdin.readline().rstrip("\r\n")
        elif sys.stdin.isatty():
            secret = getpass.getpass("入口密码：")
        else:
            raise InputError("请在终端输入入口密码或通过 --password-stdin 从受控输入读取")
        if len(secret) < 6:
            raise InputError("入口密码至少 6 位")
        return secret
    return None


def dispatch(args, client):
    if args.command == "login":
        return client.login()
    if args.command == "logout":
        return client.logout()
    if args.command == "whoami":
        return client.call("whoami")
    if args.action == "domains":
        return client.call("domains")
    if args.action == "list":
        if args.offset < 0:
            raise InputError("--offset 必须大于或等于零")
        return client.call("list_reports", {"start": args.offset, "limit": args.limit})
    if args.action == "show":
        return client.call("get_report", {"share_id": args.report})
    payload = {"request_id": args.request_id}
    if args.report:
        payload["share_id"] = args.report
    if args.action == "upload":
        if args.file.suffix.lower() not in {".htm", ".html", ".zip"} or not args.file.is_file():
            raise InputError("请选择可读的 HTML 或 ZIP 文件")
        if args.title:
            payload["title"] = args.title
        return client.call("upload", payload, file=args.file)
    payload["domain"] = args.domain
    if args.action == "publish":
        password = audience(args)
        payload.update(version=args.version, access_mode=args.access.capitalize())
        if args.access == "specified":
            payload.update(users=args.user, roles=args.role)
        if password is not None:
            payload["password"] = password
    return client.call(args.action, payload)


def main(argv=None, client_factory=None):
    from .auth import Client, ClientError

    args = parser().parse_args(argv)
    request_id = None
    if hasattr(args, "request_id"):
        request_id = args.request_id = str(args.request_id or uuid.uuid4())
    try:
        if not args.site:
            raise InputError("请用 --site 或 BIZBASE_SITE 指定要访问的 BizBase 站点")
        result = dispatch(args, (client_factory or Client)(args.site))
        reply = {"success": True, "data": result}
    except (ClientError, OSError, ValueError, EOFError) as error:
        reply = {"success": False, "error": {"code": getattr(error, "code", "input_error"), "message": str(error)}}
        if request_id:
            reply["request_id"] = request_id
    print(json.dumps(reply, ensure_ascii=False, indent=None if args.json else 2))
    return 0 if reply["success"] else 1
