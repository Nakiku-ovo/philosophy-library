# -*- coding: utf-8 -*-
"""排序体检：找出地图节点表里所有与「时间先后」冲突的位置。

用法：
    python scripts/order_check.py            # 只看问题
    python scripts/order_check.py --all      # 连解析出的年代一起列出

只做一件事：把每一行的年代解析成 (起, 止)，检查同一分区内是否单调不减。
不判断「应该怎么排」，只报告「现在这样排，时间上说不通」。
"""
from __future__ import annotations

import re
import sys

from _common import ROOT, out

MAP = ROOT / "地图.md"

# 中文数字，用于「前6世纪」这类
CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
      "九": 9, "十": 10, "十一": 11, "十二": 12}


def _num(s: str):
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s in CN:
        return CN[s]
    m = re.fullmatch(r"([一二三四五六七八九])?十([一二三四五六七八九])?", s)
    if m:
        tens = CN.get(m.group(1), 1) if m.group(1) else 1
        ones = CN.get(m.group(2), 0) if m.group(2) else 0
        return tens * 10 + ones
    return None


def parse_years(raw: str):
    """把年代字符串解析成 (start, end)，负数表示公元前。解析不了返回 None。

    只取第一段（「1466-1536／1478-1535」取前者），这是排序用的主键，
    不是学术年代考订。
    """
    s = (raw or "").strip()
    if not s or s in ("—", "-", "?", "不详"):
        return None
    # 「A／B」并列取第一个
    s = re.split(r"[／/]", s)[0].strip()

    # 前6世纪 / 前5世纪（中文或阿拉伯数字都收）
    m = re.fullmatch(r"约?前([一二三四五六七八九十]+|\d+)世纪", s)
    if m:
        c = _num(m.group(1))
        if c:
            return (-c * 100, -c * 100 + 100)
    # 约前6-4世纪
    m = re.fullmatch(r"约?前([一二三四五六七八九十]+|\d+)-([一二三四五六七八九十]+|\d+)世纪", s)
    if m:
        a, b = _num(m.group(1)), _num(m.group(2))
        if a and b:
            return (-a * 100, -b * 100 + 100)
    # 1920s-30s
    m = re.fullmatch(r"(\d{4})s-(\d{2})s", s)
    if m:
        a = int(m.group(1))
        b = int(str(a)[:2] + m.group(2))
        return (a, b + 9)
    # 前3世纪-180（世纪起、年份止）→ 取世纪起点
    m = re.fullmatch(r"约?前([一二三四五六七八九十]+|\d+)世纪-\d+", s)
    if m:
        c = _num(m.group(1))
        if c:
            return (-c * 100, -c * 100 + 100)
    # 前570-495
    m = re.fullmatch(r"约?前(\d+)-(\d+)", s)
    if m:
        return (-int(m.group(1)), -int(m.group(2)))
    # 前370
    m = re.fullmatch(r"约?前(\d+)", s)
    if m:
        return (-int(m.group(1)), -int(m.group(1)))
    # 354-430
    m = re.fullmatch(r"约?(\d+)-(\d+)", s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    # 1940- （在世）
    m = re.fullmatch(r"约?(\d+)-", s)
    if m:
        return (int(m.group(1)), None)
    # 单年份
    m = re.fullmatch(r"约?(\d+)", s)
    if m:
        return (int(m.group(1)), int(m.group(1)))
    # 战国-汉初 这类：交给人工，不强解
    return None


def load():
    """返回按分区组织的节点列表：[{code, name, years, raw, line}]"""
    text = MAP.read_text(encoding="utf-8")
    sections, cur = [], None
    for raw_line in text.splitlines():
        if raw_line.startswith("### "):
            cur = {"title": raw_line[4:].strip(), "rows": [], "line": None}
            sections.append(cur)
        elif raw_line.startswith("## "):
            cur = None
        elif cur is not None and raw_line.startswith("**") and raw_line.rstrip().endswith("**"):
            cur["line"] = raw_line.strip("*").strip()
            cur["rows"].append({"__sep__": cur["line"]})
        elif cur is not None and raw_line.startswith("|"):
            cells = [c.strip() for c in raw_line.strip("|").split("|")]
            if len(cells) >= 3 and re.fullmatch(r"[WC]-\d-\d+", cells[0]):
                cur["rows"].append({
                    "code": cells[0], "name": cells[1], "raw": cells[2],
                    "years": parse_years(cells[2]),
                })
    return [s for s in sections if s["rows"]]


def fmt(y):
    if y is None:
        return "????"
    a, b = y
    f = lambda n: f"前{-n}" if n < 0 else str(n)
    if b is None:
        return f"{f(a)}–"
    return f(a) if a == b else f"{f(a)}–{f(b)}"


def main():
    show_all = "--all" in sys.argv
    secs = load()
    total = sum(len([r for r in s["rows"] if "__sep__" not in r]) for s in secs)
    problems = 0

    out(f"地图节点共 {total} 个，分 {len(secs)} 个分区。\n")
    out("判据：同一线索块内，按行的先后，起始年应单调不减；相等时按结束年。\n"
        "块与块之间只按线索锚点排序，允许回跳——那是换房间，不是排错。\n")

    for sec in secs:
        out(f"── {sec['title']}（{len(sec['rows'])} 行）")
        prev = None
        prev_row = None
        for row in sec["rows"]:
            if "__sep__" in row:
                prev, prev_row = None, None
                if show_all:
                    out(f"   ── {row['__sep__']} ──")
                continue
            y = row["years"]
            if show_all:
                out(f"   {row['code']:<9}{fmt(y):<18}{row['name'][:22]}")
            if y is None:
                if show_all:
                    out(f"       ↑ 年代无法解析（{row['raw']}），跳过比较")
                continue
            if prev is not None:
                # 前一条起始年比当前大 → 时间倒错
                if prev[0] > y[0]:
                    problems += 1
                    out(f"   ✗ 倒错：{prev_row['code']} {fmt(prev)} → "
                        f"{row['code']} {fmt(y)}   （{prev_row['name'][:14]} → {row['name'][:14]}）")
                elif prev[0] == y[0] and (prev[1] if prev[1] is not None else 9999) > (y[1] if y[1] is not None else 9999):
                    problems += 1
                    out(f"   ✗ 同年却按卒年反了：{prev_row['code']} {fmt(prev)} → "
                        f"{row['code']} {fmt(y)}   （{prev_row['name'][:14]} → {row['name'][:14]}）")
            prev, prev_row = y, row
        out("")

    out(f"合计时间倒错 {problems} 处。")


if __name__ == "__main__":
    main()
