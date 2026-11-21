"""Calendar logic. Task timestamps are site-local, as required by Frappe Datetime."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def clock(value):
    if isinstance(value, timedelta):
        seconds = int(value.total_seconds())
        return time(seconds // 3600, seconds // 60 % 60, seconds % 60)
    return value if isinstance(value, time) else time.fromisoformat(str(value))


def parse_weekdays(value):
    days = {int(x.strip()) for x in value.split(',')}
    if not days or not days <= set(range(1, 8)):
        raise ValueError('星期必须是 1 至 7。')
    return days


def local_wall(day, value, zone):
    moment = datetime.combine(day, clock(value)).replace(tzinfo=zone)
    if moment.astimezone(timezone.utc).astimezone(zone) != moment or moment.utcoffset() != moment.replace(fold=1).utcoffset():
        raise ValueError('采样时窗包含不存在或有歧义的夏令时时间。')
    return moment.astimezone(timezone.utc)


def subdivide(day, start, end, samples, plan_zone, site_zone):
    """Each sample gets its own disjoint eligibility interval; do not count retries."""
    zone = ZoneInfo(plan_zone)
    start, end = local_wall(day, start, zone), local_wall(day, end, zone)
    length = int((end - start).total_seconds())
    if not 1 <= samples <= min(48, length):
        raise ValueError('采样次数须在 1 至 48 之间，且每个独立时窗至少一秒。')
    boundaries = [start + timedelta(seconds=length * i // samples) for i in range(samples + 1)]
    local = [item.astimezone(ZoneInfo(site_zone)).replace(tzinfo=None) for item in boundaries]
    if any(b <= a for a, b in zip(local, local[1:])):
        raise ValueError('无法用站点时间无歧义地表达采样时窗。')
    return list(zip(local, local[1:]))
