"""只读检查详情或 OBS 中的打卡点，不生成或修改打卡完成证明。"""
import base64
import gzip
import io
import json
from pathlib import Path
from .coordinates import checkpoint_coordinates, coordinate_pair, CONFLICT_METERS

MAX_BYTES = 8 * 1024 * 1024
POINT_KEYS = ("fivePointJson", "pointsResModels")
WRAPPER_KEYS = ("data", "record", "runningRecord", "runData",
                "fixed_point_json", "fixedPointJson")
RULE_LABELS = {1: "距离", 7: "时长", 9: "按顺序通过所有点位",
               11: "步频", 12: "配速", 18: "人脸验证"}


def decode_value(value):
    """解开有大小限制的 JSON 或 Base64+Gzip，兼容 OBS 字段编码。"""
    for _ in range(5):
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return None
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise ValueError("字段超过 8 MiB，停止解析")
        if text.startswith(("{", "[", '"')):
            value = json.loads(text)
            continue
        raw = base64.b64decode(text, validate=True)
        if not raw.startswith(b"\x1f\x8b"):
            raise ValueError("不是 JSON 或 Gzip 数据")
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("解压后超过 8 MiB，停止解析")
        value = raw.decode("utf-8")
    raise ValueError("字段嵌套层数过多")


def _valid_pair(lat, lng):
    """共用生成端的有限坐标和单轴占位校验，避免诊断结果不一致。"""
    return coordinate_pair(lat, lng) is not None


def analyze_checkpoints(document):
    """检查已知包装层，返回字段证据而非 App 的显示或达标结论。"""
    sources, warnings = [], []
    complete_values = set()
    render_contexts = []
    rules = []

    def visit(value, path, depth=0, point_list=False):
        """递归读取允许的字段，避免扫描或输出无关个人资料。"""
        if depth > 8:
            warnings.append(path + "：包装嵌套过深")
            return
        try:
            value = decode_value(value)
        except (ValueError, TypeError, OSError, EOFError, UnicodeError):
            warnings.append(path + "：数据无法解码")
            return
        if value is None:
            if point_list:
                sources.append({"path": path, "count": 0, "passed": 0,
                                "gcj_valid": 0, "bd_valid": 0})
            return
        if isinstance(value, list) and point_list:
            if len(value) > 5000:
                warnings.append(path + "：点位超过 5000 个，停止解析")
                return
            passed = gcj = bd = placeholders = conflicts = 0
            point_states = []
            max_delta = 0.0
            for index, item in enumerate(value):
                if not isinstance(item, dict):
                    warnings.append(path + "：列表含非对象项")
                    continue
                point_states.append({
                    "index": index,
                    "position": item.get("position") if type(item.get("position")) is int else None,
                    "is_pass": item.get("isPass") if isinstance(item.get("isPass"), bool) else None,
                })
                passed += item.get("isPass") is True
                gcj += _valid_pair(item.get("glat"), item.get("glon"))
                bd += _valid_pair(item.get("lat"), item.get("lon"))
                placeholders += item.get("position") == 999
                try:
                    _, _, _, delta = checkpoint_coordinates(item)
                    if delta is not None:
                        max_delta = max(max_delta, delta)
                        conflicts += delta > CONFLICT_METERS
                except ValueError:
                    pass
            sources.append({"path": path, "count": len(value),
                            "passed": passed, "gcj_valid": gcj, "bd_valid": bd,
                            "coordinate_conflicts": conflicts, "max_delta_m": round(max_delta, 2),
                            "point_states": point_states})
            if value and gcj < len(value):
                warnings.append(path + "：部分 glat/glon 缺失、越界或为占位坐标")
            if placeholders:
                warnings.append(path + "：存在 position=999，不能据此确认真实点位顺序")
            if conflicts:
                warnings.append(path + "：双坐标不一致 {} 个，最大差异 {:.2f}m；轨迹与点位可能使用了不同位置".format(conflicts, max_delta))
            return
        if not isinstance(value, dict):
            warnings.append(path + "：不是预期的对象或打卡点列表")
            return
        if isinstance(value.get("complete"), bool):
            complete_values.add(value["complete"])
        if "reasonList" in value:
            reason_list = value["reasonList"]
            if not isinstance(reason_list, list) or len(reason_list) > 5000:
                warnings.append(path + ".reasonList：不是有效的规则列表")
            else:
                for index, rule in enumerate(reason_list):
                    rule_path = "{}.reasonList[{}]".format(path, index)
                    if not isinstance(rule, dict):
                        warnings.append(rule_path + "：不是规则对象")
                        continue
                    rules.append({
                        "path": rule_path,
                        "type": rule.get("type") if type(rule.get("type")) is int else None,
                        "complete": rule.get("complete") if isinstance(rule.get("complete"), bool) else None,
                        "complete_status": rule.get("completeStatus") if type(rule.get("completeStatus")) is int else None,
                    })
        context = {key: value[key] for key in ("sportType", "policy")
                   if type(value.get(key)) is int}
        if context:
            render_contexts.append({"path": path, **context})
        for key in POINT_KEYS:
            if key in value:
                visit(value[key], path + "." + key, depth + 1, True)
        for key in WRAPPER_KEYS:
            if key in value:
                visit(value[key], path + "." + key, depth + 1)

    visit(document, "$", point_list=isinstance(document, list))
    complete = next(iter(complete_values)) if len(complete_values) == 1 else None
    if len(complete_values) > 1:
        warnings.append("不同包装层的 complete 状态冲突，结果记为未知")
    status = "present" if any(s["count"] for s in sources) else "empty" if sources else "missing"
    if warnings and status == "missing":
        status = "invalid"
    checkpoint_rules = [rule["complete"] for rule in rules if rule["type"] == 9]
    checkpoint_complete = (checkpoint_rules[0] if checkpoint_rules
                           and all(value is checkpoint_rules[0] for value in checkpoint_rules) else None)
    if checkpoint_rules and checkpoint_complete is None:
        warnings.append("顺序点位规则状态缺失或冲突，结果记为未知")
    if complete is True and checkpoint_complete is False:
        warnings.append("complete=true，但服务端顺序点位规则未通过；顶层完成状态不能代替逐项规则")
    return {"status": status, "sources": sources,
            "warnings": list(dict.fromkeys(warnings)), "complete": complete,
            "render_contexts": render_contexts, "rules": rules,
            "checkpoint_rule_complete": checkpoint_complete}


