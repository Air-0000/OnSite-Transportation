# =============================================================================
# 主办方案 Baseline —— 现场运输调度(赛题 track0409)
# -----------------------------------------------------------------------------
# 本文件为赛题「现场运输」的调度算法实现, 由主办方/参赛方在现场物流沙盘(TESS 仿真)
# 上跑分。算法对「卷/港区」无关: 起点、终点、路网、任务均按当前场景数据动态读取,
# 不硬编码任何 B卷特定拓扑 —— 换 C卷(不同港区、单终点)只需替换数据文件, 代码零改动。
# 全量刷分基线 = 214,737.49(官方), 由 v4 三模式(generic/optimized/ringseg) + 咽喉
# 改道 + 错峰发车组合得到。详见 .workbuddy/memory/MEMORY.md。
# =============================================================================
import pandas as pd
import csv
import time
import ast
import os
import re
import transit
from collections import defaultdict

# 动态起点/终点: 由 _resolve_endpoints 在首轮派单时按当前场景 task.csv 反推填充。
# 默认值(=模块级 EP_START/EP_END)为 B卷 82/191, 保持 v4 行为不变; 换 C卷(单终点)
# 无需改代码 —— 改 Shortest path.py 的 target_id 与 Scene/*.tess 即可。
# 注意: 回退分支统一引用 (EP_START, EP_END), 不再重复硬编码字面量, 避免与默认漂移。
EP_START = 82
EP_END = 191


def open_file_lazy(path, file_handle):
    if file_handle is not None:
        return file_handle
    if os.path.exists(path):
        try:
            f = open(path, "r")
            f.seek(0, os.SEEK_END)
            return f
        except:
            return None
    return None


def read_csv_new_lines(file_handle, data_list):
    if file_handle is None:
        return None
    try:
        new_lines = file_handle.readlines()
        if new_lines:
            reader = csv.DictReader(new_lines)
            data_list.extend(list(reader))
        return file_handle
    except:
        try:
            file_handle.close()
        except:
            pass
        return None


def choose_topo_mode(raw_tasks, vehicle_num):
    """OD 拓扑自适应选路: 归一化键名 -> od_classify -> 三模式(generic/optimized/ringseg)。
    pair/mixed -> generic; chain/ringpair -> optimized; ring -> ringseg。
    >=18车守卫已移除: optimized 用结构感知 spread(非0804交错式generic), 死锁风险交给
    STALE_WALL 超时强杀 + max(baseline,new) 兜底; 高车队若实测 gridlock 再加相位限流适配。
    mixed 的 seriality 分支(B卷仅 B13 且未验证)已弃用 -> mixed 统一走 generic。"""
    import os as _os
    import sys
    _d = _os.path.dirname(_os.path.abspath(__file__))
    if _d not in sys.path:
        sys.path.insert(0, _d)
    import od_classify
    od_tasks = [{"o": t["origin"], "d": t["dest"], "qty": t["qty"]} for t in raw_tasks]
    r = od_classify.classify_tasks(od_tasks)
    cat = r.get("cat", "mixed")
    mode = r.get("rec_mode", "generic")
    # mixed 中段默认走 generic(seriality 分支在 B卷仅 B13 且属未验证, 弃用)
    if cat == "mixed":
        mode = "generic"
    # (>=18车守卫已移除: 三模式按结构映射, 不按车数例外)
    return mode


# ===================== 动态咽喉道识别(可选, AVOID_THROAT 触发) =====================
# 旧版 AVOID_THROAT 仅硬编码 B67 的两条 OD 路径(对其它场景/OD 是 no-op)。
# 现改为: 按当前场景 OD 需求从全路网图自动定位「瓶颈边」(货运吞吐最高的有向边),
# 禁掉该边后用 Dijkstra 重算受影响 OD 的最短路径 —— 对任意场景通用, 不再写死 B67。
# 默认不触发(未设 AVOID_THROAT), v4 行为完全不变。
def _throat_enabled():
    """三级开关: 未设 AVOID_THROAT -> 关(v4 原样)。
    设了 AVOID_THROAT 且设了 THROAT_SCENES(如 "67,26,69") -> 仅这些场景生效,
    需由调用方通过 SCENE_ID 环境变量告知当前题号; 拿不到题号时保守关闭。"""
    if not os.environ.get("AVOID_THROAT"):
        return False
    only = os.environ.get("THROAT_SCENES", "").strip()
    if not only:
        return True
    sid = os.environ.get("SCENE_ID", "").strip().upper().lstrip("B")
    if not sid:
        return False
    allow = {s.strip().upper().lstrip("B")
             for s in only.replace(";", ",").split(",") if s.strip()}
    return sid in allow


