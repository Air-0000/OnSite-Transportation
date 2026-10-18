# -*- coding: utf-8 -*-
"""OD 拓扑分类通用模块 —— 输入任意 task.csv，输出 (串行度, 反配度) 2D 分类
================================================================
为什么需要: B 卷 56 题 mixed 无法用"批次数"判断选哪种派单算法(已证伪:
            同一批次数下 OD 连接方式不同、胜负相反)。C 卷没有答案可抄，
            必须把判断逻辑写成通用函数 —— 拿到任意 task.csv 就能自动分类、
            自动推荐算法。

两个连续轴(0~1):
  seriality  串行度   = 最大弱连通分量批数 / 总批数
                chain ≈ 1 (全部批连成一条链)   cycles ≈ 小 (多组独立短环)
  pairibility 反配度   = 反向配对批数 / 总批数
                cycles ≈ 1 (每批都有反向配对, 零空驶循环)
                chain  ≈ 0 (无反配可能, 只能单向推进)

分类判定(与 B 卷 80/80 实证结论一致的规则, 4 类互斥):
  chain  : seriality == 1 且 pairibility == 0 且【有1源1汇】 -> optimized(拉丁方跨批并行)
  ring   : seriality == 1 且 pairibility == 0 且【无源无汇(纯环)】 -> ring(v6欧拉环重建)
  pair   : pairibility == 1                         -> generic / manybatch(反向配对短组)
  mixed  : 其余                                     -> 按两轴细分:
              近配对 (pairibility > 0.5)            -> generic/manybatch 候选
              近链   (seriality > 0.5)              -> optimized 候选
              其余中段                              -> 需代表题实测

【v14 修正】ring 用 v6 ring 而非 orig8:
  orig8 硬编码下标 (0,4)(1,5)(2,6)(3,7) 只在 task.csv 行序恰为"间隔环序"时成立:
  B5/B33(间隔行序) 4组全首尾相接(基线 3164/1949) / B61-64(连续行序) 4组全断链
  (基线 1199/1083/1592, B36 仅 91 分) —— 同是 ring 结构基线分差 40 倍, 纯属行序运气。
  v6 ring_cycles() 按弱连通分量重建环、每分量独立成环, 任意行序都能成环 -> 通用。
  ⚠️ v6 ring 官方分从未验证(记忆 2026-08-01:757 ❌), 需 B5/B61 各跑 ring 验证。

【v11 修正】链 vs 环的区分:
  seriality=1 且 pair=0 的题曾一律推荐 optimized, 但 B5 官方分实证推翻:
  B5 的 OD 是 8 节点大环(273→122→279→163→285→136→291→108→273,
  每节点入==出==1, 无源无汇), 基线 orig8 的 (0,4)(1,5)(2,6)(3,7) 恰好把
  环切成 4 段 2-链零空驶循环 -> 基线拿 3163 分; optimized 拉丁方不利用环
  即便跑满也难赢(B5 不完整 optimized 官方分 1805 < 基线 3163)。
  => 环必须推荐 ring/沿环分组, 不能走 optimized。

【v12 命名修正】cycle→ring、cycles→pair:
  原 "cycle"(环) 与 "cycles"(反向配对) 拼写仅差 s, 极易混淆。
  现统一: chain=链 / ring=环 / pair=配对 / mixed=混合, 语义互斥。

建议算法还需叠加【车队规模】约束(实测):
  >=18车: optimized 死锁禁区 -> 需限流/入口治理; 14车: 无此问题。

用法:
    import od_classify
    r = od_classify.classify_tasks("xxx/task.csv")   # 路径
    r = od_classify.classify_tasks([{...}, ...])      # 已解析任务 dict 列表
    r -> dict(nb, seriality, pairibility, cat, rec_mode, max_comp, rev, single_chain)
"""
import csv
import os
from collections import defaultdict


def _open(p):
    for enc in ("utf-8-sig", "gbk", "latin-1"):
        try:
            f = open(p, "r", encoding=enc)
            f.read(4096)
            f.seek(0)
            return f
        except Exception:
            pass
    return open(p, "r", encoding="latin-1")


def _parse_time(t):
    t = str(t).strip()
    if ":" in t:
        p = t.split(":")
        return int(p[0]) * 3600 + int(p[1]) * 60
    try:
        return float(t)
    except Exception:
        return 0.0


def load_tasks(path):
    """读 task.csv -> [{o, d, qty, ps, pe}]，忽略空行/表头。"""
    out = []
    if isinstance(path, (list, tuple)):
        return path
    if not os.path.exists(path):
        return out
    with _open(path) as f:
        for r in csv.DictReader(f):
            if not (r.get("批次") or r.get("batch") or "").strip():
                continue
            try:
                out.append(dict(
                    o=str(r["起点"]).strip(), d=str(r["终点"]).strip(),
                    qty=int(float(r["数量"])),
                    ps=_parse_time(r.get("计划开始时刻") or r.get("计划开始") or "0"),
                    pe=_parse_time(r.get("计划结束时刻") or r.get("计划结束") or "0"),
                ))
            except Exception:
                continue
    return out