def _comparable_states(report):
    if report is None or report["status"] != "present":
        return None
    candidates = []
    for source in report["sources"]:
        states = source.get("point_states", [])
        positions = [state["position"] for state in states]
        if (len(states) != source["count"] or not states
                or any(position is None or position == 999 for position in positions)
                or len(set(positions)) != len(positions)
                or any(state["is_pass"] is None for state in states)):
            return None
        candidates.append(states)
    if not candidates or any(states != candidates[0] for states in candidates[1:]):
        return None
    return candidates[0]


def analyze_run_checkpoints(detail, submitted_point_wrapper=None, local_obs=None):
    """联合检查提交快照与服务端规则；本地 OBS 内容不等于远端验证结果。"""
    report = analyze_checkpoints(detail)
    submitted = (analyze_checkpoints({"fivePointJson": submitted_point_wrapper})
                 if submitted_point_wrapper is not None else None)
    obs = analyze_checkpoints(local_obs) if local_obs is not None else None
    reports = {"server_detail": report, "submitted": submitted, "local_obs": obs}
    comparisons = []
    for left, right in (("submitted", "local_obs"), ("server_detail", "submitted"),
                        ("server_detail", "local_obs")):
        left_states, right_states = _comparable_states(reports[left]), _comparable_states(reports[right])
        status = "unknown" if left_states is None or right_states is None else (
            "match" if left_states == right_states else "mismatch")
        comparisons.append({"left": left, "right": right, "status": status})
    report.update({"submitted": submitted, "local_obs": obs,
                   "point_state_comparisons": comparisons, "remote_obs_verified": False})
    return report


def format_report(report):
    """生成只含字段统计的中文报告，不回显账号、令牌和原始响应。"""
    labels = {"present": "找到点位字段（不代表 App 已显示）",
              "empty": "点位字段为空", "missing": "当前数据未包含点位字段",
              "invalid": "字段解析失败"}
    complete = report["complete"]
    lines = ["打卡点诊断：" + labels[report["status"]],
             "服务端 complete：" + ("未知" if complete is None else str(complete)), ""]
    for source in report["sources"]:
        lines.extend([source["path"],
                      "  点位 {count}，isPass=true {passed}，有效 glat/glon {gcj_valid}，有效 lat/lon {bd_valid}".format(**source)])
    for context in report.get("render_contexts", []):
        lines.append("显示上下文 {}：sportType={} / policy={}".format(
            context["path"], context.get("sportType", "未提供"), context.get("policy", "未提供")))
    for rule in report.get("rules", []):
        rule_label = RULE_LABELS.get(rule["type"], "规则 type={}".format(rule["type"]))
        state = "未知" if rule["complete"] is None else "通过" if rule["complete"] else "未通过"
        lines.append("服务端规则 {}：{}（completeStatus={}）".format(
            rule_label, state, rule["complete_status"]))
    evidence_labels = {"server_detail": "服务端详情", "submitted": "提交快照", "local_obs": "本地 OBS 对象"}
    for name in ("submitted", "local_obs"):
        evidence = report.get(name)
        if evidence is not None:
            lines.append("{}：{}".format(evidence_labels[name], labels[evidence["status"]]))
            for source in evidence["sources"]:
                lines.append("  {}：点位 {}，isPass=true {}".format(
                    source["path"], source["count"], source["passed"]))
            lines.extend("注意（{}）：{}".format(evidence_labels[name], warning)
                         for warning in evidence["warnings"])
    for comparison in report.get("point_state_comparisons", []):
        state = {"match": "一致", "mismatch": "不一致", "unknown": "证据不足，无法比较"}[comparison["status"]]
        lines.append("{} / {} 点位顺序及通过状态：{}".format(
            evidence_labels[comparison["left"]], evidence_labels[comparison["right"]], state))
    if "remote_obs_verified" in report:
        lines.append("本地 OBS 对象仅代表准备上传的内容；未下载验证远端对象，字段一致不代表服务端规则通过。")
    lines.extend("注意：" + text for text in report["warnings"])
    lines.extend(["", "轨迹坐标、打卡点字段、服务端达标状态是不同的数据。",
                  "详情可能仅返回摘要；缺少字段不能证明 OBS 或 App 中也没有。",
                  "本诊断不请求对象下载地址，也不修改或补造打卡信息。"])
    return "\n".join(lines)


def inspect_file(filename):
    """只读打开用户主动选择的 JSON 文件，并限制内存占用。"""
    with Path(filename).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("文件超过 8 MiB")
    return analyze_checkpoints(json.loads(raw.decode("utf-8-sig")))
