# -*- coding: utf-8 -*-
"""端到端自测：造一本 EPUB + 一本 PDF + 一本扫描件，跑通全部脚本。

用法：python _test/selftest.py
样本文件放在 _test/samples/，清理时只动那个目录。
"""
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
T = Path(__file__).resolve().parent / "samples"
PY = sys.executable


def run(*args, expect_ok=True):
    r = subprocess.run([PY, *args], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    tag = "OK " if (r.returncode == 0) == expect_ok else "FAIL"
    print(f"[{tag}] {' '.join(str(a) for a in args[:2])} rc={r.returncode}")
    body = (r.stdout or "") + (r.stderr or "")
    for ln in body.splitlines()[:16]:
        print("     " + ln)
    if tag == "FAIL":
        print("     --- full ---")
        print(body)
    return r


def make_epub(path: Path):
    chapters = [
        ("ch1.xhtml", "第一沉思", "有几个念头在我心里盘桓多年。第一件事是，我自幼年起就把许多错误的见解当作真理接受下来。"),
        ("ch2.xhtml", "第二沉思", "昨天我陷入了极深的怀疑，仿佛一切都不存在。但我立刻注意到：我在怀疑这件事本身，说明我在。我思故我在。"),
        ("ch3.xhtml", "第三沉思", "我心中的观念必有原因。一个无限的观念不可能来自我这个有限的东西。"),
    ]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
 <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>""")
        items = "".join(f'<item id="c{i}" href="{h}" media-type="application/xhtml+xml"/>' for i, (h, _a, _b) in enumerate(chapters))
        refs = "".join(f'<itemref idref="c{i}"/>' for i, _ in enumerate(chapters))
        z.writestr("OEBPS/content.opf", f"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="i">
 <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>测试沉思</dc:title></metadata>
 <manifest>{items}</manifest><spine>{refs}</spine>
</package>""")
        for h, title, sentence in chapters:
            paras = "".join(f"<p>{sentence}这是第{i}段补充文字，用于凑长度并越过 200 字门槛。</p>" for i in range(6))
            z.writestr(f"OEBPS/{h}",
                       f'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
                       f'<body><h2>{title}</h2>{paras}</body></html>')


def make_pdf(path: Path, scanned=False):
    import pymupdf
    doc = pymupdf.open()
    for i in range(1, 7):
        page = doc.new_page()
        if not scanned:
            page.insert_text((72, 100), f"Chapter {i}", fontsize=16)
            for k in range(8):
                page.insert_text((72, 130 + k * 18),
                                 f"This is line {k + 1} of page {i} about the idea of substance.",
                                 fontsize=10)
        else:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200))
            pix.clear_with(200)
            page.insert_image(page.rect, pixmap=pix)
    doc.set_toc([[1, "第一章 论实体", 1], [1, "第二章 论心灵", 4]])
    doc.save(str(path))


def main():
    T.mkdir(exist_ok=True)
    for f in T.iterdir():
        if f.is_file():
            f.unlink()
        else:
            subprocess.run(["rm", "-rf", str(f)], check=False)
    src = ROOT / "library/01-sources"
    if src.exists():
        for f in src.glob("*.md"):
            f.unlink()

    epub = T / "笛卡尔_第一哲学沉思集_测试.epub"
    pdf = T / "笛卡尔_第一哲学沉思集_测试.pdf"
    scan = T / "某某_影印本_测试.pdf"
    make_epub(epub)
    make_pdf(pdf, scanned=False)
    make_pdf(scan, scanned=True)
    print(f"造好样本：{epub.name} / {pdf.name} / {scan.name}\n")

    print("=== 1. EPUB 抽取 ===")
    run("scripts/extract.py", str(epub), "--author", "笛卡尔", "--work", "第一哲学沉思集",
        "--edition", "测试译本，测试社，2000")

    print("\n=== 2. PDF 抽取（有目录，应带页码标记）===")
    run("scripts/extract.py", str(pdf), "--author", "笛卡尔", "--work", "第一哲学沉思集",
        "--edition", "测试译本，测试社，2000")

    print("\n=== 3. 扫描件必须拒绝 ===")
    r = run("scripts/extract.py", str(scan), "--author", "某", "--work", "影印本", expect_ok=False)
    assert "没有文字层" in (r.stdout + r.stderr), "扫描件没被拦住！"

    print("\n=== 4. 人工补一条判断 + 一条摘录 ===")
    sys.path.insert(0, str(ROOT / "scripts"))
    from _common import write_item
    write_item(ROOT / "library/03-judgments/我思故我在是不是循环.md", {
        "id": "judge-cogito-01", "type": "judgment", "title": "我思故我在是不是循环论证",
        "author": "本人", "work": "痛苦的两面", "locator": "手稿", "edition": "未刊",
        "origin_of": ["我思故我在"], "tags": ["怀疑", "论证结构"], "status": "ok",
    }, "如果「我」已经在「我思」里了，那结论就没有新增什么。\n可疑的不是这一步，是它被当成了一切知识的起点。\n")
    write_item(ROOT / "library/02-excerpts/论实体的摘录.md", {
        "id": "exc-substance-01", "type": "excerpt", "title": "实体的观念从哪来",
        "author": "笛卡尔", "work": "第一哲学沉思集", "locator": "第三沉思",
        "edition": "测试译本，测试社，2000",
        "origin_of": ["实体观念"], "tags": ["观念来源"], "status": "ok",
    }, "任何观念都要有原因，而无限的观念不能来自有限的我。\n")

    print("\n=== 5. 建索引 ===")
    run("scripts/build_index.py")

    print("\n=== 6. 扫描缺口 ===")
    run("scripts/scan.py")

    print("\n=== 7. 检索 ===")
    run("scripts/query.py", "怀疑")

    print("\n=== 8. 出处追溯 ===")
    run("scripts/query.py", "--trace", "我思故我在")

    print("\n=== 9. 缺口清单（自己写的书不该算缺口）===")
    run("scripts/wanted.py")

    print("\n=== 10. 打包分享（必须剥掉非公版正文）===")
    run("scripts/pack.py", "--dest", str(T / "share"))
    share_src = list((T / "share/library/01-sources").glob("*.md"))
    leaked = [p for p in share_src
              if "这是第" in p.read_text(encoding="utf-8") or "This is line" in p.read_text(encoding="utf-8")]
    print(f"     分享包里 source 文件 {len(share_src)} 个，泄漏正文 {len(leaked)} 个")
    print("     OK: 正文一条都没漏" if not leaked else f"     FAIL: 正文泄漏！{leaked[:3]}")

    print("\n=== 11. 公版判定必须放行 ===")
    pd_file = sorted(src.glob("*.md"))[0]
    meta, body = None, None
    from _common import read_item
    meta, body = read_item(pd_file)
    meta["pd_text"], meta["pd_edition"] = True, True
    write_item(pd_file, meta, body)
    run("scripts/pack.py", "--dest", str(T / "share"))
    kept = [p for p in (T / "share/library/01-sources").glob("*.md")
            if "这是第" in p.read_text(encoding="utf-8") or "This is line" in p.read_text(encoding="utf-8")]
    print(f"     判定为公版的 {pd_file.name} 应带正文：{'OK' if len(kept) == 1 else 'FAIL（未保留）'}")

    print("\n=== 12. 引用格式抽查 ===")
    r = run("scripts/query.py", "我思", "--json")
    ok = ("〔" in r.stdout) and ("¶" in r.stdout or "p." in r.stdout)
    print(f"     带作者·著作·定位符：{'OK' if ok else 'FAIL'}")

    print("\n全部测试结束。")


if __name__ == "__main__":
    main()
