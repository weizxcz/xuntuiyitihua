#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_mismatched_steps.py
---------------------------
从 Blind hole 训练日志里找出所有因"标注面数与 graph 面数不一致"而被跳过
（即没有构建 graph 图）的 step，对照 step 文件目录把它们定位出来，
并（可选）复制到一个独立目录，方便后续逐个排查。

判定依据（日志里的 WARNING 行）：
    跳过 <step名>：标注面数(X)与graph面数(Y)不匹配

用法
----
# 1) 仅列出 + 统计（不复制文件），结果写到 out_dir/_report.txt 和 .csv
python extract_mismatched_steps.py \
    --log "Geo-Rec/logs/Blind hole/run_20260615_065732.log" \
    --step-dir "/mnt/data/geometry_data/steps/step_files_tyb/田一冰_v15_v23_2" \
    --out-dir "/mnt/data/geometry_data/steps/blind_hole_mismatched"

# 2) 同时把命中的 .stp/.step 文件复制到 out_dir（--copy 开关）
python extract_mismatched_steps.py ... --copy

说明
----
- step 目录里扩展名有 .stp / .step / .STEP / .STP 四种混用，
  脚本会依次尝试这些后缀（大小写敏感），命中第一个即取用。
- 日志中的 step 名是按 train→val→test 出现顺序的；同一 step 不会重复
  （本日志 4745 条全部唯一）。
