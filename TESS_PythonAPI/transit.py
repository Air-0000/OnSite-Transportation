import csv
import os
import threading
import Baseline
from threading import Lock

_WRITTEN_IDS = set()
VEHICLE_STATE_FILE = "vehicle_state.csv"
OPERATION_STATE_FILE = "Output/operation_state.csv"
_penalty_file_path = os.path.join(os.path.dirname(__file__), "Output/penalty.csv")
_PENALTY_FIELDS = ["butt", "conflict"]

_baseline_started = False
current_plan = None
_plan_lock = Lock()


def init_output_files():
    global _WRITTEN_IDS
    _WRITTEN_IDS.clear()

    files = [
        "Output/id.csv",
        VEHICLE_STATE_FILE,
        OPERATION_STATE_FILE,
        _penalty_file_path
    ]

    for f in files:
        if os.path.exists(f):
            # 删除再重建，确保后续写入表头
            try:
                os.remove(f)
            except PermissionError:
                # 有文件锁时 truncate
                open(f, "w").close()


def write_id_record(id_value):
    """
    平台获取到真实车辆 id 后调用。
    文件第一列为 id，追加一行。
    一辆车只写一次。
    """

    global _WRITTEN_IDS

    if id_value in _WRITTEN_IDS:
        return

    _WRITTEN_IDS.add(id_value)

    filename = "Output/id.csv"
    file_exists = os.path.exists(filename)

    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(["id"])

        writer.writerow([id_value])

def write_vehicle_state(vehicle_id, vehicle_type, x, y, road_id, lane_id, speed_ms, angle_deg, dist_to_start, simu_time):
    header = ["vehicle_id", "vehicle_type", "x", "y", "road_id", "lane_id",
              "speed_ms", "angle_deg", "dist_to_start", "simu_time"]

    file_exists = os.path.isfile(VEHICLE_STATE_FILE)
    with open(VEHICLE_STATE_FILE, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "vehicle_id": vehicle_id,
            "vehicle_type": vehicle_type,
            "x": x,
            "y": y,
            "road_id": road_id,
            "lane_id": lane_id,
            "speed_ms": speed_ms,
            "angle_deg": angle_deg,
            "dist_to_start": dist_to_start,
            "simu_time": simu_time / 1000.0
        })
        f.flush()

def write_operation_state(vehicle_id, road_id, state, wait_ms, end_time, simu_time):
    """
    state: 1 表示作业开始，0 表示作业结束
    wait_ms: 等待时间（秒）
    end_time: 结束时间（秒）
    simu_time: 当前仿真时间（秒）
    """
    header = ["vehicle_id", "road_id", "state", "simu_time", "wait_s", "end_s"]

    file_exists = os.path.isfile(OPERATION_STATE_FILE)
    with open(OPERATION_STATE_FILE, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "vehicle_id": vehicle_id,
            "road_id": road_id,
            "state": state,
            "simu_time": simu_time / 1000.0,
            "wait_s": wait_ms / 1000.0,
            "end_s": end_time / 1000.0
        })
        f.flush()

def write_penalty_record(record_dict):

    file_exists = os.path.isfile(_penalty_file_path)

    with open(_penalty_file_path, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_PENALTY_FIELDS)

        if not file_exists:
            writer.writeheader()

        row = {col: "" for col in _PENALTY_FIELDS}

        for k, v in record_dict.items():
            if k in row:
                row[k] = v

        writer.writerow(row)

def _start_baseline_thread():
    global _baseline_started
    if _baseline_started:
        return

    def _guarded(fn):
        """给 run_baseline 套一层崩溃留痕。

        【v2_v1 教训】run_baseline 跑在 daemon 线程里, 一旦抛异常, Python 只会
        把 traceback 丢进子进程 stdout(通常没人接), 主进程照常空转到外层
        看门狗 900s 强杀 —— 表现为"跑了 40 分钟、零心跳、零产物", 极难定位。
        (2026-08-02 00:07 B1/B2 全灭, 真因是 parse_time 不在作用域的 NameError。)
        这里统一把 traceback 写进 exit_reason.txt, 崩溃立刻可见。
        """
        import os as _os
        import traceback as _tb
        _f = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                           "exit_reason.txt")
        try:
            fn(update_current_plan)
        except BaseException:
            try:
                with open(_f, "a", encoding="utf-8") as _fh:
                    _fh.write("!!! run_baseline 线程崩溃 !!!\n")
                    _fh.write(_tb.format_exc())
                    _fh.write("\n")
            except Exception:
                pass
            raise

    t = threading.Thread(
        target=_guarded,
        args=(Baseline.run_baseline,),
        daemon=True
    )
    t.start()
    _baseline_started = True

def get_player_vehicle_plan():
    global current_plan
    _start_baseline_thread()
    with _plan_lock:
        plan_to_return = current_plan or []
        return plan_to_return

def update_current_plan(new_plan):
    global current_plan
    with _plan_lock:
        current_plan = new_plan
