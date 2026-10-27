#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫全库，列出元信息没填全的条目，按缺项分组。

用法：
    python scripts/scan.py            # 全部问题
    python scripts/scan.py --fix-list # 只输出文件名清单，方便逐个补

为什么要有这个：一个空着「版次」的文件，三个月后你根本不知道自己读的是哪个译本。
这本书能引不能引、能不能分享，全靠这两格。
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import LIB, REQUIRED, iter_items, out  # noqa: E402

LEGAL = ["pd_text", "pd_edition"]
SOFT = ["year", "work_original", "translator", "origin_of", "tags"]


def main():
    only_list = "--fix-list" in sys.argv
    problems = defaultdict(list)
    total = 0

    for path, meta, body in iter_items():
        total += 1
        rel = path.relative_to(LIB.parent)
        is_source = meta.get("type") == "source"
        need = REQUIRED + (LEGAL if is_source else [])
        for key in need:
            val = str(meta.get(key, "")).strip()
            if val in ("", "TODO"):
                problems[key].append((rel, meta.get("title", "")))
        for key in SOFT:
            val = meta.get(key)
            if val in ("", "TODO", [], None):
                problems[key].append((rel, meta.get("title", "")))
        if len(body.strip()) < 60 and meta.get("type") == "source":
            problems["正文过短(可能抽取失败)"].append((rel, meta.get("title", "")))
        if meta.get("status", "ok") == "todo":
            pass  # 由 REQUIRED 反映，不重复计

    out(f"全库 {total} 个条目，扫描完成。\n")
    if not problems:
        out("✓ 没有缺口，可以开始提问了。")
        return

    hard = ["author", "work", "locator", "edition", "pd_text", "pd_edition"]
    out("══ 必须先补（不补就不能引用 / 不能判断能否分享）══")
    for key in hard:
        if key in problems:
            out(f"\n[{key}]  缺 {len(problems[key])} 处")
            for rel, title in problems[key][:40]:
                out(f"    {rel}   « {title}")
            if len(problems[key]) > 40:
                out(f"    …还有 {len(problems[key]) - 40} 个")

    rest = [k for k in problems if k not in hard]
    if rest:
        out("\n── 建议补（影响检索与追溯）──")
        for key in rest:
            out(f"[{key}]  缺 {len(problems[key])} 处")

    out("\n提示：pd_text 指原文是否公有领域，pd_edition 指你手上这个版次（含译本）是否公有领域。")
    out("      两个都是 true，pack.py 才会把全文放进分享包；否则只留书目与定位符。")
    out("      拿不准就填 false——保守不会错，填错会出事。")


if __name__ == "__main__":
    main()