def _scc_kosaraju(edges):
    """Kosaraju 强连通分量分解: 返回 (环分量列表[每环节点数], 全部节点)。
    图论完备: 任意有向图 = 弱连通分量 × (强连通环 SCC | 有向无环 DAG | 孤立点)。"""
    g = defaultdict(list)
    gr = defaultdict(list)
    nodes = set()
    for e in edges:
        g[e["o"]].append(e["d"])
        gr[e["d"]].append(e["o"])
        nodes.add(e["o"])
        nodes.add(e["d"])
    order = []
    vis = set()

    def dfs(x):
        vis.add(x)
        for y in g[x]:
            if y not in vis:
                dfs(y)
        order.append(x)

    for nd in nodes:
        if nd not in vis:
            dfs(nd)
    comps = []
    vis2 = set()

    def rdfs(x, c):
        vis2.add(x)
        c.append(x)
        for y in gr[x]:
            if y not in vis2:
                rdfs(y, c)

    for nd in reversed(order):
        if nd not in vis2:
            c = []
            rdfs(nd, c)
            comps.append(c)
    return comps, nodes


def structure_signature(tasks):
    """SCC 完备结构签名: 返回 dict(comp_str, scc_rings, dag_src, dag_snk, n_comp)。
    comp_str 示例: '环r8' / '环r2 | 环r2 | 环r4' / 'DAG(1源1汇)' /
                   '环r2,r2 | 环r2 | DAG(1源1汇)'  —— 任意 C 卷 task.csv 均可生成。
    """
    edges = load_tasks(tasks)
    n = len(edges)
    if n == 0:
        return dict(comp_str="", scc_rings=[], dag_src=0, dag_snk=0, n_comp=0)
    # 弱连通分量(按节点)
    adj = defaultdict(list)
    for e in edges:
        adj[e["o"]].append(e["d"])
        adj[e["d"]].append(e["o"])
    visited = set()
    wcomps = []
    for node in adj:
        if node in visited:
            continue
        st = [node]
        c = set()
        while st:
            x = st.pop()
            if x in visited:
                continue
            visited.add(x)
            c.add(x)
            for y in adj[x]:
                if y not in visited:
                    st.append(y)
        wcomps.append(c)
    sigs = []
    for wc in wcomps:
        sub = [e for e in edges if e["o"] in wc or e["d"] in wc]
        sccs, nodes = _scc_kosaraju(sub)
        rings = sorted([len(c) for c in sccs if len(c) >= 2])
        in_ring = set()
        for c in sccs:
            if len(c) >= 2:
                in_ring.update(c)
        dag = nodes - in_ring
        ind = defaultdict(int)
        outd = defaultdict(int)
        for e in sub:
            outd[e["o"]] += 1
            ind[e["d"]] += 1
        src = len([x for x in dag if ind[x] == 0 and outd[x] > 0])
        snk = len([x for x in dag if outd[x] == 0 and ind[x] > 0])
        if rings and not dag:
            sigs.append("环%s" % (",".join("r%d" % r for r in rings)))
        elif rings and dag:
            sigs.append("环%s+DAG(%d源%d汇)" % (",".join("r%d" % r for r in rings), src, snk))
        elif dag:
            sigs.append("DAG(%d源%d汇)" % (src, snk))
        else:
            sigs.append("孤立")
    return dict(comp_str=" | ".join(sorted(sigs)), scc_rings=[],
                dag_src=0, dag_snk=0, n_comp=len(wcomps))