"""

import argparse
import csv
import os
import re
import shutil
import sys
from collections import Counter


# 匹配形如： 跳过 <名字>：标注面数(124)与graph面数(127)不匹配
# 用全角冒号「：」切分，名字里允许出现任意非冒号字符（含空格、括号、×、╱ 等）。
MISMATCH_RE = re.compile(
    r"跳过\s+(?P<name>[^：]+?)：标注面数\((?P<anno>\d+)\)与graph面数\((?P<graph>\d+)\)不匹配"
)

# step 目录里可能出现的扩展名，按优先级尝试。
STEP_EXTS = (".stp", ".step", ".STEP", ".STP")


def parse_log(log_path):
    """从日志中解析出所有被跳过的 step，返回 [(name, anno, graph), ...]（保持出现顺序）。"""
    if not os.path.isfile(log_path):
        sys.exit(f"[错误] 日志文件不存在: {log_path}")

    rows = []
    seen = set()
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = MISMATCH_RE.search(line)
            if not m:
                continue
            name = m.group("name").strip()
            anno = int(m.group("anno"))
            graph = int(m.group("graph"))
            # 同名 step 去重，保留第一次出现
            if name in seen:
                continue
            seen.add(name)
            rows.append((name, anno, graph))
    return rows


def find_step_file(name, step_dir):
    """在 step_dir 下按候选扩展名查找真实文件，返回相对文件名或 None。"""
    for ext in STEP_EXTS:
        candidate = os.path.join(step_dir, name + ext)
        if os.path.isfile(candidate):
            return name + ext
    return None


def main():
    ap = argparse.ArgumentParser(
        description="从 Blind hole 日志中提取面数不匹配的 step，并对照文件目录定位"
    )
    ap.add_argument(
        "--log", required=True,
        help="训练日志路径，例如 'Geo-Rec/logs/Blind hole/run_20260615_065732.log'",
    )
    ap.add_argument(
        "--step-dir", required=True,
        help="step 文件目录，例如 /mnt/data/geometry_data/steps/step_files_tyb/田一冰_v15_v23_2",
    )
    ap.add_argument(
        "--out-dir", required=True,
        help="输出目录（写入报告 _report.txt、列表 .csv、命中清单 found.txt、未命中清单 missing.txt）",
    )
    ap.add_argument(
        "--copy", action="store_true",
        help="附带把命中的 step 文件复制到 out_dir/files/ 下",
    )
    args = ap.parse_args()

    if not os.path.isdir(args.step_dir):
        sys.exit(f"[错误] step 目录不存在: {args.step_dir}")

    # 1) 解析日志
    rows = parse_log(args.log)
    print(f"[1/4] 日志解析完成：共 {len(rows)} 个不匹配 step（已按名称去重）")

    # 2) 对照文件目录定位
    found, missing = [], []
    for name, anno, graph in rows:
        rel = find_step_file(name, args.step_dir)
        if rel:
            found.append((name, anno, graph, rel))
        else:
            missing.append((name, anno, graph))

    print(f"[2/4] 目录对照完成：命中 {len(found)}，未命中 {len(missing)}")

    # 3) 写输出
    os.makedirs(args.out_dir, exist_ok=True)
    report_path = os.path.join(args.out_dir, "_report.txt")
    csv_path = os.path.join(args.out_dir, "mismatched_steps.csv")
    found_path = os.path.join(args.out_dir, "found.txt")
    missing_path = os.path.join(args.out_dir, "missing.txt")

    # ---- csv：name, anno_faces, graph_faces, diff, file ----
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["step_name", "anno_faces", "graph_faces", "diff", "file"])
        for name, anno, graph, rel in found:
            w.writerow([name, anno, graph, graph - anno, rel])
        for name, anno, graph in missing:
            w.writerow([name, anno, graph, graph - anno, ""])

    # ---- 纯文件名清单 ----
    with open(found_path, "w", encoding="utf-8") as f:
        for _, _, _, rel in found:
            f.write(rel + "\n")
    with open(missing_path, "w", encoding="utf-8") as f:
        for name, _, _ in missing:
            f.write(name + "\n")

    # ---- 文本报告 ----
    diffs = [graph - anno for _, anno, graph in rows]
    ext_counter = Counter(os.path.splitext(rel)[1] for _, _, _, rel in found)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("Blind hole —— 面数不匹配 step 定位报告\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"日志文件      : {args.log}\n")
        f.write(f"step 目录     : {args.step_dir}\n")
        f.write(f"输出目录      : {args.out_dir}\n\n")
        f.write(f"日志中不匹配 step 总数 : {len(rows)}\n")
        f.write(f"  - 命中文件        : {len(found)}\n")
        f.write(f"  - 未命中文件      : {len(missing)}\n\n")
        f.write("面数差值（graph面数 - 标注面数）统计：\n")
        f.write(f"  - 全部为 graph面数 > 标注面数 : "
                f"{sum(1 for d in diffs if d > 0) == len(diffs)}\n")
        f.write(f"  - 最小差值 : {min(diffs)}\n")
        f.write(f"  - 最大差值 : {max(diffs)}\n")
        f.write(f"  - 平均差值 : {sum(diffs) / len(diffs):.1f}\n\n")
        f.write("命中的扩展名分布：\n")
        for ext, n in sorted(ext_counter.items()):
            f.write(f"  {ext or '(无)'}: {n}\n")
        f.write("\n")
        if missing:
            f.write(f"未命中文件（{len(missing)} 个），见 missing.txt\n\n")

    print(f"[3/4] 报告与清单已写入: {args.out_dir}")
    print(f"        - {report_path}")
    print(f"        - {csv_path}")
    print(f"        - {found_path} / {missing_path}")

    # 4) 可选：复制文件
    if args.copy:
        copy_dir = os.path.join(args.out_dir, "files")
        os.makedirs(copy_dir, exist_ok=True)
        ok = 0
        for name, anno, graph, rel in found:
            src = os.path.join(args.step_dir, rel)
            dst = os.path.join(copy_dir, rel)
            try:
                shutil.copy2(src, dst)
                ok += 1
            except Exception as e:
                print(f"   复制失败 {rel}: {e}", file=sys.stderr)
        print(f"[4/4] 已复制 {ok}/{len(found)} 个文件到 {copy_dir}")
    else:
        print("[4/4] 跳过复制（如需复制请加 --copy）")

    # 控制台摘要
    print()
    print("=" * 60)
    print(f"不匹配 step 总数 : {len(rows)}")
    print(f"  命中           : {len(found)}")
    print(f"  未命中         : {len(missing)}")
    if rows:
        diffs = [g - a for _, a, g in rows]
        print(f"  差值范围       : [{min(diffs)}, {max(diffs)}]  (graph面数 - 标注面数)")
    print("=" * 60)


if __name__ == "__main__":
    main()
