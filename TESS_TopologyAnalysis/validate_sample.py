# -*- coding: utf-8 -*-
"""
抽样验证: 跑多种分配策略(v1)的仿真, 产出提交产物到 test_vN/B{n}/。
[注意] 本脚本【不本地算分】(rescore 已移除)。评分由竞赛网页完成:
   跑完后用 pack_submit.py 把对应 test_vN/ 压缩, 提交网页下载官方 score.csv, 再横向比较版本。
- 按批次数(6/7/8/9/10/11/12)各取代表题实跑(与 test/ 跨版本可比)
- 每种策略独立落盘到 TESS_PythonAPI/test_vN/B{n}/ (不动冻结的 test/)
- 一次只跑一个仿真(内存安全)
环境变量:
  MODES=generic,orig8,hybrid   (依次跑, 落盘 test_v1/ test_v2/ test_v3/)
  ASSIGN_MODE 由本脚本按 MODES 逐个设置并透传给 Baseline.run_baseline
用法:
  D:\Environment\anaconda3\envs\onsite2\python.exe validate_sample.py
"""
import os, sys, time
# run_low_score 已收进本目录(2026-08-02 整理), 无需再依赖上级 dev/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_low_score as r

INP = r.INPUT
TESS_API = r.BASE  # E:\...\TESS_PythonAPI

MODE_TO_VER = {"generic": "test_v1", "orig8": "test_v2", "hybrid": "test_v3"}


def batch_count(sid):
    f = os.path.join(INP, f"B_B{sid}_input", "task.csv")
    if not os.path.exists(f):
        return None
    import csv as _csv
    with open(f, encoding="gbk") as fh:
        return sum(1 for _ in _csv.DictReader(fh))


def pick_sample():
    """按批次数各取1题(首个)+ 8批额外取一题做稳定性检查"""
    from collections import defaultdict
    bc2sids = defaultdict(list)
    for n in range(1, 81):
        bc = batch_count(n)
        if bc:
            bc2sids[bc].append(n)
    sample = []
    for bc in sorted(bc2sids):
        sids = bc2sids[bc]
        sample.append(sids[0])
        if bc == 8 and len(sids) > 1:
            sample.append(sids[1])
    return sorted(set(sample))


def artifacts_ready(ver, sid):
    """该场景产物是否已存在且完整(用于跳过重跑, 非算分)"""
    d = os.path.join(TESS_API, ver, f"B{sid}")
    idp = os.path.join(d, "id.csv")
    opp = os.path.join(d, "operation_state.csv")
    return (os.path.exists(idp) and os.path.getsize(idp) > 0 and
            os.path.exists(opp) and os.path.getsize(opp) > 0)


def run_mode(mode, sids):
    os.environ["ASSIGN_MODE"] = mode
    # OUT_VER 可显式指定产物目录名(如 test_v5), 便于同一 ASSIGN_MODE 下
    # 对比不同 Baseline 版本而不覆盖旧版本产物。
    ver = os.environ.get("OUT_VER") or MODE_TO_VER.get(mode, f"test_v_{mode}")
    r.TEST_NEW = os.path.join(TESS_API, ver)  # run_one 落盘到 test_vN/B{n}
    print(f"\n########## 模式 {mode} -> {ver} ##########", flush=True)
    produced = 0
    skipped = 0
    for sid in sids:
        bc = batch_count(sid)
        if artifacts_ready(ver, sid):
            print(f"B{sid:<5}{str(bc):<5} 跳过(产物已存在) -> {ver}/B{sid}", flush=True)
            skipped += 1
            continue
        try:
            ok, _ = r.run_one(sid)            # 一次一个仿真, 只产出产物
            if ok:
                produced += 1
                print(f"B{sid:<5}{str(bc):<5} 产物已产出 -> {ver}/B{sid}", flush=True)
            else:
                print(f"B{sid:<5}{str(bc):<5} 失败", flush=True)
        except Exception as e:
            print(f"B{sid}: run_one 异常 {e}", flush=True)
    print(f"[{mode}] 新产出 {produced} 题, 跳过 {skipped} 题", flush=True)
    print(f"[{mode}] 产物目录: {os.path.join(TESS_API, ver)}", flush=True)
    print(f"[{mode}] 下一步: pack_submit.py {os.path.join(TESS_API, ver)} 压缩后提交网页评分", flush=True)


def main():
    if len(sys.argv) > 1:
        sids = []
        for tok in sys.argv[1:]:
            sids += [int(x) for x in tok.replace(",", " ").split() if x.strip()]
    else:
        sids = pick_sample()

    modes = os.environ.get("MODES", "generic,orig8,hybrid").split(",")
    modes = [m.strip() for m in modes if m.strip()]

    print(f"抽样场景: {sids}", flush=True)
    print(f"模式顺序: {modes}  (依次跑, 一次一个仿真)", flush=True)
    t0 = time.time()
    for mode in modes:
        run_mode(mode, sids)
    print(f"\n===== 全部模式产物产出完成, 耗时 {time.time()-t0:.0f}s =====", flush=True)
    print("[注意] 本脚本不本地算分。请用 pack_submit.py 把各 test_vN/ 压缩提交网页,", flush=True)
    print("   下载官方 score.csv 后, 用 compare_scores.py 横向比较版本择优。", flush=True)


if __name__ == "__main__":
    main()