def _throat_dijkstra(G, src, dst, forbid_edge=None):
    """最小跳数 Dijkstra; forbid_edge=(u,v) 时跳过该有向边。不可达返回 None。"""
    import heapq
    dist = {src: 0}
    prev = {src: None}
    pq = [(0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == dst:
            break
        if d > dist.get(u, float("inf")):
            continue
        for (v, w) in G.get(u, []):
            if forbid_edge is not None and (u, v) == forbid_edge:
                continue
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if dst not in prev:
        return None
    path, cur = [], dst
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
    return path[::-1]


def _throat_dynamic_avoid(sp_dict, G, raw_tasks, min_ratio=0.0):
    """动态绕开咽喉: 返回 (sp_dict, choke_edge, n_changed, ratio)。
    1) 按当前场景 OD 需求(加权 cargo)统计每条有向边的货运吞吐;
    2) 瓶颈边 = 吞吐最高的边; ratio = 该边吞吐 / 全场景总货运量;
    3) ratio < min_ratio 视为「不够拥挤」, 直接放弃改道(避免为微弱收益扰动已高分场景);
    4) 否则对该边所经 OD 用 Dijkstra(禁掉该边)重算; 不可达则保留原路径。"""
    od_qty = defaultdict(float)
    for t in raw_tasks:
        try:
            o = int(t.get("origin", t.get("o")))
            d = int(t.get("dest", t.get("d")))
            q = float(t.get("qty", 1) or 1)
        except Exception:
            continue
        od_qty[(o, d)] += q
    edge_load = defaultdict(float)
    for (o, d), q in od_qty.items():
        path = sp_dict.get((o, d))
        if not path:
            continue
        for i in range(len(path) - 1):
            edge_load[(int(path[i]), int(path[i + 1]))] += q
    if not edge_load:
        return sp_dict, None, 0, 0.0
    choke = max(edge_load, key=lambda e: edge_load[e])
    total = sum(od_qty.values()) or 1.0
    ratio = edge_load[choke] / total
    if ratio < min_ratio:
        return sp_dict, choke, 0, ratio
    n_changed = 0
    for (o, d), q in od_qty.items():
        path = sp_dict.get((o, d))
        if not path:
            continue
        if any((int(path[i]), int(path[i + 1])) == choke for i in range(len(path) - 1)):
            alt = _throat_dijkstra(G, o, d, forbid_edge=choke)
            if alt and len(alt) >= 2:
                sp_dict[(o, d)] = alt
                n_changed += 1
    return sp_dict, choke, n_changed, ratio


def _euler_cycle(sub_tasks):
    """对弱连通分量补最少空驶边使出入度平衡, 再 Hierholzer 求欧拉回路。"""
    edges = [(b["origin"], b["dest"]) for b in sub_tasks]
    if not edges:
        return None, 0
    outd, ind = defaultdict(int), defaultdict(int)
    nodes = set()
    for o, d in edges:
        outd[o] += 1
        ind[d] += 1
        nodes.add(o)
        nodes.add(d)
    sur, dfc = [], []
    for nd in sorted(nodes):
        diff = outd[nd] - ind[nd]
        if diff > 0:
            sur.append([nd, diff])
        elif diff < 0:
            dfc.append([nd, -diff])
    si = di = 0
    n_add = 0
    while si < len(sur) and di < len(dfc):
        take = min(sur[si][1], dfc[di][1])
        for _ in range(take):
            edges.append((dfc[di][0], sur[si][0]))
            n_add += 1
        sur[si][1] -= take
        dfc[di][1] -= take
        if sur[si][1] == 0:
            si += 1
        if dfc[di][1] == 0:
            di += 1
    adj = defaultdict(list)
    for ei, (o, d) in enumerate(edges):
        adj[o].append(ei)
    used = [False] * len(edges)
    stack = [edges[0][0]]
    circuit = []
    while stack:
        v_ = stack[-1]
        nxt = -1
        while adj[v_]:
            e = adj[v_][-1]
            if used[e]:
                adj[v_].pop()
            else:
                nxt = e
                break
        if nxt < 0:
            circuit.append(stack.pop())
        else:
            used[nxt] = True
            adj[v_].pop()
            stack.append(edges[nxt][1])
    circuit.reverse()
    if len(circuit) < 2 or not all(used):
        return None, 0
    cyc = circuit[:-1] if circuit[0] == circuit[-1] else circuit
    return (cyc if cyc else None), n_add


def ring_segment_plan(tasks, seg_len=2):
    """环序重建 + 切段并行: 弱连通分量内欧拉回路重建环序, 沿环每 seg_len 段切一组。"""
    if not tasks:
        return []
    _norm = []
    for t in tasks:
        if "origin" in t:
            _norm.append(t)
        else:
            _norm.append({"origin": t["o"], "dest": t["d"],
                          "qty": t.get("qty", 1), "ps": t.get("ps", 0),
                          "pe": t.get("pe", 0)})
    tasks = _norm
    adj_u = defaultdict(set)
    nodes = set()
    for t in tasks:
        o, d = t["origin"], t["dest"]
        adj_u[o].add(d)
        adj_u[d].add(o)
        nodes.add(o)
        nodes.add(d)
    seen, comps = set(), []
    for s in sorted(nodes):
        if s in seen:
            continue
        stack, c = [s], set()
        while stack:
            v_ = stack.pop()
            if v_ in c:
                continue
            c.add(v_)
            for w in adj_u[v_]:
                if w not in c:
                    stack.append(w)
        seen |= c
        comps.append(c)
    od2tasks = defaultdict(list)
    for t in tasks:
        od2tasks[(t["origin"], t["dest"])].append(t)
    groups = []
    for c in comps:
        sub = [t for t in tasks if t["origin"] in c]
        if not sub:
            continue
        cyc, n_add = _euler_cycle(sub)
        if not cyc:
            print("[ringseg] 分量 %s 成环失败, 退化单批组" % sorted(c), flush=True)
            groups.extend([[t] for t in sub])
            continue
        edge_batches = []
        for i in range(len(cyc)):
            o = cyc[i]
            d = cyc[(i + 1) % len(cyc)]
            if od2tasks.get((o, d)):
                edge_batches.append(od2tasks[(o, d)].pop(0))
        for i in range(0, len(edge_batches), seg_len):
            seg = edge_batches[i:i + seg_len]
            if seg:
                groups.append(seg)
    return groups


# ===================== 动态起点/终点(参数化起点终点, 卷无关) =====================
# 用户约定: Shortest path.py 的 target_id 书写顺序 = 起点 -> 终点 -> 装卸点。
# 起点 = 源码顺序第 1 个; 终点 = 源码顺序中「第一个装卸点之前」的连续节点块
# (装卸点 = 在当前场景 task.csv 中出现过的节点); 默认终点 = 最后一个终点。
# 这样换 C卷(单终点)无需改代码; 解析失败/无 task.csv 时回退 (EP_START, EP_END)
# (= 模块默认 82/191) 保持 v4 不变。所有回退统一引用模块级默认, 不重复硬编码字面量。
# 注意: target_id 是 set 字面量, ast.literal_eval 后会打乱顺序, 故必须按源码文本顺序解析。
def _parse_target_ids_source_order():
    """按 Shortest path.py 源码文本顺序解析 target_id 集合 -> [起点, 终点..., 装卸点...]。
    返回空列表表示解析失败。"""
    here = os.path.dirname(os.path.abspath(__file__))
    sp_src = os.path.join(here, "Shortest path.py")
    order = []
    try:
        with open(sp_src, "r", encoding="utf-8") as f:
            txt = f.read()
        m = re.search(r"target_id\s*=\s*\{([^}]*)\}", txt)
        if m:
            for tok in m.group(1).split(","):
                tok = tok.strip()
                if tok:
                    order.append(int(tok))
    except Exception:
        pass
    return order


def _resolve_endpoints(task_points, source_order=None):
    """由当前场景 task.csv 出现的节点反推 (起点, 终点)。
    task_points: set, 当前场景 task.csv 中出现过的所有节点(origin/dest 并集)。
    返回 (start, end)。解析失败/无装卸点出现 -> 回退 (EP_START, EP_END)(= 模块默认 82/191)。"""
    if source_order is None:
        source_order = _parse_target_ids_source_order()
    if not source_order:
        return (EP_START, EP_END)
    start = source_order[0]
    # 找到源码顺序中第一个在 task.csv 里出现的节点 = 第一个装卸点;
    # 其之前的连续节点块(不含起点)即为全部终点。
    first_handling_idx = None
    if task_points:
        for i in range(1, len(source_order)):
            if source_order[i] in task_points:
                first_handling_idx = i
                break
    if first_handling_idx is None:
        return (EP_START, EP_END)          # 没有装卸点出现 -> 异常场景, 回退
    ends = source_order[1:first_handling_idx]
    if not ends:
        return (EP_START, EP_END)          # 起点之后立刻就是装卸点(无终点?) -> 回退
    return (start, ends[-1])


def _sort_vehicle_tasks_by_deadline(vehicle_tasks, raw_tasks):
    """TIME_WINDOW_AWARE: 仅重排「每辆车自己的停靠顺序」为最早截止优先(EDF),
    不改派谁做哪批(覆盖量不变), 因此不会引入新未完成任务。
    目标: 让早截止批尽早完成 -> 减少 超时/未完成, 同时把提前加分往前推。
    仅在 TIME_WINDOW_AWARE=1 时调用。"""
    win = {}
    for rt in raw_tasks:
        k = (int(rt["origin"]), int(rt["dest"]))
        win[k] = min(win.get(k, 1 << 30), int(rt.get("en", 0) or 0))
    for v in range(len(vehicle_tasks)):
        seq = vehicle_tasks[v]
        if len(seq) < 4:
            continue
        pairs = [(seq[i], seq[i + 1]) for i in range(0, len(seq) - 1, 2)]
        pairs.sort(key=lambda od: win.get(od, 1 << 30))
        vehicle_tasks[v] = [x for p in pairs for x in p]


def run_baseline(update_plan_fn):
    # ==================== 静态输入 ====================
    input2 = pd.read_csv("Output/task.csv", encoding="gbk", engine="python")
    input2 = input2.dropna()
    input3 = pd.read_csv("vehicle.csv", encoding="gbk", engine="python")

    input4 = "vehicle_state.csv"
    input5 = "Output/operation_state.csv"
    input6 = "Output/id.csv"

    transit.init_output_files()

    vehicle_file = None
    operation_file = None
    id_file = None
    vehicle_data = []
    operation_data = []
    id_data = []

    vehicle_num = int(input3["数量"].iloc[0])

    # 解析任务
    raw_tasks = []
    _has_win = ("计划开始时刻" in input2.columns) and ("计划结束时刻" in input2.columns)
    for _, row in input2.iterrows():
        t = {
            "batch": row["批次"],
            "qty": int(row["数量"]),
            "origin": int(row["起点"]),
            "dest": int(row["终点"]),
            "st": 0, "en": 0,
        }
        if _has_win:
            try:
                h1, m1 = str(row["计划开始时刻"]).split(":"); h2, m2 = str(row["计划结束时刻"]).split(":")
                t["st"] = int(h1) * 60 + int(m1)
                t["en"] = int(h2) * 60 + int(m2)
            except Exception:
                t["st"] = t["en"] = 0
        raw_tasks.append(t)

    zone_roads = set()
    for rt in raw_tasks:
        zone_roads.add(rt["origin"])
        zone_roads.add(rt["dest"])

    # 算法变量
    vehicle_tasks = None
    vehicle_route = None
    plan_sent = None
    plan_idx = 0

    # 仿真结束检测
    last_ops_len = 0
    stale_iterations = 0
    SCORING_DONE = False

    while True:
        # ==================== 读动态输入 ====================
        vehicle_file = open_file_lazy(input4, vehicle_file)
        operation_file = open_file_lazy(input5, operation_file)
        id_file = open_file_lazy(input6, id_file)
        vehicle_file = read_csv_new_lines(vehicle_file, vehicle_data)
        operation_file = read_csv_new_lines(operation_file, operation_data)
        id_file = read_csv_new_lines(id_file, id_data)

        # 检测仿真结束
        current_ops_len = len(operation_data)
        if current_ops_len > last_ops_len:
            last_ops_len = current_ops_len
            stale_iterations = 0
        else:
            stale_iterations += 1
        _max_stale = int(os.environ.get("MAX_STALE", "600"))
        if not SCORING_DONE:
            if stale_iterations > _max_stale and current_ops_len > 0:
                # 不再本地算分: 评分一律由竞赛网页完成。
                print("\n[Baseline] 仿真结束, 产物已落盘, 退出(评分交网页)")
                SCORING_DONE = True
                import sys
                sys.stdout.flush()
                sys.exit(0)
            elif stale_iterations > 3600:
                print("\n[Baseline] 长时间无操作, 强制结束(产物已落盘, 评分交网页)")
                SCORING_DONE = True
                import sys
                sys.stdout.flush()
                sys.exit(0)

        # ==================== 1. 任务分配 (OD拓扑自适应, 纯确定性) ====================
        if vehicle_tasks is None:
            vehicle_tasks = [[] for _ in range(vehicle_num)]
            n_batches = len(raw_tasks)
            assign_mode = os.environ.get("ASSIGN_MODE", "auto")  # auto = OD拓扑自适应

            def build_groups():
                # 1) 完全反向的批次对 (a:o->d, b:d->o) -> 两段之间零空驶
                paired = [False] * n_batches
                grps = []
                for i in range(n_batches):
                    if paired[i]:
                        continue
                    oi, di = raw_tasks[i]["origin"], raw_tasks[i]["dest"]
                    for j in range(n_batches):
                        if j == i or paired[j]:
                            continue
                        if raw_tasks[j]["origin"] == di and raw_tasks[j]["dest"] == oi:
                            paired[i] = paired[j] = True
                            grps.append([raw_tasks[i], raw_tasks[j]])
                            break
                # 2) 剩余批次按 dest==origin 贪心串联(同样零空驶)
                rem = [raw_tasks[i] for i in range(n_batches) if not paired[i]]
                used = [False] * len(rem)
                for s in range(len(rem)):
                    if used[s]:
                        continue
                    chain = [rem[s]]
                    used[s] = True
                    changed = True
                    while changed:
                        changed = False
                        tail = chain[-1]["dest"]
                        for k in range(len(rem)):
                            if used[k]:
                                continue
                            if rem[k]["origin"] == tail:
                                chain.append(rem[k])
                                used[k] = True
                                changed = True
                                break
                    grps.append(chain)
                return grps

            def _exec_generic_groups(groups):
                G = len(groups)
                veh_per_group = max(1, vehicle_num // G)
                for g_idx, gb in enumerate(groups):
                    start_v = g_idx * veh_per_group
                    end_v = vehicle_num if g_idx == G - 1 else start_v + veh_per_group
                    n_veh = end_v - start_v
                    if n_veh <= 0:
                        continue
                    for b in gb:
                        base = b["qty"] // n_veh
                        rem = b["qty"] % n_veh
                        for v in range(start_v, end_v):
                            cnt = base + (1 if (v - start_v) < rem else 0)
                            for _ in range(cnt):
                                vehicle_tasks[v].extend([b["origin"], b["dest"]])

            def _exec_segment_groups(groups):
                # ringseg: 每分段(2-链, 首尾相接零空驶) 组内前半正向、后半反向
                G = len(groups)
                if G == 0:
                    return
                veh_per_group = max(1, vehicle_num // G)
                for g_idx, seg in enumerate(groups):
                    start_v = g_idx * veh_per_group
                    end_v = vehicle_num if g_idx == G - 1 else start_v + veh_per_group
                    n_veh = end_v - start_v
                    if n_veh <= 0:
                        continue
                    mid = n_veh // 2
                    fwd = seg
                    bwd = list(reversed(seg))
                    for pos, v in enumerate(range(start_v, end_v)):
                        seq = fwd if pos < mid else bwd
                        for b in seq:
                            vehicle_tasks[v].extend([b["origin"], b["dest"]])

            def _exec_spread():
                # 拉丁方轮转: 第 t 轮车 v 去做批 (v+t)%nb (链式OD首尾相接零空驶)
                V = vehicle_num
                nb = n_batches
                _out = defaultdict(list)
                _ind, _outd = defaultdict(int), defaultdict(int)
                for _i, _b in enumerate(raw_tasks):
                    _out[_b["origin"]].append(_i)
                    _outd[_b["origin"]] += 1
                    _ind[_b["dest"]] += 1
                _start = None
                for _nd in list(_outd.keys()):
                    if _outd[_nd] - _ind[_nd] == 1:
                        _start = _nd
                        break
                if _start is None:
                    _start = raw_tasks[0]["origin"]
                _used = [False] * nb
                _stack = [_start]
                _estack, _path = [], []
                while _stack:
                    _v = _stack[-1]
                    _nxt = None
                    while _out[_v]:
                        _c = _out[_v].pop()
                        if not _used[_c]:
                            _nxt = _c
                            break
                    if _nxt is None:
                        _stack.pop()
                        if _estack:
                            _path.append(_estack.pop())
                    else:
                        _used[_nxt] = True
                        _estack.append(_nxt)
                        _stack.append(raw_tasks[_nxt]["dest"])
                _path.reverse()
                for _i in range(nb):
                    if not _used[_i]:
                        _path.append(_i)
                border = _path if len(_path) == nb else list(range(nb))
                need = [min(b["qty"], V) for b in raw_tasks]
                assigned = [set() for _ in range(nb)]
                remaining = sum(need)
                for t in range(nb):
                    if remaining <= 0:
                        break
                    for v in range(V):
                        if remaining <= 0:
                            break
                        start_bi = (v + t) % nb
                        for k in range(nb):
                            cand = border[(start_bi + k) % nb]
                            if len(assigned[cand]) < need[cand] and v not in assigned[cand]:
                                assigned[cand].add(v)
                                b = raw_tasks[cand]
                                vehicle_tasks[v].extend([b["origin"], b["dest"]])
                                remaining -= 1
                                break

            # ---- OD 拓扑自适应选路 ----
            if assign_mode == "auto":
                try:
                    assign_mode = choose_topo_mode(raw_tasks, vehicle_num)
                except Exception as _e:
                    print("[topo] od_classify 失败, 回退 generic: %s" % _e, flush=True)
                    assign_mode = "generic"
            print("[topo] 选路=%s (%d批/%d车)" % (assign_mode, n_batches, vehicle_num), flush=True)

            if assign_mode == "ringseg":
                groups = ring_segment_plan(raw_tasks)
                _exec_segment_groups(groups)
            elif assign_mode == "optimized":
                groups = [raw_tasks]
                _exec_spread()
            elif assign_mode == "orig8" and n_batches >= 8:
                groups = [[raw_tasks[0], raw_tasks[4]], [raw_tasks[1], raw_tasks[5]],
                          [raw_tasks[2], raw_tasks[6]], [raw_tasks[3], raw_tasks[7]]]
                for bi in range(8, n_batches):
                    groups.append([raw_tasks[bi]])
                _exec_generic_groups(groups)
            else:
                groups = build_groups()
                _exec_generic_groups(groups)

            # 分组返回空 -> 回退 generic (保证每批都有车做)
            if not groups:
                print("[topo] 模式 %s 返回空组, 回退 generic" % assign_mode, flush=True)
                groups = build_groups()
                _exec_generic_groups(groups)

            # 分组数超过车辆数时退化为全车平分(保证每批都有车做)
            if len(groups) > vehicle_num:
                groups = [raw_tasks]
                _exec_generic_groups(groups)

            # ---- 时间窗感知重排(可选, TIME_WINDOW_AWARE 触发, 默认关) ----
            # 仅重排每辆车内部停靠顺序为最早截止优先, 不改派车覆盖; 失败关闭也不影响 v4。
            if os.environ.get("TIME_WINDOW_AWARE"):
                try:
                    _sort_vehicle_tasks_by_deadline(vehicle_tasks, raw_tasks)
                    print("[time-window] 已按截止时间重排每车停靠顺序(EDF)", flush=True)
                except Exception as _e:
                    print("[time-window] 重排失败, 跳过: %s" % _e, flush=True)

            batch_pairs = groups  # 兼容下游 len(batch_pairs)
            G = len(groups)
            veh_per_group = max(1, vehicle_num // G)

            # 参数化起点/终点: 按当前场景 task.csv 反推, 卷无关(换 C卷单终点不用改代码)
            GLOBAL_START, GLOBAL_END = _resolve_endpoints(zone_roads)
            global EP_START, EP_END
            EP_START, EP_END = GLOBAL_START, GLOBAL_END
            print("[endpoints] start=%s end=%s (scene points=%s)"
                  % (GLOBAL_START, GLOBAL_END, sorted(zone_roads)), flush=True)
            for v in range(vehicle_num):
                vehicle_tasks[v] = [GLOBAL_START] + vehicle_tasks[v] + [GLOBAL_END]

        # ==================== 2. 路径规划 ====================
        if vehicle_route is None:
            shortest_path = pd.read_csv("Shortest path.csv")
            sp_dict = {}
            _graph = defaultdict(list)
            for _, row in shortest_path.iterrows():
                od = ast.literal_eval(row.iloc[0])
                path = ast.literal_eval(row.iloc[1])
                u, v = int(od[0]), int(od[1])
                sp_dict[(u, v)] = path
                for i in range(len(path) - 1):
                    a, b = int(path[i]), int(path[i + 1])
                    _graph[a].append((b, 1))

            # ---- 动态绕开咽喉道(可选, AVOID_THROAT 触发) ----
            # 旧版仅硬编码 B67 的两条 OD; 现改为: 按当前场景 OD 需求从全路网图自动定位
            # 瓶颈边(货运吞吐最高), 禁掉该边后用 Dijkstra 重算受影响 OD 的最短路径。
            # 默认不触发, v4 行为完全不变。
            if _throat_enabled():
                _mr = float(os.environ.get("THROAT_MIN_RATIO", "0") or 0)
                sp_dict, _choke, _n, _r = _throat_dynamic_avoid(
                    sp_dict, _graph, raw_tasks, min_ratio=_mr)
                print("[avoid-throat] choke=%s load=%.1f%% rerouted_ODs=%d (min_ratio=%.2f)"
                      % (_choke, _r * 100, _n, _mr), flush=True)

            vehicle_route = []
            for tasks in vehicle_tasks:
                full_route = []
                for i in range(len(tasks) - 1):
                    s, e = tasks[i], tasks[i + 1]
                    if s == e:
                        continue  # 连续相同节点跳过
                    path = sp_dict[(s, e)]
                    if i == 0:
                        full_route.extend(path)
                    else:
                        full_route.extend(path[1:])
                vehicle_route.append(full_route)

        # ==================== 3. 生成运输计划 ====================
        new_plan = []

        BASE_INTERVAL = 15

        # 初始化动态路径 (首次运行时从vehicle_route复制)
        if not hasattr(run_baseline, 'dynamic_routes'):
            run_baseline.dynamic_routes = [list(r) for r in vehicle_route]

        n_groups = len(batch_pairs)
        veh_per_group = vehicle_num // n_groups
        STAGGER_V = os.environ.get("ASSIGN_STAGGER")  # 可选: 按全局车序均匀铺开(秒/车), 缓解咽喉桥拥堵
        for v in range(vehicle_num):
            within_group = v % veh_per_group
            if STAGGER_V:
                # 错峰发车: 全局车序线性铺开, 避免多车同时挤上咽喉桥
                send_t = 5 + v * int(STAGGER_V)
            else:
                send_t = 5 + within_group * BASE_INTERVAL

            route = run_baseline.dynamic_routes[v] if v < len(run_baseline.dynamic_routes) else []
            speed_val = None
            lane_cmd = 2 if v % 2 == 0 else 1

            vehicle_plan = {
                "send_time": send_t,
                "roadId": route[0] if route else EP_START,
                "state": 0,
                "id": None,
                "routing": None,
                "_current_idx": 0,
                "routing_link_ids": route if route else [EP_START, EP_END],
                "lane_cmd": lane_cmd,
                "speed_value": speed_val,
            }
            new_plan.append(vehicle_plan)

        if plan_sent is None:
            update_plan_fn(new_plan)
            plan_sent = True
        else:
            plan_idx += 1
            # 每轮都更新plan，保持引擎持续运行
            # 每2秒更新车道+BFS绕路检测
            # [topo] 响应式绕路(Layer2)已移除: 纯确定性派单
            # 每轮都推plan，保持引擎活跃
            update_plan_fn(new_plan)

        time.sleep(0.1)
