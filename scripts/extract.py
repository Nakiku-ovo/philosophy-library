#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 PDF / EPUB 拆成按章切分的 md，写入 library/01-sources/。

用法：
    python scripts/extract.py "D:/书/某本书.pdf"
    python scripts/extract.py "D:/书/" --author 海德格尔 --work 存在与时间 --edition "陈嘉映译，商务版"

设计要点（不要改）：
1. PDF 的页码标记 <!-- p.N --> 写的是**纸书页**，不是 PDF 物理页。
   两者常有几十页偏移（封面、序、目录都计入物理页），差一页就没法引用。
   页眉页脚取不到页码时退回物理页，并在 frontmatter 记 page_kind: pdf。
2. EPUB 没有页码，只记章节 + 段号，不假装有页码；
3. 扫描版 / 影印版没有文字层，直接报错退出，绝不产出空文件；
4. 章节层级看标题文字（第X章、第X篇、第X节），不看 PDF 目录的层级数字——
   同一本书里「章」在不同部分可能挂在不同层，按层级数字取必然取错；
5. pd_text / pd_edition 一律留 TODO，逼使用者显式判断能不能分享。
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import KIND_DIRS, LIB, out, slug, write_item  # noqa: E402

DEST = LIB / KIND_DIRS["source"]
CHUNK = 26000        # 单个文件的目标字数上限，超了在页边界处拆开
NO_TEXT = 30         # 平均字/页低于此值 = 没有文字层

CN = "一二三四五六七八九十百零〇两"
RE_CHAPTER = re.compile(rf"^第[{CN}\d]+章")
RE_SECTION = re.compile(rf"^第[{CN}\d]+节")
RE_PART = re.compile(rf"^第[{CN}\d]+[篇部]")
RE_FRONT = re.compile(r"(前言|序言|绪论|导论|引言|译序|后记|跋|附录|写在|再版)")
RE_SKIP = re.compile(r"^(封面|封底|书名页|版权|编委会|题词|目录|扉页|插页|彩插|出版说明)\s*$")
RE_DLHOST = re.compile(r"[（(][^（()）]*(?:\.sk|\.ru|\.to|\.is|\.st)\b[^（()）]*[）)]", re.I)
RE_PAGE = re.compile(r"<!--\s*p\.(\d+)\s*-->")


def base_meta(title, author, work, edition, locator, pages, lang, src):
    return {
        "id": f"{slug(work, 16)}-{slug(title, 20)}",
        "type": "source",
        "title": title or "章节待补",
        "author": author or "TODO",
        "work": work or "TODO",
        "work_original": "TODO",
        "year": "TODO",
        "edition": edition or "TODO",
        "translator": "TODO",
        "locator": locator or "TODO",
        "pages": pages or "",
        "lang": lang,
        "page_kind": "book",
        "ocr": "clean",
        "origin_of": [],
        "tags": [],
        "pd_text": "TODO",
        "pd_edition": "TODO",
        "status": "todo",
        "src_file": src,
    }


def parse_name(stem: str):
    """从文件名拆出（书名, 作者, 译者）。下载站的括号标记一律剥掉。

    文件名常见三种样子：
        存在与时间 (马丁·海德格尔) (下载站域名, 备用域名)
        心灵、自我与社会(译文经典)【文字版】 (乔治·米德)
        尼各马可伦理学 (〔古希腊〕亚里士多德著；廖申白译注)
    作者取**最后一个**像人名的括号，书名是它前面那段。
    """
    s = RE_DLHOST.sub("", stem)
    s = re.sub(r"【[^】]*】", "", s).strip(" _-")
    work, people, translator = s, "", ""
    groups = list(re.finditer(r"[（(]([^（()）]*)[）)]", s))
    for g in reversed(groups):
        v = g.group(1).strip()
        if not v or len(v) > 25 or re.fullmatch(r"[A-Za-z\s.,'’]+", v):
            continue
        work, people = s[:g.start()].strip(" _-"), v
        break
    work = re.sub(r"[（(][^（()）]*[）)]\s*$", "", work).strip(" _-")
    m = re.search(r"[；;]\s*([^；;]{2,12}?)(?:译注|译)$", people)
    if m:
        translator = m.group(1).strip()
        people = people[:m.start()].strip()
    people = re.sub(r"[〔\[（(][^〕\]）)]*[〕\]）)]", "", people).strip()
    people = re.sub(r"(等著|著|等|编|主编|译注|译)$", "", people).strip()
    people = re.sub(r"\s*etc\.?$", "", people, flags=re.I).strip()
    return work or "TODO", people or "TODO", translator


