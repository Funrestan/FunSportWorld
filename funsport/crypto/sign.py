"""Android 提交签名。"""
from .envelope import md5_hex
from ..logger import dim

SALT = "2slhe02lsfiwowlcixisla_sls-_slaor"

UPLOAD_SIGN_FIELD_ORDER = [
    "sportType", "totalTime", "totalDis", "speed", "startTime", "stopTime",
    "complete", "selDistance", "unCompleteReason", "getPrize", "status",
    "uuid", "uid", "avgStepFreq", "totalSteps", "selectedUnid", "calorie",
    "policy", "selRunTime", "validDis", "validTime", "useMobilityTools",
    "errorCode", "geeToken", "unauthorized", "themeId", "faceCheck",
    "goalId", "address", "avgPower", "totalAscent",
]


def android_value(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return v
    return str(v)


def build_sign_map(values, has_room_id=False):
    m = []
    for k in UPLOAD_SIGN_FIELD_ORDER:
        if k in values:
            m.append((k, android_value(values[k])))
    if has_room_id and "roomId" in values:
        m.append(("roomId", android_value(values["roomId"])))
    return m


def join_query(m, ignore_case):
    items = list(m)
    if ignore_case:
        items.sort(key=lambda x: x[0].lower())
    else:
        items.sort(key=lambda x: x[0])
    return "&".join(f"{k}={v}" for k, v in items)


def original_sign(values, has_room_id=False) -> str:
    m = [(k, v) for k, v in build_sign_map(values, has_room_id) if k.lower() != "signature"]
    return join_query(m, False)


def signature(values, has_room_id=False) -> str:
    m = [(k, v) for k, v in build_sign_map(values, has_room_id) if k.lower() != "signature"]
    q = join_query(m, True)
    s = md5_hex((q + SALT).encode())
    dim(f"signature={s[:12]}…")
    return s


def md5_url_sign(url: str) -> str:
    http_url = url.replace("https://", "http://", 1)
    return md5_hex((http_url + SALT).encode())
