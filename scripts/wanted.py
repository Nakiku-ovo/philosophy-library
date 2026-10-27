#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出「你引用了但库里没有原文」的书，并给出合法获取入口。

用法：
    python scripts/wanted.py              # 只看缺口
    python scripts/wanted.py --resolve    # 逐本去查公版全文与馆藏入口
    python scripts/wanted.py 精神现象学 --add   # 手动追加一本想找的

为什么按「引用」算缺口：你在摘录里写下的每一本书，都是你欠自己的一次对原文的核对。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import INDEX, iter_items, out  # noqa: E402


def norm(s: str) -> str:
    return str(s or "").strip().strip("《》").replace(" ", "").lower()


def main():
    want_resolve = "--resolve" in sys.argv
    manual = []
    if "--add" in sys.argv:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        manual = args

    have, cited = set(), {}
    for _path, meta, _body in iter_items():
        w = norm(meta.get("work"))
        if not w or w == "todo":
            continue
        if meta.get("type") == "source":
            have.add(w)
        elif meta.get("type") == "excerpt":
            # 只把「摘录里引用的书」算缺口；judgment 里的 work 是你自己的作品，不欠原文
            cited.setdefault(w, {"work": meta.get("work"), "author": meta.get("author"), "n": 0})
            cited[w]["n"] += 1

    gaps = {w: v for w, v in cited.items() if w not in have}
    for m in manual:
        gaps.setdefault(norm(m), {"work": m, "author": "—", "n": 0})

    lines = ["# 缺口清单", ""]
    if not gaps:
        out("✓ 没有缺口：你引用过的书，库里都有原文。")
        lines.append("_没有缺口。_")
    else:
        out(f"缺 {len(gaps)} 部书（被引用过、但没有原文入库）：\n")
        lines += ["| 著作 | 作者 | 被引用次数 | 合法入口 |", "|---|---|---|---|"]
        for w, v in sorted(gaps.items(), key=lambda kv: -kv[1]["n"]):
            out(f"  · 《{v['work']}》 ／ {v['author']} ／ 被引 {v['n']} 次")
            link = "—"
            if want_resolve:
                q = str(v["work"])
                try:
                    r = subprocess.run(
                        [sys.executable, str(Path(__file__).parent / "resolve.py"), q, "--provider", "library"],
                        capture_output=True, text=True, timeout=40, encoding="utf-8",
                    )
                    for ln in (r.stdout or "").splitlines():
                        if ln.strip().startswith("http"):
                            link = ln.strip()
                            break
                except Exception:
                    link = "（查询失败）"
                out(f"      → {link}")
            lines.append(f"| {v['work']} | {v['author']} | {v['n']} | {link} |")

    lines += [
        "",
        "> 缺口不是错误。哲学库的价值一半在「有什么」，一半在「我知道自己缺什么」。",
    ]
    INDEX.mkdir(parents=True, exist_ok=True)
    (INDEX / "wanted.md").write_text("\n".join(lines), encoding="utf-8")
    out(f"\n已写入 {INDEX / 'wanted.md'}")


if __name__ == "__main__":
    main()
