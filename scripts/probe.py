#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""书源体检：判断一本（或一批）书能不能进库，不能的话该怎么换。

用法：
    python scripts/probe.py "D:/书/某本书.pdf"
    python scripts/probe.py "D:/书/"            # 整个目录一起体检
    python scripts/probe.py "D:/书/" --json     # 机器可读

它回答三个问题：
1. 有没有文字层？（没有 → 扫描件，抽出来是空白，必须 OCR 或换源）
2. 文字层干不干净？（OCR 过的扫描件也有文字层，但字是错的）
3. 有没有书签目录？（决定能不能自动按章切分）

哪一项不合格，它会直接说要换什么，不用自己判断。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import out  # noqa: E402

SAMPLE = 40          # PDF 抽样页数
NO_TEXT = 30         # 平均字/页低于此值 = 没有文字层
BAD_ZI = 3.0         # 「笫」占「第/笫」的百分比，超过即 OCR 误认
BAD_FRAG = 4.5       # 每千汉字里的 1-2 字母碎片数，超过即西文被拆散
DOWNLOAD_HOST = re.compile(r"\.(?:sk|ru|to|is|st)\b", re.I)


def _stats(txt: str) -> dict:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", txt))
    di, zi = txt.count("第"), txt.count("笫")
    frag = len(re.findall(r"\b[a-zA-Z]{1,2}\b", txt))
    blank_num = len([l for l in txt.split("\n") if re.fullmatch(r"\s*\d{1,4}\s*", l)])
    return {
        "cjk": cjk,
        "zi_ratio": (zi / (di + zi) * 100) if (di + zi) else 0.0,
        "frag": (frag / cjk * 1000) if cjk else 0.0,
        "blank_num": blank_num,
    }


def _verdict(text_per_page: float, st: dict) -> tuple[str, str]:
    """返回 (结论, 建议)。"""
    if text_per_page < NO_TEXT:
        return "无文字层", "扫描件：换 EPUB 版，或先过 OCR。抽它只会得到空白"
    if st["zi_ratio"] > BAD_ZI or st["frag"] > BAD_FRAG:
        return "可用·OCR损坏", "能抽，但字有误认。引用前必须核纸书；关键句别直接引"
    return "可用", ""


def probe_pdf(path: Path) -> dict:
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    doc = fitz.open(path)
    try:
        n = doc.page_count
        st_page = max(0, n // 3)
        pages = list(range(st_page, min(st_page + SAMPLE, n))) or [0]
        txt = "".join(doc.load_page(i).get_text("text") for i in pages)
        toc = doc.get_toc() or []
        st = _stats(txt)
        per_page = st["cjk"] / max(len(pages), 1)
        verdict, advice = _verdict(per_page, st)
        return {
            "format": "PDF",
            "pages": n,
            "size_mb": round(path.stat().st_size / 1e6, 1),
            "chars_per_page": round(per_page),
            "bookmarks": len(toc),
            "zi_ratio": round(st["zi_ratio"], 1),
            "frag": round(st["frag"], 1),
            "verdict": verdict,
            "advice": advice,
        }
    finally:
        doc.close()


def probe_epub(path: Path) -> dict:
    zf = zipfile.ZipFile(path)
    names = [n for n in zf.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))]
    sample = names[:12]
    txt = ""
    for n in sample:
        raw = zf.read(n).decode("utf-8", errors="replace")
        txt += re.sub(r"<[^>]+>", " ", raw)
    zf.close()
    st = _stats(txt)
    per_ch = st["cjk"] / max(len(sample), 1)
    if per_ch < 200:
        verdict, advice = "疑似空壳", "正文文件里几乎没有字，换一本"
    elif st["zi_ratio"] > BAD_ZI:
        verdict, advice = "可用·OCR损坏", "EPUB 由扫描件转换而来，字有误认，引用前核纸书"
    else:
        verdict, advice = "可用·无页码", ""
    return {
        "format": "EPUB",
        "pages": len(names),
        "size_mb": round(path.stat().st_size / 1e6, 1),
        "chars_per_page": round(per_ch),
        "bookmarks": 0,
        "zi_ratio": round(st["zi_ratio"], 1),
        "frag": round(st["frag"], 1),
        "verdict": verdict,
        "advice": advice,
    }


def probe_one(path: Path) -> dict:
    size = path.stat().st_size
    short = DOWNLOAD_HOST.sub("", path.stem).strip(" _()（）")
    short = re.sub(r"\s*\([^()]*\)\s*$", "", short).strip() or path.stem
    if size == 0:
        return {"file": short, "format": path.suffix.lstrip(".").upper(), "pages": 0,
                "size_mb": 0, "chars_per_page": 0, "bookmarks": 0, "zi_ratio": 0,
                "frag": 0, "verdict": "空文件", "advice": "下载中断，删掉重下"}
    try:
        info = probe_pdf(path) if path.suffix.lower() == ".pdf" else probe_epub(path)
    except Exception as e:
        return {"file": short, "format": path.suffix.lstrip(".").upper(), "pages": 0,
                "size_mb": round(size / 1e6, 1), "chars_per_page": 0, "bookmarks": 0,
                "zi_ratio": 0, "frag": 0, "verdict": "打不开", "advice": f"{type(e).__name__}"}
    info["file"] = short
    return info


def main():
    ap = argparse.ArgumentParser(description="书源体检：能不能进库、不能该换什么")
    ap.add_argument("target", help="文件或目录")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    target = Path(args.target).expanduser()
    if not target.exists():
        raise SystemExit(f"× 路径不存在：{target}")
    exts = (".pdf", ".epub")
    files = [target] if target.is_file() else sorted(
        p for p in target.iterdir() if p.suffix.lower() in exts
    )
    if not files:
        raise SystemExit("× 这里没有 .pdf 或 .epub")

    rows = [probe_one(f) for f in files]
    if args.json:
        out(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    head = f"{'文件':<30} {'格式':<5} {'页/章':>6} {'体积':>7} {'字/页':>6} {'书签':>5} {'乱码':>6} {'结论':<12}"
    out(head)
    out("─" * 92)
    for r in rows:
        name = r["file"][:28]
        out(f"{name:<30} {r['format']:<5} {r['pages']:>6} {r['size_mb']:>6.1f}M "
            f"{r['chars_per_page']:>6} {r['bookmarks']:>5} {r['zi_ratio']:>5.1f}% {r['verdict']:<12}")

    out("")
    today = [r for r in rows if r["verdict"] != "可用"]
    ok = [r for r in rows if r["verdict"].startswith("可用")]
    out(f"── {len(rows)} 本：可用 {len(ok)}，有问题 {len(today)} ──")
    for r in today:
        if r["advice"]:
            out(f"  · {r['file'][:34]}：{r['advice']}")


if __name__ == "__main__":
    main()
