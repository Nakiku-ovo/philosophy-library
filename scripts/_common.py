# -*- coding: utf-8 -*-
"""公共工具：条目读写、目录定位、输出编码。

所有条目都是一份 md：YAML 头（只用单层 key: value / 行内列表）+ 正文。
不用 PyYAML，避免多一个依赖；因此字段必须保持扁平，不要写嵌套。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "library"
INDEX = ROOT / "index"
CONFIG = ROOT / "config"

KIND_DIRS = {
    "source": "01-sources",
    "excerpt": "02-excerpts",
    "judgment": "03-judgments",
    "theme": "04-themes",
}

# 必填字段缺了任何一个，scan.py 都会把它列进待补清单
REQUIRED = ["author", "work", "locator", "edition"]


def out(*args):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(*args)


def _scalar(raw: str):
    v = raw.strip()
    if v == "":
        return ""
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def read_item(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta = {}
    for line in parts[1].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        meta[key.strip()] = _scalar(val)
    return meta, parts[2].lstrip("\n")


def fmt_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return "[" + ", ".join(str(x) for x in v) + "]"
    return str(v)


def write_item(path: Path, meta: dict, body: str):
    lines = ["---"] + [f"{k}: {fmt_value(v)}" for k, v in meta.items()] + ["---"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n\n" + body, encoding="utf-8")


def iter_items(kinds=None):
    kinds = kinds or list(KIND_DIRS)
    for kind in kinds:
        base = LIB / KIND_DIRS[kind]
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.md")):
            meta, body = read_item(p)
            meta.setdefault("type", kind)
            yield p, meta, body


def slug(text: str, limit: int = 40) -> str:
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", str(text)).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:limit] or "未命名"


def page_at(body: str, pos: int):
    """取 pos 之前最近的页码标记；EPUB 没有页码则返回 None。"""
    page = None
    for m in re.finditer(r"<!--\s*p\.(\d+)\s*-->", body[:pos]):
        page = m.group(1)
    return page


def para_at(body: str, pos: int) -> int:
    pre = body[:pos]
    return len([b for b in re.split(r"\n\s*\n", pre) if b.strip()]) or 1


def cite(meta: dict, body: str, pos: int) -> str:
    """生成可核对的引用串：〔作者·《著作》·定位符〕"""
    page = page_at(body, pos)
    locator = str(meta.get("locator") or "").strip()
    if page:
        where = f"p.{page}"
        if locator:
            where = f"{locator}，{where}"
    else:
        where = f"{locator}，¶{para_at(body, pos)}" if locator else f"¶{para_at(body, pos)}"
    author = meta.get("author") or "作者待补"
    work = meta.get("work") or "著作待补"
    return f"〔{author}·《{work}》·{where}〕"
