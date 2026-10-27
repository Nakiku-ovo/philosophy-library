#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 provider 解析一本书的合法获取入口。

用法：
    python scripts/resolve.py "meditations" --provider gutenberg
    python scripts/resolve.py "存在与时间"
    python scripts/resolve.py "第一哲学沉思集" --provider library

设计边界（不要放宽）：
· 只内置公有领域全文源与「书目 / 馆藏 / 购买」入口；
· 不内置、也不代为填写任何未授权副本站点的地址；
· 网络不通时只给可点击的检索页链接，不报错退出。
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import CONFIG, out  # noqa: E402

UA = {"User-Agent": "philosophy-library/1.0 (personal research)"}
TIMEOUT = 8


def _get(url: str):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def p_gutenberg(q):
    data = json.loads(_get(f"https://gutendex.com/books?search={urllib.parse.quote(q)}"))
    rows = []
    for b in data.get("results", [])[:5]:
        authors = ", ".join(a.get("name", "") for a in b.get("authors", [])) or "作者不详"
        fmts = b.get("formats", {})
        link = fmts.get("text/html") or fmts.get("application/epub+zip") or f"https://www.gutenberg.org/ebooks/{b['id']}"
        rows.append({
            "title": b.get("title", ""),
            "author": authors,
            "year": "—",
            "note": "公有领域全文",
            "url": link,
        })
    return rows


def p_openlib(q):
    data = json.loads(_get(f"https://openlibrary.org/search.json?q={urllib.parse.quote(q)}&limit=5"))
    rows = []
    for d in data.get("docs", [])[:5]:
        rows.append({
            "title": d.get("title", ""),
            "author": ", ".join(d.get("author_name", [])[:2]) or "作者不详",
            "year": d.get("first_publish_year", "—"),
            "note": "书目 / 馆藏位置，不含全文",
            "url": "https://openlibrary.org" + d.get("key", ""),
        })
    return rows


def p_archive(q):
    fl = "&".join(f"fl[]={x}" for x in ("identifier", "title", "creator", "year"))
    url = (f"https://archive.org/advancedsearch.php?q={urllib.parse.quote(q)}"
           f"&{fl}&rows=5&page=1&output=json")
    data = json.loads(_get(url))
    rows = []
    for d in data.get("response", {}).get("docs", [])[:5]:
        rows.append({
            "title": d.get("title", ""),
            "author": d.get("creator", "作者不详"),
            "year": d.get("year", "—"),
            "note": "扫描件，部分可借阅",
            "url": f"https://archive.org/details/{d.get('identifier','')}",
        })
    return rows


def p_ctext(q):
    return [{
        "title": q, "author": "—", "year": "—",
        "note": "中国哲学原典检索页（原文公版）",
        "url": f"https://ctext.org/searchbooks.pl?if=gb&searchu={urllib.parse.quote(q)}",
    }]


def p_perseus(q):
    return [{
        "title": q, "author": "—", "year": "—",
        "note": "希腊拉丁原典与英译（原文公版）",
        "url": f"https://www.perseus.tufts.edu/hopper/searchresults?q={urllib.parse.quote(q)}",
    }]


def p_library(q):
    qq = urllib.parse.quote(q)
    return [
        {"title": q, "author": "—", "year": "—", "note": "中国国家图书馆馆藏检索",
         "url": f"http://opac.nlc.cn/F?func=find-b&find_code=WRD&request={qq}"},
        {"title": q, "author": "—", "year": "—", "note": "WorldCat 全球馆藏",
         "url": f"https://search.worldcat.org/search?q={qq}"},
        {"title": q, "author": "—", "year": "—", "note": "豆瓣书目（看版次与译者评价）",
         "url": f"https://book.douban.com/subject_search?search_text={qq}"},
    ]


PROVIDERS = {
    "gutenberg": p_gutenberg,
    "openlib": p_openlib,
    "archive": p_archive,
    "ctext": p_ctext,
    "perseus": p_perseus,
    "library": p_library,
}


def load_custom():
    cfg = CONFIG / "providers.json"
    if not cfg.exists():
        return None
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except Exception:
        return None
    c = data.get("custom") or {}
    if c.get("enabled") and c.get("base"):
        return c
    return None


def run(provider: str, q: str):
    fn = PROVIDERS.get(provider)
    if not fn:
        out(f"× 没有这个 provider：{provider}")
        out("  可用：" + "、".join(PROVIDERS))
        return []
    try:
        return fn(q)
    except Exception as e:
        out(f"  （{provider} 连不上：{type(e).__name__}；断网时只能用 library 的检索页）")
        return []


def main():
    args = sys.argv[1:]
    if not args:
        out(__doc__)
        return
    provider = None
    if "--provider" in args:
        i = args.index("--provider")
        provider = args[i + 1]
        del args[i:i + 2]
    q = " ".join(args).strip()
    if not q:
        out("× 给一个书名或关键词")
        return

    todo = [provider] if provider else ["library", "openlib", "gutenberg"]
    any_rows = False
    for pv in todo:
        rows = run(pv, q)
        if rows:
            any_rows = True
            out(f"\n【{pv}】")
            for r in rows:
                out(f"  · {r['title']}  ／ {r['author']}  ／ {r['year']}")
                out(f"    {r['note']}")
                out(f"    {r['url']}")
    if not any_rows:
        out("\n没有查到。检查网络，或者直接用 --provider library 看馆藏检索页。")

    c = load_custom()
    if c:
        out(f"\n（自定义 provider 已启用：{c.get('label') or '未命名'} —— 由你自己的配置负责其合法性）")


if __name__ == "__main__":
    main()
