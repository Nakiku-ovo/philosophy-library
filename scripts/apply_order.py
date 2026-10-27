# -*- coding: utf-8 -*-
"""把地图本体按《排序规则》落地：重排节点表，按时期分节、按线索分块。

用法：
    python scripts/apply_order.py --dry     # 只看会变成什么样，不写
    python scripts/apply_order.py --apply   # 写回（自动备份 地图.md.bak）

只重写「一、西方哲学」与「二、中国哲学」两节，其余章节原样保留。
ID 一个都不改，只改行的先后。
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import ROOT
from order_sort import load_nodes, build_order

MAP = ROOT / "地图.md"
CFG = ROOT / "config" / "order.json"
HEADER = "| 码 | 人物 | 年代 | 著作 | 主张 | 痛苦接口 | 现状 |\n|---|---|---|---|---|---|---|"

APPENDIX = """
### 附：宗教与苦谛（非人物条目）

> 这两条不是人物，是主题。混在人物表里无论怎么排都不对——公元前 5 世纪的条目排在二十世纪学者之后，不是排错，是放错了列。故另立一节，不参与人物排序。

| 码 | 条目 | 年代 | 文献 | 主张 | 痛苦接口 | 现状 |
|---|---|---|---|---|---|---|
| C-3-04 | 印度佛教苦谛 | 前5世纪 | 《阿含经》四圣谛 | 苦、集、灭、道；三苦 | **执着与我执** | ● |
| C-3-05 | 基督教、伊斯兰教、犹太教、印度教 | — | 《圣经》《古兰经》《塔木德》《奥义书》 | 原罪／考验／契约／业力 | **各自的苦因与救赎** | ● |"""

INTRO_W = """> 骨架来源：罗素《西方哲学史》三卷（古代 30 章／天主教 15 章／近代 31 章），边界之外由补卷承接。
> **本节按哲学史脉络重排**：时期 → 线索 → 生年。原来的罗素卷次不再决定位置，只作为来源记录。
> ID 是主键、永不变；行序是视图、由 `config/order.json` 算出。**编号不连续是正常的**，跳号不代表缺漏。"""

INTRO_C = """> 骨架来源：冯友兰《中国哲学史》两卷本（子学时代 16 章／经学时代 16 章），边界之外由补卷承接。
> **本节按哲学史脉络重排**：时期 → 线索 → 生年。原来的冯书篇次不再决定位置，只作为来源记录。
> ID 是主键、永不变；行序是视图。编号不连续是正常的。"""


def yr(n: int) -> str:
    if n < 0:
        return f"前{-n}"
    if n >= 2100:
        return "今"
    return str(n)


def build_section(rows, pmeta, intro: str, title: str) -> str:
    buf = [f"## {title}", "", intro, ""]
    last_p = last_l = None
    for r in rows:
        if r["period"] != last_p:
            p = pmeta[r["period"]]
            buf += [f"### {p['name']}（{yr(p['start'])} – {yr(p['end'])}）", ""]
            last_p, last_l = r["period"], None
        if r["line"] != last_l:
            buf += [f"**{r['line']}**", "", HEADER]
            last_l = r["line"]
        c = r["cells"]
        rest = c[3:7] if len(c) >= 7 else [""] * 4
        buf.append(f"| {c[0]} | {c[1]} | {c[2]} | " + " | ".join(rest) + " |")
    return "\n".join(buf)


def main():
    dry = "--apply" not in sys.argv
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    _lines, nodes = load_nodes()
    rows, unassigned, pmeta = build_order(nodes, cfg)
    if unassigned:
        print("未分配节点：", unassigned)
        return

    w_rows = [r for r in rows if r["period"].startswith("W")]
    c_rows = [r for r in rows if r["period"].startswith("C")]

    text = MAP.read_text(encoding="utf-8")
    parts = text.split("\n## ")
    head = parts[0]
    sections = {}
    order = []
    for seg in parts[1:]:
        name = seg.split("\n", 1)[0].strip()
        sections[name] = "## " + seg
        order.append(name)

    # 找出「一、西方哲学」「二、中国哲学」，其余原样保留
    w_key = next(k for k in order if k.startswith("一、"))
    c_key = next(k for k in order if k.startswith("二、"))
    others = [k for k in order if k not in (w_key, c_key)]

    new_w = build_section(w_rows, pmeta, INTRO_W, w_key)
    new_c = build_section(c_rows, pmeta, INTRO_C, c_key)
    new_c += "\n" + APPENDIX

    # 原「三、关系边」等章节的标题不变，但要把编号顺延说明加在文首
    head = head.replace(
        "> 用法见文末。共 116 个节点（西 80 / 中 36）。",
        "> 用法见文末。共 116 个节点（西 80 / 中 36），其中 114 条是人物、2 条是主题（见文末附录）。")
    head = head.replace(
        "> **行序不等于排好的顺序。** 下方各卷按的是罗素／冯友兰的章节次第，不是统一的时间轴。想看按哲学史脉络重排的结果，读 `排序视图.md`（由 `scripts/order_sort.py --emit` 生成）；排序依据见《排序规则.md》。",
        "> **行序已按哲学史脉络重排**：时期 → 线索 → 生年。规则见《排序规则.md》，归属字段在 `config/order.json`；改完跑 `python scripts/apply_order.py --apply` 重排，再跑 `order_check.py` 验有没有排乱。原始章节序留了一份快照在 `地图-罗素序.md`，供对照。")
    assembled = [head.rstrip("\n"), "", new_w, "", new_c, ""]
    for k in others:
        assembled.append(sections[k])
        assembled.append("")
    result = "\n".join(assembled).rstrip("\n") + "\n"

    if dry:
        tmp = ROOT / "_preview_地图.md"
        tmp.write_text(result, encoding="utf-8")
        print(f"[预览] 已写出 {tmp.name}（{len(result.splitlines())} 行），地图未改动。")
        print(f"  西方 {len(w_rows)} 行 / 中国 {len(c_rows)} 行 / 其余 {len(others)} 节原样保留")
        print(f"  时期 {len({r['period'] for r in rows})} 个 / 线索 {len({(r['period'], r['line']) for r in rows})} 块")
        return

    shutil.copy2(MAP, ROOT / "地图.md.bak")
    baseline = ROOT / "地图-罗素序.md"
    if not baseline.exists():
        shutil.copy2(MAP, baseline)
        print("  已另存原始序快照：地图-罗素序.md（供对照，不再改动）")
    MAP.write_text(result, encoding="utf-8")
    print(f"已写回 地图.md（{len(result.splitlines())} 行）。备份：地图.md.bak")
    print(f"  西方 {len(w_rows)} 行 / 中国 {len(c_rows)} 行 / 其余 {len(others)} 节原样保留")


if __name__ == "__main__":
    main()