def classify_tasks(tasks):
    """核心分类函数。tasks 可为路径或已解析列表。
    返回 dict: nb, seriality, pairibility, max_comp, rev, single_chain,
               pure_ring, cat, rec_mode, signature, detail
    """
    edges = load_tasks(tasks)
    n = len(edges)
    if n == 0:
        return dict(nb=0, seriality=0.0, pairibility=0.0, max_comp=0, rev=0,
                    single_chain=False, pure_ring=False, cat="empty",
                    rec_mode="generic", signature="", detail="无任务")

    # --- 反配度 pairibility: 统计反向配对批数 (i<->j: o_i==d_j 且 d_i==o_j)
    rev = 0
    seen = set()
    for i in range(n):
        for j in range(i + 1, n):
            if edges[i]["o"] == edges[j]["d"] and edges[i]["d"] == edges[j]["o"]:
                rev += 2
    pairibility = rev / float(n) if n else 0.0

    # --- 串行度 seriality: 弱连通分量里最大的那个包含多少批
    adj = defaultdict(list)          # node -> neighbors (无向)
    for e in edges:
        adj[e["o"]].append(e["d"])
        adj[e["d"]].append(e["o"])
    visited = set()
    comps = []
    for node in adj:
        if node in visited:
            continue
        stack = [node]
        comp = set()
        while stack:
            x = stack.pop()
            if x in visited:
                continue
            visited.add(x)
            comp.add(x)
            for y in adj[x]:
                if y not in visited:
                    stack.append(y)
        cb = [i for i, e in enumerate(edges) if e["o"] in comp or e["d"] in comp]
        comps.append(cb)
    max_comp = max((len(c) for c in comps), default=0)
    seriality = max_comp / float(n) if n else 0.0

    # --- 单链判定: 单连通分量 + 1源(入0)1汇(出0) + 中间节点入==出
    single_chain = False
    pure_ring = False
    if len(comps) == 1 and max_comp == n and n >= 2:
        ind = defaultdict(int)
        outd = defaultdict(int)
        nodes = set()
        for e in edges:
            outd[e["o"]] += 1
            ind[e["d"]] += 1
            nodes.add(e["o"])
            nodes.add(e["d"])
        src = sum(1 for nd in nodes if ind[nd] == 0)
        snk = sum(1 for nd in nodes if outd[nd] == 0)
        balanced_mid = sum(1 for nd in nodes if ind[nd] == outd[nd])
        single_chain = (src == 1 and snk == 1 and balanced_mid == len(nodes) - 2)
        # 【v11 修正】环(ring)判定: 单连通分量 + 无源无汇(每个节点入==出) -> 纯环
        # 例 B5: 273→122→279→163→285→136→291→108→273 (8节点大环, 无源无汇)
        # 环的正确策略是沿环循环/分组配对(orig8 类), 不是 optimized 拉丁方!
        # (B5 基线 orig8 拿 3163 分实证: (0,4)(1,5)(2,6)(3,7) 恰好把环切成4段2链零空驶)
        pure_ring = (src == 0 and snk == 0 and balanced_mid == len(nodes)
                     and len(nodes) >= 2)

    # --- 分类 + 推荐算法 (v13: SCC 签名 + 反配度, 判定顺序不可调换)
    #    chain 链: DAG 单分量 1源1汇        -> optimized(拉丁方跨批并行)
    #    ring  环: 单一大环且反配=0          -> orig8(沿环分组, B5 实证3163分)
    #    ringpair: 单一大环但反配>0          -> optimized(B17/B21 实测翻正)
    #    pair  配对: 完美反向配对(反配度=1)   -> generic(短组零空驶)
    #    mixed 混合: 其余                    -> 按 2D 轴细分
    sig = structure_signature(edges)
    sig_str = sig["comp_str"]
    # SCC 口径: 单一大环 = 签名恰为 '环r8'(或单个 rN), 由 SCC 分解保证
    is_single_big_ring = (sig_str.startswith("环r") and "|" not in sig_str
                          and "DAG" not in sig_str and "孤立" not in sig_str
                          and sig_str.count(",") == 0)
    if single_chain:
        cat = "chain"
        rec_mode = "optimized"
    elif is_single_big_ring:
        # 单一大环: 按反配度分两种行为(官方分实证)
        if pairibility < 1e-9:
            cat = "ring"
            rec_mode = "ringseg"        # v14b: 纯环 -> 环序重建+切段并行(替代orig8硬编码下标与v6整车绕环)
            # 不用 orig8: 它硬编码下标(0,4)(1,5)(2,6)(3,7)只在"间隔行序"成立,
            # B61-64(连续行序)4组全断链, 基线分 91~1592 远低于 B5/B6(3164/3538)
            # v6 ring_cycles() 按弱连通分量重建环, 任意行序都能成环 -> 通用
        else:
            cat = "ringpair"            # 环+反向配对混合: B17/B21 optimized 翻正
            rec_mode = "optimized"
    elif pairibility >= 1.0 - 1e-9:
        cat = "pair"
        rec_mode = "generic"
    else:
        cat = "mixed"
        if pairibility > 0.5:
            rec_mode = "generic"        # 近配对: 可反配 -> generic/manybatch
        elif seriality > 0.5:
            rec_mode = "optimized"      # 近链: 高串行 -> 拉丁方
        else:
            rec_mode = "generic"        # 中段默认 generic, 需实测复核




    return dict(nb=n, seriality=seriality, pairibility=pairibility,
                max_comp=max_comp, rev=rev, single_chain=single_chain,
                pure_ring=pure_ring,
                cat=cat, rec_mode=rec_mode,
                signature=sig_str,
                detail="%d批 最大分量%d 反配%d [%s]" % (n, max_comp, rev, sig_str))


if __name__ == "__main__":
    import sys
    base = r"E:\Desktop\dev\OnSite-Transportation\Test Paper B\B"
    # 传 B 卷场景号: python od_classify.py 1 2 25
    sids = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else range(1, 81)
    print("%-5s %4s %9s %9s %-7s %-9s %-28s" %
          ("题", "批", "串行度", "反配度", "分类", "推荐", "detail"))
    from collections import Counter
    cc = Counter()
    for sid in sids:
        p = os.path.join(base, "B_B%d_input" % sid, "task.csv")
        r = classify_tasks(p)
        cc[r["cat"]] += 1
        print("B%-4d %4d %9.3f %9.3f %-7s %-9s %s" %
              (sid, r["nb"], r["seriality"], r["pairibility"],
               r["cat"], r["rec_mode"], r["detail"]))
    print("\n分类计数:", dict(cc))
