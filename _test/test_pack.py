# -*- coding: utf-8 -*-
"""分享包的安全属性测试。

只测一件事：**不该发出去的东西，有没有可能被发出去。**

跑法：
    python _test/test_pack.py          # 或 python -m unittest discover _test

不用第三方测试框架，标准库 unittest 即可，保持这个项目零依赖。

为什么这几条要写成测试而不是靠人检查：pack.py 是唯一一条「错了就直接把
别人的正文发到网上」的路径。人看一眼输出「保留全文 0 篇」会以为没事，
但那个数字本身也可能是错的——审计已经证明过一次。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

LONG_BODY = "这是一段必须被拦住的正文。" * 60          # 约 780 字
PD_CONFLICT = """---
id: t-conflict
type: source
map: W-1-01
title: 译本在保护期
author: 某甲
work: 某书
locator: 第一卷
edition: 某社 2018
pd_text: true
pd_edition: false
src_file: 某书 (book-site.sk, mirror.ru).epub
---
""" + LONG_BODY + "\n"

PD_CLEAR = """---
id: t-clear
type: source
map: W-1-02
title: 双闸门都开
author: 某乙
work: 另一书
locator: 第二卷
edition: 某社 1900
pd_text: true
pd_edition: true
---
""" + LONG_BODY + "\n"

EXCERPT = """---
id: t-excerpt
type: excerpt
title: 一条过长的摘录
author: 某丙
work: 第三书
locator: 第三卷
edition: 某社 2000
---
""" + ("摘录内容。" * 200) + "\n"


class PackSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="phil_pack_test_"))
        shutil.copytree(SCRIPTS, self.tmp / "scripts")
        for d in ("01-sources", "02-excerpts", "03-judgments", "04-themes"):
            (self.tmp / "library" / d).mkdir(parents=True)
        (self.tmp / "config").mkdir()
        (self.tmp / "index").mkdir()
        (self.tmp / "library" / "01-sources" / "conflict.md").write_text(PD_CONFLICT, encoding="utf-8")
        (self.tmp / "library" / "01-sources" / "clear.md").write_text(PD_CLEAR, encoding="utf-8")
        (self.tmp / "library" / "02-excerpts" / "long.md").write_text(EXCERPT, encoding="utf-8")
        self.out = self.tmp / "share"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_pack(self, dest=None):
        return subprocess.run(
            [sys.executable, str(self.tmp / "scripts" / "pack.py"), "--dest", str(dest or self.out)],
            capture_output=True, text=True, encoding="utf-8", cwd=str(self.tmp))

    # ── 属性一：原文公版、译本不公版时，正文必须被剥掉 ──────────────
    def test_conflicting_license_strips_body(self):
        r = self.run_pack()
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.out / "library" / "01-sources" / "conflict.md").read_text(encoding="utf-8")
        self.assertNotIn("必须被拦住的正文", text,
                         "pd_text=true 但 pd_edition=false 时正文仍进了分享包——这是最严重的一种泄漏")
        self.assertIn("正文未随包分发", text)

    # ── 属性二：两个闸门都开时才保留正文，别误伤公版书 ──────────────
    def test_both_clear_keeps_body(self):
        self.run_pack()
        text = (self.out / "library" / "01-sources" / "clear.md").read_text(encoding="utf-8")
        self.assertIn("必须被拦住的正文", text, "两个闸门都开却被剥了，说明规则写反了")

    # ── 属性三：分享包里不许出现来源痕迹 ────────────────────────────
    def test_no_source_traces(self):
        """只查数据文件，不查脚本源码——extract.py 里 src_file 是字段名，不是泄漏。"""
        self.run_pack()
        targets = list((self.out / "library").rglob("*.md")) + list((self.out / "index").rglob("*.json"))
        self.assertTrue(targets, "没有可检查的数据文件，测试本身有问题")
        for f in targets:
            t = f.read_text(encoding="utf-8", errors="ignore")
            for m in re.finditer(r"[\w.-]+\.(?:sk|ru|to|is|st)\b", t, re.I):
                self.fail(f"{f.relative_to(self.out)} 残留下载站痕迹：{m.group(0)}")
            self.assertNotIn(str(Path.home()), t, f"{f.relative_to(self.out)} 残留本机路径")
            self.assertNotIn("src_file", t, f"{f.relative_to(self.out)} 残留 src_file 字段")

    # ── 属性四：摘录超长要截断，不能把整章当摘录发出去 ──────────────
    def test_excerpt_truncated(self):
        self.run_pack()
        text = (self.out / "library" / "02-excerpts" / "long.md").read_text(encoding="utf-8")
        self.assertIn("摘录过长", text)
        self.assertLess(len(text), 1200, "截断没生效")

    # ── 属性五：不许清空一个不像分享包的目录 ────────────────────────
    def test_refuses_to_wipe_foreign_dir(self):
        foreign = self.tmp / "someone_else"
        foreign.mkdir()
        (foreign / "important.txt").write_text("别删我", encoding="utf-8")
        r = self.run_pack(dest=foreign)
        self.assertNotEqual(r.returncode, 0, "应当拒绝，却返回了成功")
        self.assertTrue((foreign / "important.txt").exists(), "护栏失效，陌生目录被清空了")

    # ── 属性六：覆盖自己生成的分享包应当被允许，不能一刀切拒绝 ──────
    def test_allows_overwriting_own_output(self):
        self.assertEqual(self.run_pack().returncode, 0)
        r = self.run_pack()          # 第二次，目标已存在且带标记文件
        self.assertEqual(r.returncode, 0, f"重跑时被自己的护栏挡住了：{r.stdout}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
