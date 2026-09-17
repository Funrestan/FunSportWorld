"""iOS/Android 请求头构造。"""
import json
import uuid

from .envelope import md5_hex, now_ms
from ..logger import dim

TOKEN_SIGN_SUFFIX = "2slhe02lsfiwowlcixisla_sls-_slaor"
IOS_APP_VERSION = "7.3.40"
ANDROID_APP_VERSION = "7.3.70"

UA_IOS = "SWCampus/7.3.40 (iPhone; iOS 18.1; Scale/3.00)"
UA_ANDROID = ("Mozilla/5.0 (Linux; Android 14; 22081212C Build/UKQ1.231003.002) "
              "AppleWebKit/537.36 SWCampus/7.3.70")


def native_token_sign(uid: int, token: str, ts: int) -> str:
    query = f"timeStamp={ts}&token={token}&uid={uid}"
    return md5_hex((query + TOKEN_SIGN_SUFFIX).encode())


def build_ios_header(identity, uid, token, ts=None):
    ts = ts or now_ms()
    device_id = identity["device_id"]
    install = identity["app_install_time"]
    m = {
        "osType": "1",
        "DeviceId": device_id,
        "deviceName": identity["device_name"],
        "CustomDeviceId": f"{device_id}_iOS_sportsWorld_campus",
        "osVersion": identity["os_version"],
        "logicPixel": "360x640",
        "physicPixel": "1080x1920",
        "cpuModel": "x86_64",
        "appVersion": IOS_APP_VERSION,
        "isRoot": False,
        "appInstallTime": install,
    }
    if identity.get("idfa"):
        m["IDFA"] = identity["idfa"]
    nonce = str(uuid.uuid4()).upper()
    m["nonce"] = nonce
    if uid >= 1:
        m["uid"] = uid
    if token:
        m["token"] = token
    m["timeStamp"] = ts
    m["studentId"] = uid if uid >= 1 else 0
    if uid >= 1 and token:
        m["tokenSign"] = native_token_sign(uid, token, ts)

    extra = [
        ("nonce", nonce),
        ("timeStamp", str(ts)),
        ("tokenSign", native_token_sign(uid, token, ts)),
    ]
    dim(f"iOS 头 uid={uid} device={device_id[:8]}… ts={ts}")
    return json.dumps(m, separators=(",", ":")), extra


def build_android_header(identity, uid, token, ts=None):
    ts = ts or now_ms()
    device_id = identity["device_id"]
    install = identity["app_install_time"]
    m = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "appVersion": ANDROID_APP_VERSION,
        "osType": "0",
        "DeviceId": device_id,
        "osVersion": identity["os_version"],
        "deviceName": identity["device_name"],
        "IMEI": "",
        "logicPixel": "1080x2400",
        "physicPixel": "1080x2400",
        "androidId": "",
        "blMac": "",
        "wifiMac": "",
        "cpuModel": "arm64-v8a",
        "isRoot": False,
        "appUpdateTime": install,
        "appInstallTime": install,
    }
    nonce = str(uuid.uuid4()).upper()
    m["nonce"] = nonce
    m["timeStamp"] = ts
    m["CustomDeviceId"] = f"{device_id}_android_sportsWorld_campus"
    m["uid"] = uid
    m["token"] = token
    m["studentId"] = uid
    sign = native_token_sign(uid, token, ts)
    m["tokenSign"] = sign

    extra = [("nonce", nonce), ("timeStamp", str(ts)), ("tokenSign", sign)]
    dim(f"Android 头 uid={uid} device={device_id[:8]}… ts={ts}")
    return json.dumps(m, separators=(",", ":")), extra


def build_header_for(identity, uid, token, ts=None):
    if identity.get("platform") == "android":
        return build_android_header(identity, uid, token, ts)
    return build_ios_header(identity, uid, token, ts)
