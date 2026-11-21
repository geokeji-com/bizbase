"""Pure validation used by both the versioned capability and the execution server."""
import hashlib
import json
from datetime import datetime
from urllib.parse import urlsplit


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def as_object(value):
    obj = json.loads(value) if isinstance(value, str) else value
    if not isinstance(obj, dict):
        raise ValueError('需要 JSON 对象')
    return obj


def schema(value):
    obj = as_object(value)
    for name, choices in obj.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(choices, list) or not choices:
            raise ValueError('每个参数都需要名称和可选值数组')
        if any(type(choice) not in (str, int, bool) for choice in choices):
            raise ValueError('参数选项只能是布尔值、整数或文本')
    return obj


def parameters(value, definitions):
    obj = as_object(value)
    if obj.keys() != definitions.keys():
        raise ValueError('请求参数与能力版本声明的字段不一致')
    for name, choices in definitions.items():
        if canonical(obj[name]) not in [canonical(choice) for choice in choices]:
            raise ValueError(f'不支持的参数值：{name}')
    return obj


def site_time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.tzinfo is not None:
        raise ValueError('请提供站点本地日期时间，不带时区偏移')
    return value


def url(value):
    if not isinstance(value, str) or len(value) > 8192 or any(c.isspace() for c in value):
        raise ValueError('URL 格式错误')
    parsed = urlsplit(value)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('仅接受不含认证信息的 HTTP(S) 地址')
    return value


def result_fields(operation, payload, requested):
    data = as_object(payload)
    if len(canonical(data).encode()) > 2_000_000:
        raise ValueError('回传正文超过大小限制')
    if operation == 'link_check':
        if set(data) != {'http_status', 'final_url'} or type(data['http_status']) is not int or not 100 <= data['http_status'] <= 599:
            raise ValueError('链接观测需提供 HTTP 状态码和最终 URL')
        return {'response_kind': 'link_check', 'http_status': data['http_status'], 'final_url': url(data['final_url'])}
    if operation != 'prompt' or set(data) - {'answer', 'response_kind', 'actual_parameters', 'sources', 'share_url'}:
        raise ValueError('不支持的采集回传字段')
    if not isinstance(data.get('answer'), str) or not data['answer'].strip():
        raise ValueError('缺少原始回答')
    kind = data.get('response_kind', 'answer')
    if kind not in ('answer', 'refusal'):
        raise ValueError('无效的回答种类')
    if canonical(data.get('actual_parameters')) != canonical(requested):
        raise ValueError('实际采集条件未确认或与请求不符，请回报执行失败')
    sources = data.get('sources')
    if sources is not None:
        if not isinstance(sources, list) or len(sources) > 500:
            raise ValueError('信源需按原顺序回传')
        for source in sources:
            if not isinstance(source, dict) or set(source) - {'title', 'url'} or not isinstance(source.get('title', ''), str):
                raise ValueError('信源须包含链接，可附标题')
            url(source.get('url'))
    return {'answer': data['answer'], 'response_kind': kind, 'actual_parameters': canonical(requested),
            'sources': canonical(sources), 'share_url': url(data['share_url']) if data.get('share_url') else None}
