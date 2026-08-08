import csv
import math
import heapq
from collections import defaultdict

# =========================
# 1. 参数
# =========================

LANE_CSV = "车道.csv"
LANE_CONNECT_CSV = "车道连接.csv"

ENCODING = "gbk"
DELIMITER = ","

target_id = {82, 104, 191, 273, 279, 285, 291, 108, 122, 163, 136}

# =========================
# 2. 几何工具
# =========================

def parse_points(s):
    """
    解析:
    '(-302.871 -422.442) (-627.398 -422.216)'
    -> [(x1,y1),(x2,y2)]
    """
    pts = []
    for part in s.strip().split(")"):
        part = part.strip()
        if not part:
            continue
        part = part.replace("(", "")
        x, y = part.split()
        pts.append((float(x), float(y)))
    return pts


def polyline_length(points):
    length = 0.0
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        length += math.hypot(x2 - x1, y2 - y1)
    return length

# =========================
# 3. 读取路段长度（来自车道中心线）
# =========================

def load_segment_length(lane_csv):
    """
    一个路段有多条车道
    -> 取第一条车道的中心线长度作为路段长度
    """
    segment_len = {}

    with open(lane_csv, "r", encoding=ENCODING) as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        for row in reader:
            seg_id = int(row["路段ID"])

            if seg_id in segment_len:
                continue

            points = parse_points(row["中心点序列"])
            segment_len[seg_id] = polyline_length(points)

    return segment_len

# =========================
# 4. 读取连接段（边）
# =========================

def load_edges(connect_csv, valid_segments):
    graph = defaultdict(list)

    with open(connect_csv, "r", encoding=ENCODING) as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        for row in reader:
            u = int(row["起始路段ID"])
            v = int(row["目标路段ID"])

            if u not in valid_segments or v not in valid_segments:
                continue

            pts = parse_points(row["中心点序列"])
            edge_len = polyline_length(pts)

            graph[u].append((v, edge_len))

    return graph

# =========================
# 5. Dijkstra（节点+边长度）
# =========================

def dijkstra(graph, seg_len, start, end):
    pq = []
    heapq.heappush(pq, (seg_len[start], start, [start]))

    dist = {start: seg_len[start]}

    while pq:
        cost, u, path = heapq.heappop(pq)

        if u == end:
            return cost, path

        if cost > dist.get(u, float("inf")):
            continue

        for v, edge_len in graph.get(u, []):
            new_cost = cost + edge_len + seg_len[v]

            if new_cost < dist.get(v, float("inf")):
                dist[v] = new_cost
                heapq.heappush(pq, (new_cost, v, path + [v]))

    return None, None

# =========================
# 6. 构建目标路段两两最短路任务
# =========================

def build_target_pair_shortest_paths():
    # 1. 计算路段长度（节点权重）
    seg_len = load_segment_length(LANE_CSV)

    # 2. 构建路段级有向图（边权重）
    graph = load_edges(LANE_CONNECT_CSV, seg_len)

    # 3. 目标路段列表（固定顺序）
    targets = list(target_id)

    # 4. 存储最终任务结果
    tasks = []

    # 5. 目标两两最短路
    for i in range(len(targets)):
        for j in range(len(targets)):
            if i == j:
                continue

            s = targets[i]
            t = targets[j]

            if s not in seg_len or t not in seg_len:
                continue

            cost, path = dijkstra(graph, seg_len, s, t)

            if path is not None:
                tasks.append({
                    "任务": [s, t],
                    "最短路": path
                })

    # 6. 存成 CSV
    with open("Shortest path.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["任务", "最短路"])
        writer.writeheader()
        for row in tasks:
            writer.writerow({
                "任务": str(row["任务"]),
                "最短路": str(row["最短路"])
            })

    return tasks


# =========================
# 7. 运行（按你工程需要调用）
# =========================

if __name__ == "__main__":
    tasks = build_target_pair_shortest_paths()
    print(tasks)