def clean_text(t: str) -> str:
    t = t.replace("笫", "第")          # OCR 把「第」认成竹字头的「笫」
    t = re.sub(r"[ \t\u00a0]+", " ", t)
    return t


class HtmlText(HTMLParser):
    """把 xhtml 转成带 # 标题标记的纯文本。"""

    BLOCK = {"p", "div", "br", "li", "tr", "blockquote", "section", "article"}
    SKIP = {"script", "style", "head", "nav"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.buf, self.skip, self.head = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif re.fullmatch(r"h[1-6]", tag or ""):
            self.head = int(tag[1])
            self.buf.append("\n\n")
        elif tag in self.BLOCK:
            self.buf.append("\n\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif re.fullmatch(r"h[1-6]", tag or ""):
            self.head = 0
            self.buf.append("\n\n")

    def handle_data(self, data):
        if self.skip:
            return
        if self.head and data.strip():
            self.buf.append(f"\n\n{'#' * self.head} {data.strip()}\n\n")
        else:
            self.buf.append(data)

    def text(self):
        raw = "".join(self.buf)
        raw = re.sub(r"[ \t\u00a0]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def html_to_text(data: bytes) -> str:
    p = HtmlText()
    p.feed(data.decode("utf-8", errors="replace"))
    p.close()
    return p.text()


def split_big(text: str, title: str):
    """章节过长时按小标题切开，返回 [(子标题, 文本)]。"""
    if len(text) <= CHUNK:
        return [(title, text)]
    parts = re.split(r"\n(?=#{1,6}\s)", text)
    chunks, cur = [], ""
    for seg in parts:
        if cur and len(cur) + len(seg) > CHUNK:
            chunks.append(cur)
            cur = seg
        else:
            cur += "\n" + seg if cur else seg
    if cur.strip():
        chunks.append(cur)
    out_list = []
    for i, c in enumerate(chunks, 1):
        m = re.search(r"#{1,6}\s+(.+)", c)
        sub = m.group(1).strip() if m else f"{title}·{i}"
        out_list.append((sub, c))
    return out_list


def do_epub(path: Path, author, work, edition, lang):
    zf = zipfile.ZipFile(path)
    try:
        container = ET.fromstring(zf.read("META-INF/container.xml"))
    except KeyError:
        raise SystemExit("× 不是标准 EPUB：缺 META-INF/container.xml")
    ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
    rootfile = container.find(".//c:rootfile", ns)
    if rootfile is None:
        raise SystemExit("× EPUB 结构异常：找不到 rootfile")
    opf_path = rootfile.get("full-path")
    opf = ET.fromstring(zf.read(opf_path))
    base = str(Path(opf_path).parent)

    manifest = {}
    for item in opf.iter("{http://www.idpf.org/2007/opf}item"):
        manifest[item.get("id")] = item.get("href")
    spine = [it.get("idref") for it in opf.iter("{http://www.idpf.org/2007/opf}itemref")]
    files = [manifest[i] for i in spine
             if i in manifest and manifest[i].lower().endswith((".xhtml", ".html", ".htm"))]
    if not files:
        raise SystemExit("× 这本书的 EPUB 找不到正文 xhtml")

    written = []
    for idx, href in enumerate(files, 1):
        full = f"{base}/{href}" if base and base != "." else href
        try:
            text = html_to_text(zf.read(full))
        except KeyError:
            continue
        if len(text) < 200:
            continue
        head = re.search(r"^#{1,6}\s*(.+)$", text, re.M)
        title = clean_text(head.group(1).strip()) if head else f"第{idx:02d}节"
        for sub_title, body in split_big(text, title):
            meta = base_meta(sub_title, author, work, edition, title, "", lang, path.name)
            meta["id"] = f"{slug(work, 16)}-{idx:02d}-{slug(sub_title, 20)}"
            meta["page_kind"] = "section"
            dest = DEST / (slug(f"{author or 'TODO'}_{work or 'TODO'}_{idx:02d}_{sub_title}", 90) + ".md")
            write_item(dest, meta, body)
            written.append(dest)
    return written


def detect_offset(doc) -> int | None:
    """从页眉页脚的孤立数字推断「PDF 物理页 → 纸书页」的固定偏移。

    取页面上方 4 行、下方 3 行里的纯数字行，逐页算差，多数投票。
    一致性不到 60% 就认为这本书没有可靠页眉页码，返回 None。
    """
    n = doc.page_count
    start = max(0, n // 5)
    step = max(1, (n - start) // 80)
    pairs = []
    for i in range(start, n, step):
        lines = [l.strip() for l in doc.load_page(i).get_text("text").split("\n")]
        for l in lines[:4] + lines[-3:]:
            if re.fullmatch(r"\d{1,4}", l):
                pairs.append((i + 1, int(l)))
    if len(pairs) < 8:
        return None
    off, cnt = Counter(p - b for p, b in pairs).most_common(1)[0]
    return off if cnt / len(pairs) >= 0.6 else None


def clean_page(txt: str, expected: int | None = None) -> str:
    """去掉页眉页脚残留的孤立页码、目录页的点线。

    expected 是本页应有的纸书页；等于它的孤立数字一律视为页码清除，
    不管它落在第几行（有些书的页眉被排到章标题之后）。
    """
    lines = txt.split("\n")
    keep = []
    for i, l in enumerate(lines):
        s = l.strip()
        if re.fullmatch(r"\d{1,4}", s):
            at_edge = i < 4 or i >= len(lines) - 3
            if at_edge or (expected is not None and int(s) == expected):
                continue
        keep.append(l)
    t = "\n".join(keep)
    t = re.sub(r"[.．·]{3,}", "……", t)
    t = clean_text(t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def build_spans(toc, total):
    """按标题文字识别章节粒度，返回 [(标题, 起始物理页, 结束物理页)]。"""
    items = []
    for lvl, title, page in (toc or []):
        t = clean_text(str(title)).strip()
        if not t or RE_SKIP.match(t):
            continue
        items.append({"title": t, "page": max(1, int(page))})
    items.sort(key=lambda x: x["page"])          # 目录常乱序，先按页码归位

    n_ch = len([1 for it in items if RE_CHAPTER.match(it["title"])])
    n_part = len([1 for it in items if RE_PART.match(it["title"])])
    n_sec = len([1 for it in items if RE_SECTION.match(it["title"])])

    if 6 <= n_ch <= 60:
        pick = RE_CHAPTER
    elif n_part >= 3:
        pick = RE_PART
    elif n_sec >= 6:
        pick = RE_SECTION
    elif n_ch:
        pick = RE_CHAPTER
    elif items:
        pick = None
    else:
        return []

    if pick is None:
        keep = items
    else:
        keep = [it for it in items if pick.match(it["title"]) or RE_FRONT.search(it["title"])]

    seen, uniq = set(), []
    for it in keep:
        key = (it["page"], it["title"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    spans = []
    for i, it in enumerate(uniq):
        nxt = uniq[i + 1]["page"] if i + 1 < len(uniq) else total + 1
        if nxt <= it["page"]:
            continue                             # 与下一条同页起头，让给下一条
        spans.append((it["title"], it["page"], min(nxt - 1, total)))
    return spans


def pack_pages(pages, chunk=CHUNK):
    """把 [(纸书页, 文本)] 按字数打包，超出 chunk 就在页边界断开。"""
    groups, cur, size = [], [], 0
    for pg, txt in pages:
        if cur and size + len(txt) > chunk:
            groups.append(cur)
            cur, size = [], 0
        cur.append((pg, txt))
        size += len(txt)
    if cur:
        groups.append(cur)
    return groups or [[]]


def do_pdf(path: Path, author, work, edition, lang):
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            raise SystemExit(
                "× 缺 PDF 抽取库。先运行：\n    python -m pip install pymupdf\n"
                "  （EPUB 不需要这个库，只有 PDF 需要）"
            )

    doc = fitz.open(path)
    total = doc.page_count
    texts = [doc.load_page(i).get_text("text") for i in range(total)]
    chars = sum(len(t.strip()) for t in texts)
    if chars / max(total, 1) < NO_TEXT:
        raise SystemExit(
            f"× 这本 PDF 没有文字层（{total} 页、平均每页 {chars // max(total, 1)} 字）——\n"
            "  是扫描件或影印版，需要先做 OCR。本脚本不会假装抽出内容。\n"
            "  先跑 python scripts/probe.py 这本书，看它建议换什么。"
        )

    offset = detect_offset(doc)
    page_kind = "book" if offset is not None else "pdf"
    shift = offset or 0

    bad = sum(t.count("笫") for t in texts)
    ocr = "damaged" if bad > 3 else "clean"

    spans = build_spans(doc.get_toc() or [], total)
    if not spans:
        step = 20
        spans = [(f"p.{s}-{min(s + step - 1, total)}（无目录，按页切）", s, min(s + step - 1, total))
                 for s in range(1, total + 1, step)]

    written = []
    for title, start, end in spans:
        pages = [(pno - shift, clean_page(texts[pno - 1], pno - shift)) for pno in range(start, end + 1)]
        pages = [(pg, txt) for pg, txt in pages if txt]
        if sum(len(t) for _, t in pages) < 80:
            continue
        groups = pack_pages(pages)
        for gi, grp in enumerate(groups, 1):
            if len(groups) == 1:
                label = title
            else:
                seq = CN[gi - 1] if 0 < gi <= 10 else str(gi)
                label = f"{title}（{seq}）"
            body = "\n\n".join(f"<!-- p.{pg} -->\n{txt}" for pg, txt in grp)
            lo, hi = grp[0][0], grp[-1][0]
            phys = f"（PDF {start}-{end}）" if page_kind == "book" else ""
            meta = base_meta(label, author, work, edition, title,
                             f"p.{lo}-{hi}{phys}", lang, path.name)
            meta["page_kind"] = page_kind
            meta["ocr"] = ocr
            meta["id"] = f"{slug(work, 16)}-{len(written) + 1:02d}-{slug(label, 20)}"
            dest = DEST / (slug(f"{author or 'TODO'}_{work or 'TODO'}_{len(written) + 1:02d}_{label}", 90) + ".md")
            write_item(dest, meta, body)
            written.append(dest)
    return written


def main():
    ap = argparse.ArgumentParser(description="PDF/EPUB → 按章切分的素材 md")
    ap.add_argument("target", help="文件或目录")
    ap.add_argument("--author", default="")
    ap.add_argument("--work", default="")
    ap.add_argument("--edition", default="")
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--link-judgments", nargs="*", default=[],
                    help="给每条素材挂上既有的判断条目 id，可多个")
    args = ap.parse_args()

    target = Path(args.target).expanduser()
    if not target.exists():
        raise SystemExit(f"× 路径不存在：{target}")
    files = [target] if target.is_file() else sorted(
        [p for p in target.iterdir() if p.suffix.lower() in (".pdf", ".epub")]
    )
    if not files:
        raise SystemExit("× 这个目录里没有 .pdf 或 .epub")

    DEST.mkdir(parents=True, exist_ok=True)
    all_written = []
    for f in files:
        out(f"\n▶ {f.name}")
        author, work, edition = args.author, args.work, args.edition
        if not (author and work):
            g_work, g_author, g_tr = parse_name(f.stem)
            author = author or g_author
            work = work or g_work
            if g_tr and not edition:
                edition = f"{g_tr}译"
            out(f"  · 书名={work}  作者={author}" + (f"  译者={g_tr}" if g_tr else "") + "   ← 从文件名推断，不对就加 --work/--author")
        try:
            if f.suffix.lower() == ".epub":
                got = do_epub(f, author, work, edition, args.lang)
            else:
                got = do_pdf(f, author, work, edition, args.lang)
        except SystemExit:
            raise
        except Exception as e:
            out(f"  × 失败：{type(e).__name__}: {e}")
            continue
        out(f"  ✓ 切出 {len(got)} 个章节文件")
        all_written += got

    out(f"\n共写入 {len(all_written)} 个文件 → {DEST}")
    out("下一步：python scripts/scan.py  ← 看哪些元信息还没补")


if __name__ == "__main__":
    main()
