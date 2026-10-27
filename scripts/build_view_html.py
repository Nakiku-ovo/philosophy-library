# -*- coding: utf-8 -*-
"""生成《排序验收》HTML：数据全部从地图与 config/order.json 现算，不手填。

用法：
    python scripts/build_view_html.py
输出：
    排序验收.html
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import ROOT
from order_sort import load_nodes, build_order, parse_bd

CFG = ROOT / "config" / "order.json"
OUT = ROOT / "排序验收.html"

# 22 处倒错的归因。键是（前一个节点, 后一个节点），值是类型。
# 类型只用三种：真错 / 跳层 / 特例 / 非人
KIND = {
    ("W-1-05", "W-1-06"): "真错",
    ("W-1-07", "W-1-08"): "跳层",
    ("W-1-11", "W-1-12"): "跳层",
    ("W-3-14", "W-3-15"): "真错",
    ("W-4-05", "W-4-06"): "特例",
    ("W-4-07", "W-4-08"): "跳层",
    ("W-4-12", "W-4-13"): "真错",
    ("W-4-15", "W-4-16"): "跳层",
    ("W-4-17", "W-4-18"): "真错",
    ("W-4-21", "W-4-22"): "真错",
    ("W-4-22", "W-4-23"): "真错",
    ("W-4-23", "W-4-24"): "跳层",
    ("W-4-26", "W-4-27"): "跳层",
    ("W-4-27", "W-4-28"): "真错",
    ("W-4-31", "W-4-32"): "真错",
    ("C-1-03", "C-1-04"): "特例",
    ("C-1-05", "C-1-06"): "真错",
    ("C-1-09", "C-1-11"): "跳层",
    ("C-2-09", "C-2-10"): "真错",
    ("C-2-11", "C-2-12"): "真错",
    ("C-3-03", "C-3-04"): "非人",
}

# 每处的解释（一句话，说清为什么）
WHY = {
    ("W-1-05", "W-1-06"): "阿那克萨哥拉比恩培多克勒年长六年，同属自然哲学，没有理由排后面",
    ("W-1-07", "W-1-08"): "从自然哲学切到智者，位置往回退三十年",
    ("W-1-11", "W-1-12"): "从古典切到希腊化，犬儒学派创始人比亚里士多德年长",
    ("W-3-14", "W-3-15"): "同生于 1788，拜伦卒于 1824，按卒年该在前",
    ("W-4-05", "W-4-06"): "维也纳学派是集体，没有生年，与个人不可比",
    ("W-4-07", "W-4-08"): "从分析哲学切到现象学，往回跳 102 年，全书最大一跳",
    ("W-4-12", "W-4-13"): "萨特生于 1905，梅洛-庞蒂 1908，同属现象学",
    ("W-4-15", "W-4-16"): "从存在主义切到结构主义",
    ("W-4-17", "W-4-18"): "拉康生于 1901，列维-斯特劳斯 1908，同属结构主义",
    ("W-4-21", "W-4-22"): "德勒兹 1925 早于德里达 1930，同属后结构",
    ("W-4-22", "W-4-23"): "利奥塔 1924 早于德勒兹 1925，同属后结构",
    ("W-4-23", "W-4-24"): "从后结构切到法兰克福学派",
    ("W-4-26", "W-4-27"): "从法兰克福切到生命哲学，往回跳七十年",
    ("W-4-27", "W-4-28"): "詹姆斯生于 1842，柏格森 1859，同属生命哲学与实用主义",
    ("W-4-31", "W-4-32"): "威廉斯生于 1929，帕菲特 1942，同属当代伦理学",
    ("C-1-03", "C-1-04"): "老子生卒是学术悬案，此处从冯友兰说《老子》成书晚于《孟子》",
    ("C-1-05", "C-1-06"): "惠施生于前 370，庄子前 369，差一年",
    ("C-1-09", "C-1-11"): "从法家切到阴阳家，邹衍年长于韩非",
    ("C-2-09", "C-2-10"): "慧能生于 638，法藏 643，同属中国佛学",
    ("C-2-11", "C-2-12"): "邵雍生于 1011，周敦颐 1017，同属理学",
    ("C-3-03", "C-3-04"): "印度佛教苦谛不是人物，是主题，混进了人物表",
}


def collect():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    lines, nodes = load_nodes()
    rows, unassigned, pmeta = build_order(nodes, cfg)

    # 旧序固定对着原始章节序快照，重排后对比才不会失真
    base = ROOT / "地图-罗素序.md"
    _l2, nodes_old = load_nodes(base if base.exists() else None)
    old_order = [n["code"] for n in sorted(nodes_old.values(), key=lambda x: x["row"])]
    old_pos = {c: i + 1 for i, c in enumerate(old_order)}

    people = []
    for i, r in enumerate(rows, 1):
        b, d = r["birth"], r["death"]
        people.append({
            "id": r["code"], "name": r["name"], "years": r["raw"],
            "birth": b, "death": d,
            "period": r["period"], "periodName": pmeta[r["period"]]["name"],
            "line": r["line"], "seq": i,
            "old": old_pos.get(r["code"]), "moved": old_pos.get(r["code"]) != i,
        })

    # 倒错：按旧顺序逐条比较。只比同一传统内部——中西两条线不共享时间轴，
    # 交界处（西 80 人末 → 中 36 人首）不构成倒错。
    incidents = []
    prev = None
    for c in old_order:
        n = nodes[c]
        b, d = parse_bd(n["raw"])
        if b is None:
            continue
        same_trad = prev is not None and prev["id"][0] == c[0]
        if same_trad and prev["birth"] > b:
            key = (prev["id"], c)
            incidents.append({
                "from": prev["id"], "fromName": prev["name"], "fromB": prev["birth"],
                "to": c, "toName": n["name"], "toB": b,
                "drop": prev["birth"] - b,
                "kind": KIND.get(key, "未归类"),
                "why": WHY.get(key, ""),
            })
        elif same_trad and prev["birth"] == b and \
                (prev["death"] if prev["death"] is not None else 9999) > (d if d is not None else 9999):
            key = (prev["id"], c)
            incidents.append({
                "from": prev["id"], "fromName": prev["name"], "fromB": prev["birth"],
                "to": c, "toName": n["name"], "toB": b,
                "drop": 0, "kind": KIND.get(key, "未归类"), "why": WHY.get(key, ""),
            })
        prev = {"id": c, "name": n["name"], "birth": b, "death": d}

    kinds = {}
    for it in incidents:
        kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1

    periods = [{"code": p["code"], "name": p["name"], "start": p["start"], "end": p["end"],
                "tradition": p.get("tradition", "")} for p in cfg["periods"]]

    seams = []
    for i in range(1, len(people)):
        a, b = people[i - 1], people[i]
        if a["birth"] is not None and b["birth"] is not None and a["birth"] > b["birth"]:
            seams.append({"from": a["name"], "to": b["name"], "drop": a["birth"] - b["birth"],
                          "fromLine": a["line"], "toLine": b["line"],
                          "cross": a["period"] != b["period"]})

    return {"seams": seams, "nSeam": len(seams),
            "people": people, "incidents": incidents, "kinds": kinds,
            "periods": periods, "nPeople": len(people), "nPeriods": len(periods),
            "nLines": len({p["line"] for p in people}), "nMoved": sum(1 for p in people if p["moved"]),
            "nNodes": len(nodes), "nInc": len(incidents)}


def esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def rows_html(data) -> str:
    out, last = [], None
    for p in data["people"]:
        if p["periodName"] != last:
            last = p["periodName"]
            out.append(
                f'<tr data-sep="1" data-period="{esc(last)}"><td colspan="7" '
                f'style="background:rgba(26,26,24,.03);font-size:12px;color:#5F5E5A;padding:8px 12px">'
                f'{esc(last)}</td></tr>')
        pos = (f'<span class="pill blue">{p["old"]} → {p["seq"]}</span>' if p["moved"]
               else f'<span class="dim mono">{p["seq"]}</span>')
        out.append(
            f'<tr data-period="{esc(p["periodName"])}" data-line="{esc(p["line"])}" '
            f'data-name="{esc(p["name"])}" data-id="{esc(p["id"])}">'
            f'<td class="mono dim">{p["seq"]}</td>'
            f'<td class="mono dim">{esc(p["id"])}</td>'
            f'<td>{esc(p["name"])}</td>'
            f'<td class="mono" style="font-size:12px;color:#5F5E5A">{esc(p["years"])}</td>'
            f'<td class="dim" style="font-size:12px">{esc(p["periodName"])}</td>'
            f'<td><span class="pill teal">{esc(p["line"])}</span></td>'
            f'<td>{pos}</td></tr>')
    return "\n".join(out)


def incident_rows_html(data) -> str:
    out = []
    for i, it in enumerate(data["incidents"], 1):
        drop = f'−{it["drop"]} 年' if it["drop"] > 0 else "同生年"
        cls = "red" if it["kind"] == "真错" else ("amber" if it["kind"] == "跳层" else "gray")
        out.append(
            f'<tr><td class="mono dim">{i}</td>'
            f'<td>{esc(it["fromName"])}<span class="dim mono" style="margin-left:6px">{esc(it["from"])}</span></td>'
            f'<td>{esc(it["toName"])}<span class="dim mono" style="margin-left:6px">{esc(it["to"])}</span></td>'
            f'<td class="mono">{drop}</td>'
            f'<td><span class="pill {cls}">{esc(it["kind"])}</span></td>'
            f'<td class="dim" style="font-size:12px;line-height:1.6">{esc(it["why"])}</td></tr>')
    return "\n".join(out)


def main():
    data = collect()
    tpl = (Path(__file__).parent / "view_template.html").read_text(encoding="utf-8")
    html = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    # 页面上的数字一律从数据取，模板里不手写，避免改数据后对不上
    html = html.replace("__N_NODES__", str(data["nNodes"]))
    html = html.replace("__N_LINES__", str(data["nLines"]))
    html = html.replace("__N_INC__", str(data["nInc"]))
    html = html.replace("__N_MOVED__", str(data["nMoved"]))
    html = html.replace("__N_PEOPLE__", str(data["nPeople"]))
    html = html.replace("__N_SEAM__", str(data["nSeam"]))
    html = html.replace("__ROWS__", rows_html(data))
    html = html.replace("__INC_ROWS__", incident_rows_html(data))
    OUT.write_text(html, encoding="utf-8")
    print(f"已生成 {OUT.name}")
    print(f"  {data['nPeople']} 人 / {data['nPeriods']} 时期 / {data['nLines']} 线索 / "
          f"倒错 {data['nInc']} 处 / 位置变动 {data['nMoved']} 人")
    print(f"  分类：{data['kinds']}")


if __name__ == "__main__":
    main()
