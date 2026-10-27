# -*- coding: utf-8 -*-
"""按《排序规则》重算节点顺序，输出预览或写回地图。

用法：
    python scripts/order_sort.py              # 只预览，不动地图
    python scripts/order_sort.py --diff       # 只列出位置变动的行
    python scripts/order_sort.py --apply      # 写回地图（会先备份）

排序键（严格按序比较，前一级相同才看下一级）：
    1. 时期 period       —— 按 config/order.json 中 periods 的先后
    2. 线索锚点 line     —— 该线索最早成员的生年（见 line_anchor）
    3. 生年 birth
    4. 卒年 death        —— 在世者视为无穷大，排在同年生者之末
    5. ID                —— 兜底，保证结果唯一
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

from _common import ROOT, out

MAP = ROOT / "地图.md"
CFG = ROOT / "config" / "order.json"

CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
      "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}


def _num(s: str):
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s in CN:
        return CN[s]
    m = re.fullmatch(r"([一二三四五六七八九])?十([一二三四五六七八九])?", s)
    if m:
        t = CN.get(m.group(1), 1) if m.group(1) else 1
        o = CN.get(m.group(2), 0) if m.group(2) else 0
        return t * 10 + o
    return None


def parse_bd(raw: str):
    """返回 (birth, death)。death 为 None 表示在世或不明。"""
    s = (raw or "").strip()
    if not s or s in ("—", "-", "?", "不详"):
        return (None, None)
    s = re.split(r"[／/]", s)[0].strip()

    m = re.fullmatch(r"约?前([一二三四五六七八九十]+|\d+)世纪-(\d+)", s)
    if m:
        c = _num(m.group(1))
        if c:
            return (-c * 100, -int(m.group(2)))
        return (None, None)

    m = re.fullmatch(r"约?前([一二三四五六七八九十]+|\d+)世纪", s)
    if m:
        c = _num(m.group(1))
        return (-c * 100, -c * 100 + 100) if c else (None, None)

    m = re.fullmatch(r"约?前([一二三四五六七八九十]+|\d+)-([一二三四五六七八九十]+|\d+)世纪", s)
    if m:
        a, b = _num(m.group(1)), _num(m.group(2))
        return (-a * 100, -b * 100 + 100) if a and b else (None, None)

    m = re.fullmatch(r"(\d{4})s-(\d{2})s", s)
    if m:
        a = int(m.group(1))
        return (a, int(str(a)[:2] + m.group(2)) + 9)

    m = re.fullmatch(r"约?前(\d+)-(\d+)", s)
    if m:
        return (-int(m.group(1)), -int(m.group(2)))

    m = re.fullmatch(r"约?前(\d+)", s)
    if m:
        return (-int(m.group(1)), -int(m.group(1)))

    m = re.fullmatch(r"(\d+)-(\d+)", s)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    m = re.fullmatch(r"(\d+)-", s)
    if m:
        return (int(m.group(1)), None)

    m = re.fullmatch(r"约?(\d+)", s)
    if m:
        return (int(m.group(1)), int(m.group(1)))

    return (None, None)


def load_nodes(path=None):
    """解析地图节点表：code -> {code,name,raw,line_no,birth,death}"""
    path = Path(path) if path else MAP
    lines = path.read_text(encoding="utf-8").splitlines()
    nodes = {}
    for i, ln in enumerate(lines):
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) < 3 or not re.fullmatch(r"[WC]-\d-\d+", cells[0]):
            continue
        b, d = parse_bd(cells[2])
        nodes[cells[0]] = {"code": cells[0], "name": cells[1], "raw": cells[2],
                           "birth": b, "death": d, "row": i, "cells": cells}
    return lines, nodes


def build_order(nodes, cfg):
    pidx = {p["code"]: i for i, p in enumerate(cfg["periods"])}
    pmeta = {p["code"]: p for p in cfg["periods"]}
    ov = cfg.get("birth_override", {})
    anchors = cfg.get("line_anchor", {})
    assigned = cfg["nodes"]

    rows, unassigned = [], []
    for code, n in nodes.items():
        if code in cfg.get("not_persons", []):
            continue
        a = assigned.get(code)
        if not a:
            unassigned.append(code)
            continue
        birth = ov.get(code, {}).get("birth", n["birth"])
        death = n["death"]
        key = f"{a['period']}|{a['line']}"
        anchor = anchors.get(key)
        if anchor is None:
            anchor = birth if birth is not None else 0
        rows.append({
            **n, "period": a["period"], "line": a["line"],
            "birth": birth, "death": death,
            "porder": pidx.get(a["period"], 999),
            "anchor": anchor,
            "bsort": birth if birth is not None else 9999,
            "dsort": death if death is not None else 9999,
        })

    rows.sort(key=lambda r: (r["porder"], r["anchor"], r["bsort"], r["dsort"], r["code"]))
    return rows, unassigned, pmeta


def fmt_bd(r):
    b, d = r["birth"], r["death"]
    f = lambda n: f"前{-n}" if n < 0 else str(n)
    if b is None:
        return r["raw"]
    if d is None:
        return f"{f(b)}–"
    return f(b) if b == d else f"{f(b)}–{f(d)}"


def yr(n: int) -> str:
    if n < 0:
        return f"前{-n}"
    if n >= 2100:
        return "今"
    return str(n)


HEADER = "| 码 | 人物 | 年代 | 著作 | 主张 | 痛苦接口 | 现状 |\n|---|---|---|---|---|---|---|"


def emit(rows, pmeta, path: Path):
    """生成独立的排序视图文件，不动地图本体。"""
    buf = ["# 哲学史节点排序视图", "",
           "> 由 `scripts/order_sort.py --emit` 生成，**不要手改**——改 `config/order.json` 后重跑。",
           "> 规则见《排序规则.md》。ID 是主键，行序是视图，索引是入口。", ""]
    last_p = None
    for r in rows:
        if r["period"] != last_p:
            p = pmeta[r["period"]]
            trad = p.get("tradition", "")
            buf += ["", f"## {'西方' if trad == '西' else '中国'}哲学 · {p['name']}（{yr(p['start'])} – {yr(p['end'])}）", ""]
            last_p, last_l = r["period"], None
        if r["line"] != last_l:
            buf += ["", f"**{r['line']}**", "", HEADER]
            last_l = r["line"]
        c = r["cells"]
        rest = c[3:7] if len(c) >= 7 else [""] * 4
        buf.append(f"| {r['code']} | {c[1]} | {c[2]} | " + " | ".join(rest) + " |")
    path.write_text("\n".join(buf) + "\n", encoding="utf-8")
    return path


def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    lines, nodes = load_nodes()
    rows, unassigned, pmeta = build_order(nodes, cfg)

    if unassigned:
        out(f"⚠ 以下节点未在 config/order.json 中指定 period/line，已跳过：{unassigned}\n")

    old_order = [n["code"] for n in sorted(nodes.values(), key=lambda x: x["row"])]
    new_order = [r["code"] for r in rows]
    common = [c for c in new_order if c in set(old_order)]
    moved = sum(1 for i, c in enumerate(common) if old_order[i] != c)

    if "--diff" in sys.argv:
        out("ID       人物                    原位置  新位置")
        out("-" * 48)
        for newpos, r in enumerate(rows, 1):
            oldpos = next((i + 1 for i, c in enumerate(old_order) if c == r["code"]), None)
            if oldpos != newpos:
                out(f"{r['code']:<9}{r['name'][:20]:<22}{oldpos:>6}{newpos:>6}")
        out(f"\n位置变动 {moved} / {len(rows)} 行")
        return

    if "--emit" in sys.argv:
        i = sys.argv.index("--emit")
        target = Path(sys.argv[i + 1]) if len(sys.argv) > i + 1 else ROOT / "排序视图.md"
        emit(rows, pmeta, target)
        out(f"已生成 {target.name}（{len(rows)} 行），地图本体未改动。")
        return

    last_p = last_l = None
    for r in rows:
        if r["period"] != last_p:
            p = pmeta[r["period"]]
            out("")
            out(f"═══ {p['name']}（{yr(p['start'])} – {yr(p['end'])}） ═══")
            last_p, last_l = r["period"], None
        if r["line"] != last_l:
            out(f"  〔{r['line']}〕")
            last_l = r["line"]
        out(f"    {r['code']:<9}{fmt_bd(r):<16}{r['name'][:26]}")

    out("")
    out(f"合计 {len(rows)} 行；位置相对现状变动 {moved} 处。")
    if "--apply" not in sys.argv:
        out("（预览模式，未改动地图。加 --apply 写回）")


if __name__ == "__main__":
    main()
