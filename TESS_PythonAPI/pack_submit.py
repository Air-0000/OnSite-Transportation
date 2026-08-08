#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把仿真产物目录压缩成提交网页用的包。
⚠️ 只负责打包, 不评分。评分由竞赛网页对压缩包完成, 下载官方 score.csv。

用法:
  D:\Environment\anaconda3\envs\onsite2\python.exe pack_submit.py [结果目录] [--with-root]
  结果目录 默认: TESS_PythonAPI/test   (也可传 test_v1 / test/new_test 等)

产物: 在结果目录同级生成 {目录名}_submit.zip
  ⚠️ 默认扁平结构: 压缩包内直接是 B1/B2/.../B80 (无 test/ 顶层文件夹),
     符合网站要求。加 --with-root 才保留顶层文件夹。
"""
import os
import sys
import zipfile

BASE = r"E:\Desktop\dev\OnSite-Transportation\TESS_PythonAPI"

REQUIRED = ["id.csv", "operation_state.csv", "penalty.csv"]
OPTIONAL = ["task.csv"]


def validate(src):
    """检查每题产物是否齐全, 返回 (ok_list, missing_list)"""
    ok, missing = [], []
    if not os.path.isdir(src):
        return ok, missing
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        if not os.path.isdir(d) or not name.startswith("B"):
            continue
        lacks = [f for f in REQUIRED if not os.path.exists(os.path.join(d, f))]
        if lacks:
            missing.append((name, lacks))
        else:
            ok.append(name)
    return ok, missing


def main():
    args = sys.argv[1:]
    with_root = "--with-root" in args
    src_args = [a for a in args if not a.startswith("--")]
    src = src_args[0] if src_args else os.path.join(BASE, "test")
    src = os.path.abspath(src)
    if not os.path.isdir(src):
        print(f"结果目录不存在: {src}")
        sys.exit(1)

    ok, missing = validate(src)
    print(f"校验 {src}")
    print(f"  产物齐全场景: {len(ok)}")
    if missing:
        print(f"  ⚠️ 缺失产物(将被跳过, 不影响其余):")
        for name, lacks in missing:
            print(f"    {name}: 缺 {lacks}")
    else:
        print("  ✅ 所有 B 场景产物齐全")

    parent = os.path.dirname(src)
    base = os.path.basename(src.rstrip(os.sep))
    out_zip = os.path.join(parent, f"{base}_submit.zip")
    # 用 "w" 模式直接覆盖旧包(避免触发沙箱批量删除钩子)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(src)):
            d = os.path.join(src, name)
            if not os.path.isdir(d) or not name.startswith("B"):
                continue
            for root, _, files in os.walk(d):
                for f in files:
                    fp = os.path.join(root, f)
                    if with_root:
                        arc = os.path.join(base, os.path.relpath(fp, src))
                    else:
                        arc = os.path.relpath(fp, src)  # 扁平: B1/id.csv
                    z.write(fp, arc)

    print(f"\n✅ 提交包已生成: {out_zip}")
    if with_root:
        print(f"   结构: {base}/B1/... {base}/B80/... (每题含 {REQUIRED})")
    else:
        print(f"   结构: B1/... B80/... (扁平, 无顶层文件夹, 每题含 {REQUIRED})")
    print(f"   下一步: 用 upload_submit.py 上传该 zip, 下载官方 score.csv 后,")
    print(f"           用 compare_scores.py 与 test/score.csv 对比。")


if __name__ == "__main__":
    main()
