"""不可变的跑步预览快照、单次提交门闩及几何检查。"""
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from .coordinates import distance_m

PLAN_TTL_SECONDS = 600
# App 7.3.70 的顺序地图只有五组编号图标，不能生成越界序号。
SEQUENCE_POINT_LIMIT = 5


def prepare_checkpoint_order(points, policy):
    """仅为顺序模式准备本次路线的点位顺序，复制数据且不改通过状态。

    已有完整的零起始顺序按其排序；全部缺省时沿用本次途经点列表的
    规划顺序编号。部分缺失或冲突不能证明意图，拒绝猜测和覆盖。
    """
    if type(policy) is not int:
        raise ValueError("跑步策略不是整数，不能确定点位模式，请重新读取策略")
    if not isinstance(points, list) or any(not isinstance(point, dict) for point in points):
        raise ValueError("打卡点必须是对象列表，请重新读取点位")
    ordered = [dict(point) for point in points]
    if policy != 1:
        return ordered, {"source": "unchanged", "assigned": 0}
    if not 1 <= len(ordered) <= SEQUENCE_POINT_LIMIT:
        raise ValueError("顺序模式需要1至5个点位；当前数量无法对应App编号，停止生成")
    positions = [point.get("position") for point in ordered]
    unset = [position is None or (type(position) is int and position == 999)
             for position in positions]
    if all(unset):
        for index, point in enumerate(ordered):
            point["position"] = index
        return ordered, {"source": "route_order", "assigned": len(ordered)}
    if any(unset):
        raise ValueError("顺序模式的点位顺序部分缺失，不能覆盖已有顺序，请重新读取点位")
    if (any(type(position) is not int for position in positions)
            or sorted(positions) != list(range(len(ordered)))):
        raise ValueError("顺序模式的position必须从0起连续且不重复；异常顺序未改写")
    ordered.sort(key=lambda point: point["position"])
    return ordered, {"source": "source", "assigned": 0}


def validate_checkpoint_plan(data):
    """校验各模式的预览与包装一致性，并拒绝旧顺序999方案，不改冻结数据。"""
    points, policy = data.get("points"), data.get("policy")
    ordered, _ = prepare_checkpoint_order(points, policy)
    if policy == 1 and ordered != points:
        raise ValueError("顺序点位尚未按路线编号或排序，请重新生成并预览方案")
    try:
        wrapper = json.loads(data["five_point_json"])
        if (not isinstance(wrapper, dict) or wrapper.get("useZip") is not False
                or not isinstance(wrapper.get("fivePointJson"), str)):
            raise ValueError("不支持的点位包装")
        serialized = json.loads(wrapper["fivePointJson"])
        normalized, _ = prepare_checkpoint_order(serialized, policy)
        if serialized != normalized or serialized != points:
            raise ValueError("点位内容不一致")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("点位包装与预览不一致，请重新生成方案") from exc


def account_key(client):
    """用账号、学校和设备的摘要绑定方案，不在方案中保存登录令牌。"""
    session = client.session_data or {}
    text = "{}|{}|{}".format(client.uid(), session.get("unid", ""), client.identity.get("device_id", ""))
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class RunPlan:
    """保存序列化快照；每次读取返回副本，不能意外改掉待提交轨迹。"""
    json_text: str
    owner: str
    created_at: float = field(default_factory=time.time)
    _attempt: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)
    _lock: object = field(default_factory=threading.Lock, repr=False, compare=False)

    @classmethod
    def create(cls, client, data):
        """冻结完整轨迹、点位包装和策略参数，并拒绝 NaN。"""
        return cls(json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False), account_key(client))

    def data(self):
        """获取独立副本；GUI 的展示处理不会改变内部快照。"""
        return json.loads(self.json_text)

    @property
    def plan_id(self):
        """返回便于核对预览与提交一致性的内容摘要。"""
        return hashlib.sha256(self.json_text.encode()).hexdigest()[:12]

    @property
    def attempted(self):
        """标识本方案是否已进入提交请求阶段，包括结果不明的失败。"""
        return self._attempt.is_set()

    def validate(self, client):
        """拒绝不可提交、过期、换账号、重复及顺序点位不一致的方案。"""
        data = self.data()
        if data.get("preview_only"):
            raise ValueError("这是仅供测试的轨迹预览，没有学校策略，不允许提交")
        if account_key(client) != self.owner:
            raise ValueError("账号、学校或设备已变化，请重新生成方案")
        if not 0 <= time.time() - self.created_at <= PLAN_TTL_SECONDS:
            raise ValueError("方案已超过 10 分钟，请重新生成并检查")
        if self.attempted:
            raise ValueError("本方案已经尝试提交，请先查询记录，勿重复提交")
        validate_checkpoint_plan(data)

    def claim(self, client):
        """在发请求前原子占用方案，防止重复或并发提交。"""
        with self._lock:
            self.validate(client)
            self._attempt.set()


