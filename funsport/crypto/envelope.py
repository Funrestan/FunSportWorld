"""NetSecKit 信封加密（iOS 请求链）。"""
import base64
import hashlib
import json
import random
import time
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad

from ..logger import dim

KEYDATA_ONE   = "nhang.school"
KEYDATA_TWO   = "5K0E8400-E29"
KEYDATA_THREE = "597DEA1AFB49"

SALT_ALPHABET = "+kot8A*B45jF6CD@a!UVWubcdKLZ{efgMpNOxyz01PQ}Rn)Tvw23XYh(iG7rsEqJHI9+Slm/"

RSA_PUB_PEM = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC5pqlTzsGNZk1RxhH4O4x3JNTD
V7FbVH66mPfW5v1tnIy4ty7xv8DGMG4Zn/TvstwlJWeYOADHdi8uF21lJaBvzvPt
VEhifHXZq825fI9hGYtDoaVQmCN/Nfs2dKmt89XDrhtl3SZxO6TumOCTQt+5oqjF
2Jo3o1YtkAyGzjaJnwIDAQAB
-----END PUBLIC KEY-----"""


def now_ms() -> int:
    return int(time.time() * 1000)


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode()


def b64d(s: str) -> bytes:
    return base64.b64decode(s)


def aes_cbc_encrypt(key: bytes, plain: bytes, iv: bytes = b"\0" * 16) -> bytes:
    return AES.new(key, AES.MODE_CBC, iv).encrypt(pad(plain, 16))


def aes_cbc_decrypt(key: bytes, ct: bytes, iv: bytes = b"\0" * 16) -> bytes:
    return unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ct), 16)


def random_fragment(n: int) -> str:
    return "".join(random.choice(SALT_ALPHABET) for _ in range(n))


def req_key() -> str:
    return random_fragment(16)


def normalize_raw_key_data(value: str) -> str:
    b = value.encode()
    if len(b) <= 7:
        return value + random_fragment(12 - len(b))
    if len(b) >= 13:
        return b[-12:].decode(errors="ignore")
    return value


def key_data_four_from_ms(ms: float) -> str:
    return normalize_raw_key_data(f"{ms:.6f}")


class EnvelopeSession:
    """同一会话复用 Four。"""
    def __init__(self):
        self._four = None

    def key_data(self):
        if self._four is None:
            self._four = key_data_four_from_ms(now_ms())
        return [KEYDATA_ONE, KEYDATA_TWO, KEYDATA_THREE, self._four]

    @classmethod
    def with_four(cls, four: str):
        s = cls()
        s._four = four
        return s


def serialize_container(data_b64: str, ts: int, kd) -> bytes:
    obj = {
        "data": data_b64,
        "timeStamp": ts,
        "platform": 1,
        "keyDataOne": kd[0],
        "keyDataTwo": kd[1],
        "keyDataThree": kd[2],
        "keyDataFour": kd[3],
    }
    return json.dumps(obj, separators=(",", ":")).encode()


def serialize_envelope_fields(d, h, k, order):
    if order == "observed":
        return f'{{"k":"{k}","p":101,"d":"{d}","h":"{h}","t":0}}'
    return f'{{"d":"{d}","h":"{h}","k":"{k}","p":101,"t":0}}'


class BuiltEnvelope:
    def __init__(self, json_str, container, req_key, ts_ms, key_data):
        self.json = json_str
        self.container = container
        self.req_key = req_key
        self.ts_ms = ts_ms
        self.key_data = key_data


def rsa_public_key():
    return RSA.import_key(RSA_PUB_PEM)


def build_envelope(session: EnvelopeSession, plain: str, order="insert", ts_ms=None):
    if ts_ms is None:
        ts_ms = now_ms()
    kd = session.key_data()
    container = serialize_container(b64e(plain.encode()), ts_ms, kd)
    rk = req_key()
    d = b64e(aes_cbc_encrypt(rk.encode(), container))
    h = md5_hex(container)
    pub = rsa_public_key()
    cipher = PKCS1_v1_5.new(pub)
    k = b64e(cipher.encrypt(rk.encode()))
    json_str = serialize_envelope_fields(d, h, k, order)
    dim(f"信封[{order}] ts={ts_ms} reqKey={rk[:4]}… container={len(container)}B")
    return BuiltEnvelope(json_str, container, rk, ts_ms, kd)
