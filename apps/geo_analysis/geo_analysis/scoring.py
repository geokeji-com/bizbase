"""Immutable v1 scoring semantics. Ranking is supplied by an evidence reviewer."""

import hashlib


def answer_hash(answer):
    return hashlib.sha256(answer.encode('utf-8')).hexdigest()


def evaluate(answer, names, outcome, position, quote, refusal_policy):
    if not quote or not quote.strip() or quote not in answer:
        raise ValueError('复核依据必须是本条回答的原文片段。')
    if refusal_policy not in ('Exclude', 'Include as miss'):
        raise ValueError('请选择有效的拒答处理口径。')
    if outcome not in ('Ranked', 'Unranked', 'Refusal'):
        raise ValueError('请选择复核结论。')
    if outcome == 'Ranked':
        if not isinstance(position, int) or position < 1:
            raise ValueError('有明确推荐顺序时，请填写正整数名次。')
    elif position not in (None, 0):
        raise ValueError('未排名或拒答的样本请留空名次。')
    matches = [name for name in dict.fromkeys(names) if name and name in answer]
    return dict(mentioned_as='\n'.join(matches), included=int(outcome != 'Refusal' or refusal_policy == 'Include as miss'),
                hit=int(outcome == 'Ranked' and position <= 3), source_hash=answer_hash(answer))


def format_rate(hit, included):
    return f'{100 * hit / included:.2f}%' if included else '无有效样本'
