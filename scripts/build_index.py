#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 index/index.md（给人看）和 index/index.json（给程序用）。

用法：
    python scripts/build_index.py

每次投放 / 修改素材后跑一遍。它会顺手做一件重要的事：
发现同一个知识点记了两个不同的最早出处 —— 那说明你记错了一个，或者你正在看到一场争论。
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import INDEX, LIB, iter_items, out  # noqa: E402

SHARE_MARK = {True: "可", False: "否"}


def share_flag(meta) -> str:
    a = meta.get("pd_text") is True
    b = meta.get("pd_edition") is True
    if a and b:
        return "可"
    if str(meta.get("pd_text")) == "TODO" or str(meta.get("pd_edition")) == "TODO":
        return "未判"
    return "否"


def main():
    items = []
    by_work = defaultdict(list)
    by_term = defaultdict(list)

    for path, meta, body in iter_items():
        rel = path.relative_to(LIB.parent).as_posix()
        items.append({"path": rel, "chars": len(body), **meta})
        if meta.get("work") and meta.get("type") == "source":
            by_work[(meta.get("work"), meta.get("author"))].append(meta)
        terms = meta.get("origin_of") or []
        if isinstance(terms, str):
            terms = [terms]
        for t in terms:
            by_term[t].append((meta, rel))

    INDEX.mkdir(parents=True, exist_ok=True)
    (INDEX / "index.json").write_text(
        json.dumps(
            {"generated": time.strftime("%Y-%m-%d %H:%M"), "count": len(items), "items": items},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    L = []
    L.append("# 索引")
    L.append("")
    L.append(f"> 自动生成于 {time.strftime('%Y-%m-%d %H:%M')}｜共 {len(items)} 条｜著作 {len(by_work)} 部")
    L.append("> 不要手改这个文件，改素材后重跑 `python scripts/build_index.py`。")
    L.append("")

    L.append("## 一、著作总表")
    L.append("")
    L.append("| 著作 | 作者 | 版次 | 章节数 | 可否分享全文 |")
    L.append("|---|---|---|---|---|")
    for (work, author), metas in sorted(by_work.items(), key=lambda kv: (str(kv[0][1]), str(kv[0][0]))):
        share = "可" if all(share_flag(m) == "可" for m in metas) else (
            "未判" if any(share_flag(m) == "未判" for m in metas) else "否"
        )
        L.append(f"| {work} | {author} | {metas[0].get('edition','')} | {len(metas)} | {share} |")
    L.append("")

    conflicts = {t: v for t, v in by_term.items() if len({(m.get('author'), m.get('work')) for m, _ in v}) > 1}
    L.append("## 二、知识点出处表")
    L.append("")
    if not by_term:
        L.append("_还没有条目填了 `origin_of`。填法：`origin_of: [我思故我在, 心物二元论]`_")
    else:
        L.append("| 知识点 | 最早出处 | 定位符 | 库里条目 |")
        L.append("|---|---|---|---|")
        for term, refs in sorted(by_term.items()):
            m = refs[0][0]
            L.append(f"| {term} | {m.get('author')}·《{m.get('work')}》 | {m.get('locator')} | {len(refs)} |")
    L.append("")

    if conflicts:
        L.append("## ⚠ 出处冲突（同一知识点记了不同出处，必须裁定）")
        L.append("")
        for term, refs in conflicts.items():
            L.append(f"**{term}**")
            for m, rel in refs:
                L.append(f"- {m.get('author')}·《{m.get('work')}》 {m.get('locator')} — `{rel}`")
            L.append("")

    L.append("## 三、全部条目")
    L.append("")
    L.append("| 类型 | 标题 | 作者·著作 | 定位符 | 标签 | 状态 |")
    L.append("|---|---|---|---|---|---|")
    for it in items:
        author = it.get("author") or "—"
        work = it.get("work") or "—"
        tags = it.get("tags")
        tags = "/".join(tags) if isinstance(tags, list) else (tags or "")
        L.append(
            f"| {it.get('type')} | {it.get('title')} | {author}·《{work}》 | "
            f"{it.get('locator')} | {tags} | {it.get('status','ok')} |"
        )
    L.append("")

    (INDEX / "index.md").write_text("\n".join(L), encoding="utf-8")

    out(f"✓ index.md / index.json 已生成：{len(items)} 条，{len(by_work)} 部著作")
    if conflicts:
        out(f"⚠ 有 {len(conflicts)} 个知识点的出处互相矛盾，见 index.md 第二节下方")
    if not items:
        out("  （库是空的。先把书丢进 library/01-sources/ 再跑 extract.py）")


if __name__ == "__main__":
    main()
