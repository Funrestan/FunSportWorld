"""登录链。"""
import base64
import json
import time
import uuid

from .gt4 import solve_gt4
from .errors import BusinessError
from ..config import HOST, save_session, clear_session
from ..crypto.decrypt import parse_data_field, get_field, decrypt_response, derive_paes_key
from ..crypto.header import build_ios_header, UA_IOS
from ..crypto.envelope import build_envelope
from ..logger import log, ok, err, warn

GEEVALIDATE_PATH = "/api/v70270/security/geevalidate"
GEECHECK_PATH = "/api/v65/security/checkGeeUse"
LOGIN_PATH = "/api/v70100/login"
LOGOUT_PATH = "/api/v6/user/logout"

CAPTCHA_ID_BIZ0 = "8c065103d81f5fd3efec8ad3e3a84c30"


def _gee_check(client, username):
    body = json.dumps({
        "username": username,
        "uuid": str(uuid.uuid4()),
        "unid": 0,
        "type": 2,
    })
    try:
        biz = client.call("POST", GEECHECK_PATH, body)
        skip = biz.get("data") is True
        log.info(f"[gee] checkGeeUse data={skip}")
        return skip
    except Exception as e:
        warn(f"[gee] checkGeeUse 失败: {e}，按需验证处理")
        return False


def _geevalidate(client, body, uuid_value, username):
    """直接走 envelope_request，返回 error 码，不抛异常。"""
    url = HOST + GEEVALIDATE_PATH
    header_plain, hp_extra = build_ios_header(client.identity, -1, "")
    header_env = build_envelope(client.env_session, header_plain, "observed")
    body_env = build_envelope(client.env_session, body, "insert", header_env.ts_ms + 1)
    headers = {"Content-Type": "application/json; charset=utf-8",
               "headerSign": header_env.json}
    for k, v in hp_extra:
        headers[k] = v
    resp = client.http.post(url, data=body_env.json, headers=headers, timeout=30)
    key = derive_paes_key(*body_env.key_data)
    dec = decrypt_response(resp.content, key)
    return dec.business.get("error")


def login(client, username, password):
    uuid_value = str(uuid.uuid4())
    if _gee_check(client, username):
        ok("[login] 免验证码路径")
    else:
        captcha_id = CAPTCHA_ID_BIZ0
        validated = False
        for attempt in range(1, 4):
            log.info(f"[login] GT4 滑块验证 {attempt}/3…")
            creds = solve_gt4(captcha_id)
            body = json.dumps({
                "lotNumber": creds["lotNumber"],
                "captchaOutput": creds["captchaOutput"],
                "passToken": creds["passToken"],
                "genTime": creds["genTime"],
                "isOffline": False,
                "osType": 1,
                "businessType": 0,
                "uuid": uuid_value,
                "username": username,
            }, separators=(",", ":"))
            try:
                gv_err = _geevalidate(client, body, uuid_value, username)
            except Exception as e:
                warn(f"[geevalidate] 异常: {e}")
                gv_err = -1
            if gv_err == 10000:
                ok("[geevalidate] 验证通过")
                validated = True
                break
            elif gv_err == 10003:
                warn(f"[geevalidate] 验证失败 {attempt}/3，重试")
                time.sleep(2)
            else:
                warn(f"[geevalidate] err={gv_err}，继续登录")
                validated = True
                break
        if not validated:
            raise RuntimeError("geevalidate 连续失败")
        time.sleep(2)

    identity = client.identity
    device_id = identity["device_id"] or str(uuid.uuid4()).upper()
    login_body = json.dumps({
        "device_model": identity["device_name"],
        "os_version": identity["os_version"],
        "mac_address": identity["mac_address"],
        "imei": "",
        "loginType": 0,
        "username": username,
        "password": password,
        "uuid": uuid_value,
        "osType": "0",
    }, separators=(",", ":"))

    credential = base64.b64encode(f"{username}:{password}".encode()).decode()
    extra = [("Authorization", f"Basic {credential}")]
    biz = client.call("POST", LOGIN_PATH, login_body, extra_headers=extra)

    uid = get_field(biz, "uid") or 0
    token = get_field(biz, "token") or ""
    if uid < 1 or not token:
        raise RuntimeError(f"登录响应缺 uid/token: {biz}")
    unid = get_field(biz, "unid") or "0"
    sess = {
        "uid": uid,
        "token": token,
        "unid": str(unid),
        "name": get_field(biz, "name") or "",
        "weight": get_field(biz, "weight") or 68.0,
        "username": username,
        "device_id": device_id,
        "profile": parse_data_field(biz),
    }
    save_session(sess)
    ok(f"登录成功 uid={uid} unid={unid} name={sess['name']}")
    return sess


def logout(client):
    """使用当前会话请求服务器退出；确认成功才清理本地，失败保留凭据。"""
    session = client.session_data or {}
    if not session.get("uid") or not session.get("token"):
        raise ValueError("没有可用会话，无法请求服务器退出；未执行本地清理")
    try:
        response = client.call("POST", LOGOUT_PATH, "{}")
    except BusinessError as exc:
        raise BusinessError(exc.code, "服务器拒绝退出；本地会话已保留，不能视为退出成功", LOGOUT_PATH) from None
    except Exception:
        raise RuntimeError("退出请求失败或响应无法验证；服务器是否退出未知，本地会话已保留。请检查网络后重试退出。") from None
    if not isinstance(response, dict) or response.get("error") != 10000:
        raise RuntimeError("退出响应未确认成功；本地会话已保留，不能视为退出成功")
    client.session_data = None
    try:
        clear_session()
    except OSError:
        message = "服务器已确认退出，但本地会话文件清理失败；请检查文件权限，不要继续使用旧会话。"
        warn(message)
        return {"local_cleared": False, "message": message}
    message = "服务器已确认退出，本地会话已清除"
    ok(message)
    return {"local_cleared": True, "message": message}
