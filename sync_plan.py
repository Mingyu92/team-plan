#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把飞书「月计划表」里某个月的计划，同步到团队计划网页。

用法（在任意目录）：
    python sync_plan.py                 # 同步当月
    python sync_plan.py --month 2026-11 # 同步指定月份
    python sync_plan.py --dry-run       # 只看拉到什么，不写文件

做三件事：
  1. 用 lark-cli 拉「诗媛生意进展 / 月计划表」的记录
  2. 只留指定月份的行，按「大类」分成三栏
  3. 替换 index.html 和 team-structure.html 里 PLAN_DATA_START / END 之间的内容
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

BASE_TOKEN = "MpskbFpSqah0JcsWk1Jc8g01nNg"
TABLE_ID = "tblacxgD46R5O577"
MONTH_NAMES = [str(m) + " 月" for m in range(1, 13)]

DEFAULT_FILES = [
    Path(r"C:\Users\14374\team-plan-site\index.html"),
    Path(r"C:\Users\14374\tuanxun_html\team-structure.html"),
]

BEGIN = "/* PLAN_DATA_START */"
END = "/* PLAN_DATA_END */"


def fetch_rows():
    cmd = [
        "lark-cli", "base", "+record-list",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--page-size", "200",
        "--format", "json",
        "--as", "user",
    ]
    out = subprocess.run(
        " ".join(cmd), shell=True, capture_output=True,
        encoding="utf-8", errors="replace")
    if out.returncode != 0:
        sys.exit("lark-cli 调用失败：\n" + out.stderr)
    data = json.loads(out.stdout)["data"]
    names = data["fields"]
    return [dict(zip(names, row)) for row in data["data"]]


def txt(v):
    """飞书字段值转成纯文本（文本字段可能是 str 或 [{"text":...}]）。"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        parts = []
        for x in v:
            if isinstance(x, str):
                parts.append(x)
            elif isinstance(x, dict):
                parts.append(x.get("text") or x.get("name") or "")
        return "".join(parts).strip()
    if isinstance(v, dict):
        return (v.get("text") or v.get("name") or "").strip()
    return str(v).strip()


def num(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else f


def month_label(month):
    y, m = month.split("-")
    return "%s 年 %d 月 · 月计划" % (y, int(m))


def build(month):
    rows = fetch_rows()
    groups, order = {}, []
    for r in rows:
        if not txt(r.get("月份")).startswith(month):
            continue
        if num(r.get("本月计划")) == 0:      # 隐藏掉不属于当月的模板行
            continue
        g = txt(r.get("大类")) or "其他"
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append({
            "tag": txt(r.get("子任务")),
            "text": txt(r.get("具体内容")),
            "target": num(r.get("需要完成量")),
            "note": txt(r.get("备注")),
        })
    return {
        "label": month_label(month),
        "syncedAt": date.today().isoformat(),
        "groups": [{"name": g, "items": groups[g]} for g in order],
    }


def to_js(plan):
    body = json.dumps(plan, ensure_ascii=False, indent=4)
    body = "\n".join("  " + line for line in body.splitlines())
    return BEGIN + "\n  var PLAN = " + body.strip() + ";\n  " + END


def patch(path, block):
    text = path.read_text(encoding="utf-8")
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < 0:
        sys.exit("%s 里没有找到 PLAN_DATA 标记，先手工加一次。" % path)
    new = text[:i] + block + text[j + len(END):]
    path.write_text(new, encoding="utf-8")
    return text != new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=date.today().strftime("%Y-%m"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--file", action="append", default=None)
    args = ap.parse_args()

    plan = build(args.month)
    n = sum(len(g["items"]) for g in plan["groups"])
    print("拉到 %s：%d 项，分 %d 栏（%s）" % (
        plan["label"], n, len(plan["groups"]),
        " / ".join(g["name"] for g in plan["groups"])))
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return

    block = to_js(plan)
    files = [Path(f) for f in args.file] if args.file else DEFAULT_FILES
    for f in files:
        if not f.exists():
            print("跳过（不存在）：%s" % f)
            continue
        changed = patch(f, block)
        print(("已更新：" if changed else "没有变化：") + str(f))


if __name__ == "__main__":
    main()
