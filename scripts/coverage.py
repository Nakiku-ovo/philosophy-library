# -*- coding: utf-8 -*-
"""地图 × 库 覆盖对照：告诉你「现在能写哪一篇」。

用法：
    python scripts/coverage.py              # 按苦因每一栏的覆盖率
    python scripts/coverage.py --nodes      # 每个地图节点的条目数
    python scripts/coverage.py --next       # 只列出缺得最少的栏（优先补哪栏）

判据只有一条：一个地图码下面挂了几个条目（source / excerpt / judgment 都算）。
有原文（type: source）才算「可写」；只有判断没有原文的，标「半」。
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict

from _common import ROOT, iter_items, out

MAP = ROOT / "地图.md"


def load_map():
    """返回 (code -> 人名, [苦因栏...])"""
    if not MAP.exists():
        out(f"找不到地图文件：{MAP}")
        sys.exit(1)
    text = MAP.read_text(encoding="utf-8")

    names = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        m = re.fullmatch(r"([WC]-\d-\d+)", cells[0])
        if m:
            names[m.group(1)] = cells[1]

    buckets = []
    if "### 按苦因" in text:
        sec = text.split("### 按苦因", 1)[1]
        for line in sec.splitlines():
            if not line.startswith("|") or "---" in line:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 2 or cells[0] in ("苦因", ""):
                continue
            codes = re.findall(r"([WC]-\d-\d+)", cells[1])
            if codes:
                buckets.append((cells[0], cells[1], codes))
    return names, buckets


def load_coverage():
    """code -> {'source': n, 'excerpt': n, 'judgment': n, 'theme': n}"""
    cov = defaultdict(lambda: defaultdict(int))
    for _p, meta, _body in iter_items():
        code = str(meta.get("map") or "").strip()
        if re.fullmatch(r"[WC]-\d-\d+", code):
            cov[code][str(meta.get("type", "?"))] += 1
    return cov


def bar(have: int, total: int, width: int = 10) -> str:
    filled = round(width * have / total) if total else 0
    return "█" * filled + "·" * (width - filled)


def main():
    args = sys.argv[1:]
    names, buckets = load_map()
    cov = load_coverage()

    if "--nodes" in args or "-n" in args:
        out(f"{'码':<10}{'人物':<14}{'原文':>4}{'摘录':>4}{'判断':>4}{'主题':>4}")
        out("-" * 44)
        for code in sorted(names, key=lambda c: (c[0] != "W", c.split("-")[0], int(c.split("-")[1]), int(c.split("-")[2]))):
            c = cov.get(code, {})
            mark = "●" if c.get("source") else ("○" if not c else "◐")
            out(f"{code:<10}{names[code][:12]:<14}{c.get('source',0):>4}{c.get('excerpt',0):>4}"
                f"{c.get('judgment',0):>4}{c.get('theme',0):>4}  {mark}")
        empty = [c for c in names if c not in cov]
        out(f"\n共 {len(names)} 个节点：有原文 {sum(1 for c in names if cov.get(c,{}).get('source'))}，"
            f"仅摘录/判断 {sum(1 for c in names if cov.get(c) and not cov.get(c,{}).get('source'))}，"
            f"完全空白 {len(empty)}")
        return

    rows = []
    for name, who, codes in buckets:
        has_src = [c for c in codes if cov.get(c, {}).get("source")]
        has_any = [c for c in codes if cov.get(c)]
        rows.append((name, codes, has_src, has_any))

    if "--next" in args:
        rows.sort(key=lambda r: (-len(r[2]), len(r[1])))
        out("按「缺得最少」排序，补完就能写的栏：\n")
    else:
        out("按苦因 × 库覆盖（判据：该栏里有多少人已有原文）\n")

    out(f"{'苦因':<16}{'人数':>4}{'覆盖':>12}{'可写':>5}  缺谁")
    out("-" * 78)
    for name, codes, has_src, has_any in rows:
        miss = [c for c in codes if c not in has_src]
        miss_s = "、".join(f"{names.get(c,c)}" for c in miss[:4])
        if len(miss) > 4:
            miss_s += f" 等{len(miss)}人"
        ready = "✓" if has_src else ("半" if has_any else "—")
        out(f"{name:<16}{len(codes):>4}  {bar(len(has_src), len(codes))} {len(has_src):>2}"
            f"{ready:>5}  {miss_s}")

    writable = [r for r in rows if r[2]]
    out(f"\n13 栏中可开写 {len(writable)} 栏；"
        f"已有原文的节点 {sum(1 for c in names if cov.get(c,{}).get('source'))}/{len(names)}")


if __name__ == "__main__":
    main()
