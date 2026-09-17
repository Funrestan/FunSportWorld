"""GT4 滑块验证。"""
import hashlib
import json
import random
import time
import uuid

import requests
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA

from .gt4image import get_distance_original
from ..logger import log, ok, err, warn, dim
GEE_HOST = "https://gcaptcha4.geetest.com"
STATIC_HOST = "https://static.geetest.com/"
UA_WEB = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

_LIMBS = [
    134982529, 254232810, 164556709, 234907349, 134685994, 35463984, 258277946, 12518857,
    44638621, 93783641, 212253739, 62792472, 186688352, 109500232, 182488077, 261196188,
    26354094, 103248217, 106891695, 165771045, 41530993, 263704736, 111785174, 12753611,
    232116673, 155524985, 218291229, 122452343, 248250238, 118739550, 251169095, 129059733,
    149835464, 5498868, 71719731, 154456417, 49635,
]


def _gee_rsa_public_key():
    n = 0
    for limb in reversed(_LIMBS):
        n = n * (1 << 28) + limb
    return RSA.construct((n, 65537))


def _four_random_chart(rng):
    v = int(65536 * (1.0 + rng.random()))
    s = f"{v:x}"
    return s[1:5]


def _get_str_16(rng):
    return "".join(_four_random_chart(rng) for _ in range(4))


def _get_pow_msg_str_16(base: str, max_try=2_000_000):
    hexchars = "0123456789abcdef"
    for i in range(max_try):
        nonce = "".join(random.choice(hexchars) for _ in range(16))
        h = hashlib.sha256((base + nonce).encode()).hexdigest()
        if h.startswith("00"):
            dim(f"PoW nonce 尝试 {i+1} 次")
            return nonce
    raise RuntimeError("PoW 超限")


def _get_pow_msg(pow_detail, captcha_id, lot_number):
    base = "{}|{}|{}|{}|{}|{}||".format(
        pow_detail.get("version", ""),
        pow_detail.get("bits", ""),
        pow_detail.get("hashfunc", ""),
        pow_detail.get("datetime", ""),
        captcha_id,
        lot_number,
    )
    nonce = _get_pow_msg_str_16(base)
    return base + nonce


def _get_pow_sign(pow_msg):
    return hashlib.sha256(pow_msg.encode()).hexdigest()


def _aes_o(plaintext, str_16):
    key = str_16.encode()
    iv = b"0000000000000000"
    data = plaintext.encode()
    pad = 16 - len(data) % 16
    data += bytes([pad]) * pad
    ct = AES.new(key, AES.MODE_CBC, iv).encrypt(data)
    return ct.hex()


def _encrypt_data(pub_key, plaintext):
    cipher = PKCS1_v1_5.new(pub_key)
    return cipher.encrypt(plaintext.encode()).hex()


def _get_w(set_left, lot_number, pow_msg, pow_sign, str16):
    pk = _gee_rsa_public_key()
    userresponse = set_left / 1.0059466666666665 + 2.0
    lf = lambda a, b: lot_number[a:b]
    plaintext = json.dumps({
        "setLeft": set_left,
        "passtime": 1887,
        "userresponse": userresponse,
        "device_id": "",
        "lot_number": lot_number,
        "pow_msg": pow_msg,
        "pow_sign": pow_sign,
        "geetest": "captcha",
        "lang": "zh",
        "ep": "123",
        "biht": "1426265548",
        "gee_guard": {"roe": {
            "aup": "3", "sep": "3", "egp": "3", "auh": "3",
            "rew": "3", "snh": "3", "res": "3", "cdc": "3"
        }},
        "YciC": "P3Vn",
        lf(26, 30) + lf(7, 11): lf(6, 14),
        "em": {"ph": 0, "cp": 0, "ek": "11", "wd": 1, "nt": 0, "si": 0, "sc": 0},
    }, separators=(",", ":"))
    r = _encrypt_data(pk, str16)
    i = _aes_o(plaintext, str16)
    return i + r


def _jsonp_value(text):
    s = text.find("(")
    e = text.rfind(")")
    if s < 0 or e <= s:
        raise ValueError("JSONP 格式错误")
    return json.loads(text[s + 1:e])


def _urlencode(s):
    safe = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~"
    return "".join(c if c in safe else f"%{ord(c):02X}" for c in s)


def _download(session, url):
    r = session.get(url, headers={"User-Agent": UA_WEB}, timeout=30)
    r.raise_for_status()
    return r.content


def solve_once(captcha_id):
    session = requests.Session()
    challenge = uuid.uuid4().hex
    cb = f"geetest_{int(time.time()*1000)}"
    load_url = (f"{GEE_HOST}/load?callback={cb}&captcha_id={captcha_id}"
                f"&challenge={challenge}&client_type=web&risk_type=slide&lang=zh")
    r = session.get(load_url, headers={"User-Agent": UA_WEB}, timeout=30)
    data = _jsonp_value(r.text)["data"]
    bg = data["bg"]
    slice_ = data["slice"]
    lot_number = data["lot_number"]
    payload = data["payload"]
    process_token = data["process_token"]
    pow_detail = data["pow_detail"]

    log.info("下载验证码图片…")
    bg_png = _download(session, STATIC_HOST + bg)
    slice_png = _download(session, STATIC_HOST + slice_)

    dist = get_distance_original(bg_png, slice_png)
    ok(f"缺口 distance={dist}")

    pow_msg = _get_pow_msg(pow_detail, captcha_id, lot_number)
    pow_sign = _get_pow_sign(pow_msg)
    str16 = _get_str_16(random)
    w = _get_w(dist, lot_number, pow_msg, pow_sign, str16)

    cb2 = f"geetest_{int(time.time()*1000)}"
    verify_url = (f"{GEE_HOST}/verify?callback={cb2}&captcha_id={captcha_id}"
                  f"&client_type=web&lot_number={_urlencode(lot_number)}"
                  f"&risk_type=slide&payload={_urlencode(payload)}"
                  f"&process_token={_urlencode(process_token)}"
                  f"&payload_protocol=1&pt=1&w={_urlencode(w)}")
    r = session.get(verify_url, headers={"User-Agent": UA_WEB}, timeout=30)
    root = _jsonp_value(r.text)
    if root.get("status") != "success":
        raise RuntimeError(f"GT4 verify 失败: {r.text[:200]}")
    seccode = root["data"]["seccode"]
    ok(f"GT4 通过 lot={seccode['lot_number'][:8]}…")
    return {
        "lotNumber": seccode["lot_number"],
        "captchaOutput": seccode["captcha_output"],
        "passToken": seccode["pass_token"],
        "genTime": seccode["gen_time"],
    }


def solve_gt4(captcha_id, max_retry=3):
    last = ""
    for i in range(1, max_retry + 1):
        try:
            return solve_once(captcha_id)
        except Exception as e:
            err(f"GT4 第 {i} 次失败: {e}")
            last = str(e)
            time.sleep(3)
    raise RuntimeError(f"GT4 连续 {max_retry} 次失败: {last}")
