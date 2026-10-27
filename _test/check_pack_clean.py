# -*- coding: utf-8 -*-
"""检查分享包是否真的干净——CI 和本地都用这一个。

用法：
    python _test/check_pack_clean.py

退出码 0 = 干净；1 = 有问题（会打印具体是哪几个文件）。

单独成文件而不是写进 workflow，是因为 YAML 的 `run: |` 会把缩进带进
Python 源码，heredoc 里的代码必然 IndentationError。也方便本地随时跑。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY_LIMIT = 400


def main() -> int:
    dest = Path(tempfile.mkdtemp(prefix="phil_ci_")) / "share"
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "pack.py"), "--dest", str(dest)],
        capture_output=True, text=True)
    if r.returncode != 0:
        print("打包失败：", r.stdout, r.stderr)
        return 1

    problems = []

    src = dest / "library" / "01-sources"
    for f in src.rglob("*.md"):
        body = f.read_text(encoding="utf-8", errors="ignore").split("---", 2)[-1].strip()
        if len(body) > BODY_LIMIT:
            problems.append(f"正文未剥离：{f.name}（{len(body)} 字）")

    # 来源痕迹的精确判定在 test_pack.py，这里只查最直白的两样
    for f in list((dest / "library").rglob("*.md")) + list((dest / "index").rglob("*.json")):
        t = f.read_text(encoding="utf-8", errors="ignore")
        if "src_file:" in t:
            problems.append(f"残留 src_file：{f.name}")
        if str(Path.home()) in t:
            problems.append(f"残留本机路径：{f.name}")
    if problems:
        print("\n".join(problems))
        return 1

    kept = sum(1 for f in src.rglob("*.md")
               if "正文未随包分发" not in f.read_text(encoding="utf-8"))
    print(f"分享包干净：01-sources 共 {sum(1 for _ in src.rglob('*.md'))} 条，"
          f"其中带正文 {kept} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