def checkpoint_distances(track, points):
    """计算轨迹采样点到打卡点的最近距离，仅作预览，不改写 isPass。"""
    locations = [(p["gLat"], p["gLng"]) for p in track["locations"] if p.get("type") != -1]
    return [round(min(distance_m((p["lat"], p["lon"]), loc) for loc in locations), 1)
            if locations else None for p in points]


def format_plan(plan):
    """展示冻结的时间、距离、点位顺序及道路指纹，不重新选路或生成。"""
    data = plan.data()
    track = data["track"]
    start = datetime.fromtimestamp(track["startTime"] / 1000)
    stop = datetime.fromtimestamp(track["startTime"] / 1000 + track["totalTime"])
    cadence = track["totalSteps"] * 60 / track["totalTime"]
    pace = track["totalTime"] * 1000 / track["totalDistance"]
    lines = [
        "方案 ID：" + plan.plan_id,
        "类型：" + ("仅轨迹预览，不可提交" if data.get("preview_only") else "在线生成方案"),
        "跑步策略：" + (str(data["policy"]) if data.get("policy") is not None else "未获取"),
        "路线来源：" + ("高德步行 API / 已校验的高德路线缓存" if data.get("route", {}).get("provider") == "amap_walking" else "未提供"),
        "开始：" + start.strftime("%Y-%m-%d %H:%M:%S"),
        "结束：" + stop.strftime("%Y-%m-%d %H:%M:%S"),
        "距离：{:.0f} m / 时长：{} s".format(track["totalDistance"], track["totalTime"]),
        "配速：{:.0f} 秒/km / 步频：{:.0f} 步/分钟 / 总步数：{}".format(pace, cadence, track["totalSteps"]),
        "轨迹采样：{} / 打卡点：{} / 种子：{}".format(len(track["locations"]), len(data["points"]), data["seed"]),
        "有效时间：" + data["window_reason"],
        "点位状态：本地模拟结果，服务端判定待提交后查询。",
        "底图与轨迹使用 GCJ-02；底图不参与提交。",
    ]
    order = data.get("checkpoint_order", {})
    if order.get("source") == "route_order":
        lines.append("点位顺序：按本次高德途经顺序补齐0至{}".format(len(data["points"]) - 1))
    elif order.get("source") == "source":
        lines.append("点位顺序：沿用源顺序，路线与上传一致")
    elif order.get("source") == "unchanged":
        lines.append("点位顺序：当前非顺序模式，保留源字段")
    evaluation = data.get("checkpoint_evaluation")
    if evaluation and evaluation.get("supported"):
        lines.append("本地顺序点：{}/{}；本次到点事件 {} 个".format(
            evaluation["passed_count"], len(data["points"]), len(evaluation["events"])))
    completion = data.get("completion")
    if completion:
        state = completion.get("complete")
        lines.append("本地完成条件：{}".format("满足" if state is True else "未满足" if state is False else "未知"))
    route = data.get("route", {})
    if "ring_length_m" in route:
        lines.append("完整环长：{} m / 已覆盖整圈：{}".format(route["ring_length_m"], route["complete_laps"]))
    if "road_fingerprint" in route:
        lines.append("道路指纹：{} / 分段候选：{}".format(route["road_fingerprint"],
                                                          "/".join(map(str, route["segment_candidates"]))))
        if route["candidate_combinations"] == 1:
            lines.append("道路选择：高德各段仅有一条有效道路，没有可切换的备选")
        else:
            lines.append("道路组合：{} / {}（组合上限；不同组合也可能共用部分道路）".format(
                route["selected_variant"], route["candidate_combinations"]))
    coordinates = data.get("coordinate_report")
    if coordinates:
        lines.append("坐标来源：原生高德 {native_gcj} / 百度转换 {converted_bd}".format(**coordinates))
        lines.append("源双坐标差异：最大 {max_delta_m} m / 超过 5m 的点 {conflicts} 个".format(**coordinates))
        if coordinates["conflicts"]:
            lines.append("坐标不一致：已统一采用原生高德坐标；请先核对点位所在位置。")
    if data.get("preview_only"):
        stamp = data.get("points_cached_at")
        cached_at = datetime.fromtimestamp(stamp / 1000).strftime("%Y-%m-%d %H:%M:%S") if isinstance(stamp, (int, float)) else "未知"
        lines.append("缓存点位时间：{}（可能已过期，仅作路线预览）".format(cached_at))
    return "\n".join(lines)
