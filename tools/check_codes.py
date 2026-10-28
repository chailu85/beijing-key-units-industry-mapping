#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核对 Markdown 中出现的 GB/T 4754 代码是否存在于官方注释字典。

用法：
    python tools/check_codes.py                       # 默认核 docs/ 下现行对照表
    python tools/check_codes.py docs/xxx.md [...]     # 核指定文件
    python tools/check_codes.py --rebuild             # 由 ref/*.xlsx 重建 ref/code_entries.json

说明：
- 字典 ref/code_entries.json 由官方《2017国民经济行业分类注释》XLSX 提取，
  条目形如 {"codes": ["4420"], "name": "电力供应", "row": 512, "notes": [...]}。
- 退出码 1 表示存在字典中查不到的代码，需人工确认是笔误还是刻意引用的不存在代码。
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "ref" / "code_entries.json"
XLSX = ROOT / "ref" / "GBT_4754-2017_分类注释.xlsx"
DEFAULT_DOC = ROOT / "docs" / "重点单位13类_GBT4754-2017条件性对照_v3.1_20261028.md"

# 4 位带前导零的小类，以及 2 位大类、1 位门类字母；5 位用于少量历史码
CODE_RE = re.compile(r"(?<![0-9A-Za-z])([0-9]{4}|[0-9]{2})(?![0-9])")

# 文档中会正常出现的非行业码数字串（年份、页码、条款号、标准号等），不参与校验
IGNORE = {"2017", "2023", "2026", "2022", "2020", "2018", "2025", "2552", "4754", "0001"}


def load_index():
    if not INDEX.exists():
        sys.exit(f"缺少字典 {INDEX}，先运行：python tools/check_codes.py --rebuild")
    entries = json.loads(INDEX.read_text(encoding="utf-8"))
    idx = {}
    for e in entries:
        for c in e.get("codes", []):
            idx[c] = e
    return entries, idx


def rebuild():
    try:
        from openpyxl import load_workbook
    except ImportError:
        sys.exit("重建字典需要 openpyxl（pip install openpyxl）；仅做校验则无需该依赖。")

    if not XLSX.exists():
        sys.exit(f"缺少注释原表 {XLSX}")
    wb = load_workbook(XLSX, read_only=True, data_only=True)
    entries = []
    for ws in wb:
        for n, row in enumerate(ws.iter_rows(values_only=True), 1):
            vals = [str(v).strip() if v is not None else "" for v in row]
            if not any(vals):
                continue
            code_cell = vals[0]
            codes = re.findall(r"[0-9]{2,5}|[A-T]", code_cell)
            if not codes:
                continue
            entries.append({"codes": codes, "name": vals[1], "row": n, "notes": [v for v in vals[2:] if v]})
    INDEX.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已重建 {INDEX.relative_to(ROOT)}，条目数 {len(entries)}")


def load_known_absent():
    """文档中刻意引用的「不存在代码」（用于说明区间不可机械展开），逐行写 代码 #理由。"""
    p = ROOT / "tools" / "known_absent.txt"
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out[line] = True
    return out


def check(path, idx, allowed):
    text = path.read_text(encoding="utf-8")
    body = re.sub(r"https?://\S+", " ", text)  # 排除 URL 中的数字片段
    found = sorted({c for c in CODE_RE.findall(body) if c not in IGNORE})
    missing = [c for c in found if c not in idx and c not in allowed]
    expected = [c for c in found if c not in idx and c in allowed]
    print(f"\n{path.relative_to(ROOT)}")
    print(f"  行业代码 {len(found)} 个；字典未收录 {len(missing)} 个（另 {len(expected)} 个为登记在案的不存在代码）")
    for c in missing:
        line = next((i for i, ln in enumerate(body.splitlines(), 1) if c in ln), 0)
        print(f"  ! {c}  首次出现于第 {line} 行，需人工确认")
    return missing


def main():
    args = sys.argv[1:]
    if "--rebuild" in args:
        rebuild()
        return 0
    _, idx = load_index()
    allowed = load_known_absent()
    targets = [Path(a).resolve() for a in args] or [DEFAULT_DOC]
    bad = 0
    for t in targets:
        if not t.exists():
            sys.exit(f"文件不存在：{t}")
        bad += len(check(t, idx, allowed))
    print("\n结论：" + ("存在未收录代码，请逐个人工确认" if bad else "全部代码在字典中可查"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
