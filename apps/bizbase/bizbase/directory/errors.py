"""对外错误只使用固定消息，绝不拼接来源内容或异常文本。"""

ERRORS = {
    "INVALID_ARGUMENT": (400, "请求参数不正确"),
    "FORBIDDEN": (403, "没有客户目录读取权限"),
    "NOT_FOUND": (404, "客户不存在或未获授权"),
    "DIRECTORY_DISABLED": (503, "客户目录尚未启用"),
    "SOURCE_UNAVAILABLE": (503, "客户目录来源暂时不可用，请稍后重试"),
    "AUDIT_UNAVAILABLE": (503, "客户目录暂时不可用，请稍后重试"),
}


class DirectoryError(Exception):
    def __init__(self, code):
        self.code = code
        self.status, self.message = ERRORS[code]
        super().__init__(self.message)

    def response(self, request_id):
        return {"error": {"code": self.code, "message": self.message, "request_id": request_id}}
