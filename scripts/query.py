#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在库里检索，并且一定带定位符回来。

用法：
    python scripts/query.py 痛苦 死亡          # 同时含这些词（AND）
    python scripts/query.py --trace 我思故我在   # 这个知识点最早到底出自哪
    python scripts/query.py 痛苦 --limit 5 --json

纪律：本脚本只报告库里有什么。找不到就明说找不到，绝不凭模型记忆补。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import cite, iter_items, out  # noqa: E402

SKIP = re.compile(r"<!--\s*p\.\d+\s*-->|^#{1,6}\s.*$", re.M)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", SKIP.sub(" ", text)).strip()


def snippet(body: str, pos: int, width=70) -> str:
    a = max(0, pos - width)
    b = min(len(body), pos + width)
    s = clean(body[a:b])
    return ("…" if a > 0 else "") + s + ("…" if b < len(body) else "")


def search(terms, limit):
    """检索范围含标题、标签、知识点出处，不只是正文。

    标题里写着「论实体的摘录」，正文却不出现「实体」二字——只搜正文会让这种条目
    永远搜不到。命中的若是元信息而非正文，摘要从正文开头取，不假装找到了。
    """
    hits = []
    for path, meta, body in iter_items():
        low_body = body.lower()
        title = str(meta.get("title") or "")
        extra = " ".join(str(meta.get(k) or "") for k in ("tags", "origin_of", "work", "author"))
        haystack = f"{title}\n{extra}\n{body}".lower()
        positions = []
        for t in terms:
            idx = haystack.find(t.lower())
            if idx < 0:
                break
            positions.append(idx)
        else:
            first_body = low_body.find(terms[0].lower())
            hits.append((path, meta, body, first_body if first_body >= 0 else 0, min(positions)))
    hits.sort(key=lambda h: h[4])
    return [h[:4] for h in hits[:limit]]


def trace(term):
    rows = []
    for path, meta, body in iter_items():
        terms = meta.get("origin_of") or []
        if isinstance(terms, str):
            terms = [terms]
        if any(term in str(t) for t in terms):
            idx = body.lower().find(term.lower())
            rows.append((path, meta, body, idx if idx >= 0 else 0))
    return rows


def emit(rows, header):
    out(header)
    if not rows:
        out("\n  库里没有。这不是「不存在」，是「这个库还没收」。")
        out("  要么补书，要么把这条记进缺口：python scripts/wanted.py")
        return
    for i, (path, meta, body, pos) in enumerate(rows, 1):
        out(f"\n{i}. {cite(meta, body, pos)}")
        out(f"   {meta.get('title','')}  ·  {path.name}")
        out(f"   {snippet(body, pos)}")
        if meta.get("edition") not in (None, "", "TODO"):
            out(f"   版次：{meta.get('edition')}   定位：{meta.get('locator')}")


def main():
    args = [a for a in sys.argv[1:]]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]

    limit = 10
    if "--limit" in args:
        i = args.index("--limit")
        limit = int(args[i + 1])
        del args[i:i + 2]

    if not args:
        out(__doc__)
        return

    if args[0] == "--trace":
        term = " ".join(args[1:]).strip()
        if not term:
            out("× --trace 后面要跟一个知识点")
            return
        rows = trace(term)
        if as_json:
            out(json.dumps([{"cite": cite(m, b, p), "path": str(pa), "meta": m} for pa, m, b, p in rows],
                           ensure_ascii=False, indent=1))
            return
        emit(rows, f"【出处追溯】{term}")
        if rows:
            seen = {(m.get("author"), m.get("work")) for _p, m, _b, _x in rows}
            if len(seen) > 1:
                out(f"\n⚠ 这个知识点在库里有 {len(seen)} 个不同出处记录，必须裁定哪个才是最早的。")
        return

    terms = [t for t in args if not t.startswith("--")]
    if not terms:
        out("× 没有给关键词")
        return
    rows = search(terms, limit)
    if as_json:
        out(json.dumps([{"cite": cite(m, b, p), "path": str(pa), "meta": m, "snippet": snippet(b, p)}
                        for pa, m, b, p in rows], ensure_ascii=False, indent=1))
        return
    emit(rows, f"【检索】{' + '.join(terms)}   命中 {len(rows)} 条")


if __name__ == "__main__":
    main()
