#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
重跑题目，产出仿真结果产物(供提交网页评分)。
⚠️ 评分一律由竞赛网页完成: 跑完把结果目录压缩后提交到网页, 下载官方 score.csv。
   本脚本【不再本地算分】(rescore 已移除, 因其口径与官方不一致, 会误导对比)。

旧分数来源(仅用于筛选低分题/参考, 不参与本地评分):
  SSoT = 仓库根目录 score.csv (80套题官方权威全量分, 212418.31);
  旧 TESS_PythonAPI/test/score.csv 已缺失, 现改指根目录 SSoT 以恢复自动挑低分题。

产物: 每题在 TEST_NEW/B{n}/ 下生成 id.csv / operation_state.csv / penalty.csv / task.csv
      这些 csv 即提交网页的评分输入。

用法:
  校验输入(不启动仿真):  python run_low_score.py --dry-run
  正式重跑(需本机装有 TESS NG + onsite2 环境 + 桌面会话):
                          D:\Environment\anaconda3\envs\onsite2\python.exe run_low_score.py
  打包提交:                D:\Environment\anaconda3\envs\onsite2\python.exe pack_submit.py
"""
import csv, os, shutil, subprocess, sys, time
from collections import defaultdict

BASE      = os.path.dirname(os.path.abspath(__file__)) if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")) else r"E:\Desktop\dev\OnSite-Transportation\TESS_PythonAPI"
TEST_NEW  = os.path.join(BASE, "test", "new_test")
INPUT     = os.environ.get("ONSITE_INPUT", r"E:\Desktop\dev\OnSite-Transportation\Test Paper B\B")
# 旧分数仅用于筛选低分题/参考, 不参与本地评分
SCORE_CSV = os.path.join(BASE, "score.csv") if os.path.exists(os.path.join(BASE, "score.csv")) else os.path.join(os.path.dirname(BASE), "score.csv")  # SSoT 权威全量分(根目录)
PYTHON    = os.environ.get("ONSITE_PYTHON", r"D:\Environment\anaconda3\envs\onsite2\python.exe")
KILL_TESS = r"C:\Users\Administrator\AppData\Local\Temp\kill_tess_only.ps1"
MAIN_PY   = os.path.join(BASE, "main.py")
MAX_TIME  = 3600

# ============== 步骤 1：加载旧分数(仅参考) ==============
def load_old_scores():
    """从 SCORE_CSV 读取旧分数，第9列(索引8)=总得分。仅用于筛选/参考。"""
    scores = {}
    if not os.path.exists(SCORE_CSV):
        return scores
    with open(SCORE_CSV, 'rb') as f:
        text = f.read().decode('utf-8-sig')
    for line in text.strip().split('\n')[1:]:
        parts = line.split(',')
        if len(parts) < 9:
            continue
        scene = parts[2].strip()
        if not scene.startswith('B'):
            continue
        try:
            scores[scene] = float(parts[8].strip())
        except ValueError:
            scores[scene] = 0.0
    return scores

# ============== 步骤 2：筛选低分题 ==============
def get_low_scenes(old_scores, threshold=1500):
    """返回分数 < threshold 的题号列表，按数字排序"""
    scenes = sorted([s for s, v in old_scores.items() if v < threshold],
                    key=lambda x: int(x[1:]))
    print(f"旧分数 < {threshold} 的题目共 {len(scenes)} 道:")
    for s in scenes:
        print(f"  {s}: {old_scores[s]:.2f}")
    return scenes

# ============== 步骤 2b：咽喉白名单按分数自动限定 ==============
_throat_low_cache = None
def throat_low_score_set(threshold):
    """基于 SSoT score.csv 选出「低分题」(总得分 < threshold) 的题号集合(纯数字字符串)。
    仅用于自动设定 THROAT_SCENES 白名单: 保证高分题绝不被咽喉改道(避免回归)。
    score.csv 缺失时返回空集 -> 白名单为空 -> 咽喉机制安全关闭(fail-closed)。"""
    global _throat_low_cache
    if _throat_low_cache is None:
        scores = load_old_scores()
        _throat_low_cache = {s.lstrip("Bb") for s, v in scores.items() if v < threshold}
    return _throat_low_cache

# ============== 步骤 3：补 csv 表头(数据整理, 非算分) ==============
def fix_csv_headers(scene_dir):
    """修复各 csv 首行表头，使提交网页的产物格式正确。"""
    fixes = {
        "id.csv":               "id",
        "operation_state.csv":  "vehicle_id,road_id,state,simu_time,wait_s,end_s",
        "penalty.csv":          "butt,conflict",
    }
    for fname, header in fixes.items():
        path = os.path.join(scene_dir, fname)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            first = f.readline().strip()
        if first != header and first != "":
            print(f"    修复 {fname} 表头: {first} -> {header}")
            with open(path) as f:
                data = f.read().strip()
            with open(path, 'w') as f:
                f.write(header + '\n' + data)

# ============== 步骤 4：杀 TESS NG ==============
def kill_tess():
    """只杀 TESS NG 进程，不杀自身"""
    subprocess.run(
        ["powershell", "-File", KILL_TESS],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30
    )
    time.sleep(2)


def _kill_tree(pid):
    """杀掉进程及其子进程树(含 TESS GUI 残留)，不依赖外部 ps1"""
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    except Exception as e:
        print(f"  kill_tree {pid} 失败: {e}")


# ============== 步骤 5：跑单题(只产出产物, 不算分) ==============
def run_one(scene_id):
    """
    跑一道题，保存到 TEST_NEW/B{n}/ (产出提交网页用的产物)。
    返回: (成功bool, None)  -- 本地不再算分, 分数由网页给出。
    """
    bid  = f"B_B{scene_id}"
    scene = f"B{scene_id}"
    input_dir = os.path.join(INPUT, f"{bid}_input")
    new_dir   = os.path.join(TEST_NEW, scene)

    task_csv = os.path.join(input_dir, "task.csv")
    veh_csv  = os.path.join(input_dir, "vehicle.csv")

    if not os.path.exists(task_csv):
        print(f"  跳过 {scene}：无 task.csv")
        return False, None

    # ---- 清空 Output ----
    os.makedirs(os.path.join(BASE, "Output"), exist_ok=True)
    for f in ["id.csv", "operation_state.csv", "penalty.csv"]:
        open(os.path.join(BASE, "Output", f), 'w').close()
    # ⚠️ 同时清空 BASE/vehicle_state.csv: run_one 的停滞/收尾监控读它末行 simu_time,
    #   若不清除会残留上一题的 3600 导致启动瞬间误判"已达总时长"(虽会被真实 sim 时钟复位, 但留噪音)。
    vsf = os.path.join(BASE, "vehicle_state.csv")
    # ⚠️ 用 "w" 截断清空, 绝不用 os.remove —— 本机 sitecustomize 把 os.remove patch 成
    #   _safe_remove, 其内 subprocess.run(capture_output=True) 在 onsite2(Py3.6.8)下崩溃
    #   (见 _archive_dev/sim_lock.py 注释)。截断写清空且无 os.remove 调用, 不触发钩子。
    try:
        open(vsf, "w").close()
    except OSError:
        pass

    # ---- 复制输入文件 ----
    # ⚠️ 官方约定(见 Baseline_docker_ref.py): task.csv 在 Output/ , vehicle.csv 在【根目录】
    #    Baseline.py 第301行 pd.read_csv("vehicle.csv") 读的是 BASE/vehicle.csv。
    #    历史 BUG: 只复制到 Output/vehicle.csv, 导致车辆数永远沿用根目录旧值(14辆),
    #    18/24/30 辆的题实际只调度 14 辆 -> 少调度、任务未完成扣分暴涨。
    shutil.copy2(task_csv, os.path.join(BASE, "Output", "task.csv"))
    shutil.copy2(veh_csv,  os.path.join(BASE, "vehicle.csv"))          # 主: Baseline 实际读这个
    shutil.copy2(veh_csv,  os.path.join(BASE, "Output", "vehicle.csv"))  # 兼容: 保持两处一致
    try:
        with open(veh_csv, 'rb') as _f:
            _vtxt = _f.read().decode('gbk', 'ignore').strip().split('\n')
        print(f"  [输入] {scene} vehicle.csv -> {_vtxt[1] if len(_vtxt) > 1 else '?'}")
    except Exception:
        pass

    # ---- 启动仿真(带仿真停滞监控, 防卡死) ----
    env = os.environ.copy()
    env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    env["PYTHONPATH"] = ""          # 清除 hermes python3.11 污染
    env["MAX_SIM_TIME"] = str(MAX_TIME)
    # 告知 Baseline 当前题号, 供 THROAT_SCENES 白名单按场景生效(不设则该白名单失效)
    env["SCENE_ID"] = str(scene_id)

    # 咽喉白名单按分数自动限定: 仅低分题可触发改道, 高分题一律不碰(防回归)。
    # 用户显式设了 THROAT_SCENES 则尊重其设定; 否则按 SSoT 分数阈值自动生成白名单。
    if os.environ.get("AVOID_THROAT") and not os.environ.get("THROAT_SCENES", "").strip():
        _thr = float(os.environ.get("THROAT_SCORE_THRESHOLD", "1500") or 1500)
        _low = throat_low_score_set(_thr)
        if _low:
            env["THROAT_SCENES"] = ",".join(sorted(_low, key=lambda x: int(x)))
            print(f"  [throat] AVOID_THROAT 已开, 按低分阈值 {_thr:.0f} 自动限定白名单"
                  f"(高分题不触发): {env['THROAT_SCENES']}", flush=True)
        else:
            print(f"  [throat] 警告: 低分白名单为空(score.csv 缺失或阈值过高), "
                  f"咽喉机制安全关闭", flush=True)

    run_timeout = int(os.environ.get("RUN_TIMEOUT", "7200"))
    # 【v7】Baseline 的 MAX_STALE 已默认关闭, 内层只在【真实仿真钟】到 3600s 才退。
    # 外层这道停滞墙同样改看真实仿真钟(见下), 只有引擎真的不推进(TESS 崩了/挂死)
    # 才触发, 故可放宽到 900s, 避免误杀本来还能跑的仿真。
    stale_wall = int(os.environ.get("STALE_WALL", "900"))
    # 注: 到达总时长后不再强制收尾宽限, 交由 TESS 自然退出; 若真卡死由 stale_wall 兜底。
    print(f"\n[{time.strftime('%H:%M')}] {scene} 开始 (run_timeout={run_timeout}s, stale_wall={stale_wall}s)")
    start = time.time()
    last_sim = None
    last_progress = time.time()
    killed = False
    proc = None
    try:
        proc = subprocess.Popen([PYTHON, MAIN_PY], cwd=BASE, env=env)
        while True:
            rc = proc.poll()
            if rc is not None:
                print(f"  {scene} 子进程正常退出 rc={rc}", flush=True)
                break
            # 【v7】停滞判定改看【真实仿真钟】(vehicle_state.csv 末行 simu_time),
            # 而不是 operation_state.csv(= 最后一次装卸作业时刻)。
            # 车队若被平台批量终止, 作业时刻会永久定格, 但仿真引擎仍在推进 ——
            # 用旧口径会把"车死了"误杀成"卡死", 且掩盖真实病因。
            # vehicle_state 很大(十几 MB), 用 seek 到尾部只读最后一块。
            vsf = os.path.join(BASE, "vehicle_state.csv")
            cur_sim = None
            try:
                if os.path.exists(vsf):
                    with open(vsf, "rb") as fh:
                        fh.seek(0, os.SEEK_END)
                        sz = fh.tell()
                        fh.seek(max(0, sz - 8192))
                        tail = fh.read().decode("utf-8", "ignore")
                    for ln in reversed([x for x in tail.splitlines() if x.strip()]):
                        parts = ln.split(",")
                        if len(parts) >= 10:
                            try:
                                cur_sim = float(parts[9])   # simu_time 是第 10 列
                                break
                            except ValueError:
                                continue
            except Exception:
                cur_sim = None
            if cur_sim is None:      # 兜底: 回退旧口径
                try:
                    opf = os.path.join(BASE, "Output", "operation_state.csv")
                    if os.path.exists(opf):
                        with open(opf, encoding="utf-8") as fh:
                            last = ""
                            for line in fh:
                                if line.strip():
                                    last = line
                        if last and len(last.split(",")) >= 4:
                            cur_sim = float(last.split(",")[3])
                except Exception:
                    cur_sim = None
            if cur_sim is not None and (last_sim is None or cur_sim > last_sim):
                last_sim = cur_sim
                last_progress = time.time()
            # 仿真停滞: 长时间无仿真时钟进展 -> 判定卡死, 强制结束
            if time.time() - last_progress > stale_wall:
                print(f"  仿真停滞 {stale_wall}s 无进展(末simu_time={last_sim})，强制结束", flush=True)
                killed = True
                _kill_tree(proc.pid)
                break
            if time.time() - start > run_timeout:
                print(f"  超时 {run_timeout}s，杀掉", flush=True)
                killed = True
                _kill_tree(proc.pid)
                break
            time.sleep(5)
    except Exception as e:
        print(f"  启动/监控异常: {e}", flush=True)
        killed = True

    if proc is not None and proc.poll() is None:
        _kill_tree(proc.pid)
    try:
        if proc is not None:
            proc.wait(timeout=30)
    except Exception:
        pass
    time.sleep(3)

    # ---- 检查输出 ----
    id_csv = os.path.join(BASE, "Output", "id.csv")
    if not os.path.exists(id_csv) or os.path.getsize(id_csv) == 0:
        print(f"  {scene} 无输出")
        return False, None

    # ---- 保存到 TEST_NEW/B{n}/ (提交网页的产物) ----
    os.makedirs(new_dir, exist_ok=True)
    for f in ["id.csv", "operation_state.csv", "penalty.csv", "task.csv"]:
        src = os.path.join(BASE, "Output", f)
        dst = os.path.join(new_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, dst)

    fix_csv_headers(new_dir)
    print(f"  完成 {scene}: 产物已保存到 {new_dir} (分数由网页给出)")
    return True, None


# ============== 步骤 6：主流程 ==============
def main():
    dry = "--dry-run" in sys.argv
    print("=" * 60)
    print("重跑产出提交产物(本地不算分)" + (" [DRY-RUN]" if dry else ""))
    print("=" * 60)

    old_scores = load_old_scores()
    print(f"\n共读取 {len(old_scores)} 道题的参考旧分数")

    low_scenes = get_low_scenes(old_scores, threshold=1500)
    print(f"\n{'='*60}\n")

    # --only B{n}: 仅跑单个场景(用于探测)
    if "--only" in sys.argv:
        idx = sys.argv.index("--only") + 1
        only = sys.argv[idx] if idx < len(sys.argv) else ""
        if only:
            only = only.upper().lstrip("B") if only.upper().startswith("B") else only
            low_scenes = [s for s in low_scenes if s.upper().lstrip("B") == str(int(only))]
            print(f"--only 模式: 仅跑 {low_scenes}")

    if dry:
        print("DRY-RUN: 仅校验输入文件，不启动仿真")
        ok = 0
        for scene in low_scenes:
            sid = int(scene[1:])
            input_dir = os.path.join(INPUT, f"B_B{sid}_input")
            has = (os.path.exists(os.path.join(input_dir, "task.csv")) and
                   os.path.exists(os.path.join(input_dir, "vehicle.csv")))
            print(f"  {scene}: 输入{'OK' if has else '缺失'}  -> {input_dir}")
            ok += 1 if has else 0
        print(f"\nDRY-RUN 完成: {ok}/{len(low_scenes)} 个场景输入就绪")
        return

    done, fail = 0, 0
    for scene in low_scenes:
        sid = int(scene[1:])
        ok, _ = run_one(sid)
        done += 1 if ok else 0
        fail += 0 if ok else 1

    print(f"\n{'='*60}")
    print(f"产物产出完成: 成功 {done} / 失败 {fail}")
    print(f"产物目录: {TEST_NEW}")
    print(f"下一步: 运行 pack_submit.py 把结果目录压缩, 提交到竞赛网页下载官方 score.csv")


if __name__ == "__main__":
    main()
