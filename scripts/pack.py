#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包分享版：把你的框架给别人，同时把不属于你的正文留在你自己这里。

用法：
    python scripts/pack.py                 # 输出到 share/
    python scripts/pack.py --dest D:/分享包

硬规则（没有开关，也不打算加）：
· 01-sources 里的章节，只有 pd_text 和 pd_edition 同时为 true 才保留正文；
· 其余章节只留书目与定位符，正文整段移除；
· 02-excerpts 每条正文截到 300 字（保守的适当引用范围，不是法定标准）；
· 03-judgments / 04-themes 是你的作品，原样带走。
"""
from __future__ import annotations

import re
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import KIND_DIRS, LIB, ROOT, iter_items, out, write_item  # noqa: E402

EXCERPT_LIMIT = 300
KEEP_DIRS = ["scripts", "config", "index"]
PLACEHOLDER = (
    "_（正文未随包分发。此条只保留书目与定位信息，"
    "请通过合法渠道取得本书后放入 library/01-sources/。）_\n"
)

# 来源痕迹与本地路径：一律不许进分享包。
# src_file 记的是原始文件名，常带下载站域名；绝对路径则暴露使用者机器上的目录结构。
SCRUB = [
    (re.compile(r"（\s*原始文件[^）]*）|\(\s*原始文件[^)]*\)"), "（来源信息不入包）"),
    (re.compile(r"[^\s,，()（）]{2,60}\.(?:sk|ru|to|is|st)\b[^\s,，()（）]*", re.I), ""),
    (re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"，,）)]+", re.I), "<本机>"),
    (re.compile(r"/Users/[^/\s\"，,）)]+"), "<本机>"),
    (re.compile(r"[A-Za-z]:[\\/]+[^\s\"，,）)]*WorkBuddy[^\s\"，,）)]*", re.I), "<skill根目录>"),
]


def scrub_text(t: str) -> str:
    for pat, rep in SCRUB:
        t = pat.sub(rep, t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"（\s*）|\(\s*\)", "", t)
    return t


def sanitize(meta: dict) -> dict:
    """来源文件名整条丢弃——它的唯一作用是指回原始文件，对收包的人没有意义。"""
    return {k: v for k, v in meta.items() if k != "src_file"}


def scrub_tree(dest: Path) -> int:
    n = 0
    for f in list(dest.rglob("*.md")) + list(dest.rglob("*.json")):
        try:
            t = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        t2 = scrub_text(t)
        if t2 != t:
            f.write_text(t2, encoding="utf-8")
            n += 1
    return n


def main():
    dest = ROOT / "share"
    if "--dest" in sys.argv:
        dest = Path(sys.argv[sys.argv.index("--dest") + 1]).expanduser()
    if dest.exists():
        if dest.resolve() in (ROOT.resolve(), ROOT.parent.resolve(), Path.home().resolve()):
            out(f"✗ 拒绝删除：{dest} 是库根目录或家目录。")
            sys.exit(1)
        nonempty = any(dest.iterdir())
        if nonempty and not (dest / "分享包说明.md").exists():
            out(f"✗ 拒绝删除：{dest} 非空，且不像上一次生成的分享包（缺 分享包说明.md）。")
            out("  换一个输出目录，或手工确认后自行清空。")
            sys.exit(1)
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    for d in KEEP_DIRS:
        src = ROOT / d
        if src.exists():
            shutil.copytree(src, dest / d)
            for junk in (dest / d).rglob("__pycache__"):
                shutil.rmtree(junk, ignore_errors=True)
    for doc in ("SKILL.md", "README.md", "使用说明.md", "地图.md", "排序规则.md",
                "选书标准.md", "LICENSE", "LICENSE-CONTENT", "地图-罗素序.md"):
        if (ROOT / doc).exists():
            shutil.copy2(ROOT / doc, dest / doc)

    kept, stripped, truncated = 0, 0, 0
    for kind, dirname in KIND_DIRS.items():
        (dest / "library" / dirname).mkdir(parents=True, exist_ok=True)

    for path, meta, body in iter_items():
        rel = path.relative_to(ROOT)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        kind = meta.get("type")

        if kind == "source":
            shareable = meta.get("pd_text") is True and meta.get("pd_edition") is True
            if shareable:
                write_item(target, sanitize(meta), body)
                kept += 1
            else:
                write_item(target, sanitize({**meta, "status": "bibliography-only"}), PLACEHOLDER)
                stripped += 1
        elif kind == "excerpt":
            if len(body) > EXCERPT_LIMIT:
                body = body[:EXCERPT_LIMIT].rstrip() + "\n\n_（摘录过长，分享版已截断。）_\n"
                truncated += 1
            write_item(target, sanitize(meta), body)
        else:
            write_item(target, sanitize(meta), body)

    notice = f"""# 分享包说明

这个包里有什么、没什么，一句话：**框架公开，全文留给你自己。**

## 分三层

| 层 | 内容 | 是否随包分发 |
|---|---|---|
| 框架 | SKILL.md、脚本、目录约定、索引结构 | 是 |
| 书目 | 作者、著作、版次、译者、定位符、知识点出处 | 是（这是本包的主要价值） |
| 你写的判断 | library/03-judgments、04-themes | 是（你的著作权） |
| 正文全文 | library/01-sources 里非公有领域的章节 | **否** |

## 本次打包结果

- 保留全文：{kept} 篇（原文与版次都已确认属公有领域）
- 仅留书目、正文移除：{stripped} 篇
- 摘录被截断：{truncated} 条

## 怎么把缺的书补回来

拿到本包的人不欠你什么，也不用去找盗版。包里给的是坐标，取得是你的动作：

```bash
python scripts/wanted.py            # 看你缺哪些书
python scripts/resolve.py "书名"     # 查公版全文或馆藏入口
```

`resolve.py` 只内置公有领域全文源（Gutenberg / Perseus / ctext / archive.org）
与书目馆藏入口（Open Library / 国图 / WorldCat / 豆瓣）。没有别的。

## 一条必须说清的话

一本书是公有领域，不等于你手上这一版是公有领域。
译本、校注、编选都各自有著作权。脚本要求 `pd_text` 与 `pd_edition` **两个都为 true** 才保留正文，
就是为了挡住「原文公版所以译本也能传」这个最常见的错误。

拿不准就填 false。保守不会错，填错会出事。
"""
    (dest / "分享包说明.md").write_text(notice, encoding="utf-8")

    total = sum(1 for _ in dest.rglob("*"))
    out(f"✓ 分享包已生成：{dest}")
    scrubbed = scrub_tree(dest)
    out(f"  保留全文 {kept} 篇｜仅留书目 {stripped} 篇｜摘录截断 {truncated} 条｜共 {total} 个路径")
    out(f"  清除来源痕迹与本地路径：{scrubbed} 个文件")
    out("  这个目录可以直接压成 zip 给人，不需要再手工删任何东西。")


if __name__ == "__main__":
    main()
