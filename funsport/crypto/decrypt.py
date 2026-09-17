"""响应解密链。"""
import json

from .envelope import md5_hex, b64d, aes_cbc_decrypt, rsa_public_key
from ..logger import dim


def c_string_bytes(v: str) -> bytes:
    b = v.encode()
    i = b.find(b"\0")
    return b[:i] if i >= 0 else b


def fold32(value: str) -> int:
    h = 0
    for c in c_string_bytes(value):
        h = (((h & 0xFFFFFF) << 8) | c) ^ (h >> 24)
    return h & 0xFFFFFFFF


def ror32(v: int, bits: int) -> int:
    v &= 0xFFFFFFFF
    return ((v >> bits) | (v << (32 - bits))) & 0xFFFFFFFF


def derive_paes_key(one, two, three, four) -> bytes:
    for v in (one, two, three, four):
        l = len(c_string_bytes(v))
        assert 8 <= l <= 12, f"keyData 长度必须 8..12B: {v}"

    a, b, c, d = fold32(one), fold32(two), fold32(three), fold32(four)

    w9 = (c ^ a) & 0xFFFFFFFF
    w10 = (w9 ^ ror32(w9, 24)) & 0xFFFFFFFF
    w9 = (w10 ^ ror32(w9, 8)) & 0xFFFFFFFF
    w10 = (w9 ^ b) & 0xFFFFFFFF
    w9 = (w9 ^ d) & 0xFFFFFFFF
    w8 = (d ^ b) & 0xFFFFFFFF
    w11 = (w8 ^ ror32(w8, 24)) & 0xFFFFFFFF
    w8 = (w11 ^ ror32(w8, 8)) & 0xFFFFFFFF
    w11 = (w8 ^ a) & 0xFFFFFFFF
    w8 = (w8 ^ c) & 0xFFFFFFFF

    w12 = (w8 & w10) & 0xFFFFFFFF
    w11 = (w11 ^ w12) & 0xFFFFFFFF
    w12 = (w8 | w9) & 0xFFFFFFFF
    w8 = (w8 ^ w9) & 0xFFFFFFFF
    w10 = (w10 ^ w12) & 0xFFFFFFFF
    w8 = (w10 ^ (~w8 & 0xFFFFFFFF)) & 0xFFFFFFFF
    w12 = (w8 ^ w11) & 0xFFFFFFFF
    w8 = (w8 | w11) & 0xFFFFFFFF
    w8 = (w8 ^ w10) & 0xFFFFFFFF
    w10 = (w12 & (~w10 & 0xFFFFFFFF)) & 0xFFFFFFFF
    w9 = (w9 ^ w10) & 0xFFFFFFFF

    out = b""
    for w in (w9, w8, w12, w11):
        out += w.to_bytes(4, "little")
    return out


def rsa_recovered_digest(s_b64: str, pub_key) -> str:
    sig = b64d(s_b64)
    n = pub_key.n
    size = (n.bit_length() + 7) // 8
    if len(sig) != size:
        raise ValueError(f"s 长度错误 {len(sig)} != {size}")
    m = int.from_bytes(sig, "big")
    em = pow(m, pub_key.e, n).to_bytes(size, "big")
    if em[0] != 0 or em[1] != 1:
        raise ValueError("s 不是 PKCS#1 type-1 块")
    sep = em.find(b"\0", 2)
    if sep < 10 or any(b != 0xFF for b in em[2:sep]):
        raise ValueError("PKCS#1 填充不合法")
    digest = em[sep + 1:]
    if len(digest) != 32 or not all(48 <= b <= 57 or 97 <= b <= 102 for b in digest):
        raise ValueError("尾部不是 32B 小写 hex")
    return digest.decode()


class Decrypted:
    def __init__(self, plaintext, business, expected_md5="", actual_md5=""):
        self.plaintext = plaintext
        self.business = business
        self.expected_md5 = expected_md5
        self.actual_md5 = actual_md5


def decrypt_response(raw: bytes, key: bytes) -> Decrypted:
    text = raw.decode(errors="ignore").strip()
    obj = json.loads(text)

    if isinstance(obj.get("resp"), str):
        obj = json.loads(obj["resp"])
    elif obj.get("resp") is not None:
        obj = obj["resp"]

    if not all(k in obj for k in ("r", "s", "v")):
        return Decrypted(text, obj)

    if obj["v"] != 101:
        raise ValueError(f"响应版本错误 {obj['v']} != 101")

    pub = rsa_public_key()
    expected = rsa_recovered_digest(obj["s"], pub)
    layer1 = aes_cbc_decrypt(key, b64d(obj["r"]))
    actual = md5_hex(layer1)
    if actual != expected:
        raise ValueError(f"验签失败 实际={actual} 期望={expected}")

    plaintext = layer1.decode(errors="ignore")
    env = json.loads(plaintext)

    if "d" in env:
        layer2 = aes_cbc_decrypt(key, b64d(env["d"]))
        outer = json.loads(layer2)
    else:
        outer = env

    business = outer
    if isinstance(outer.get("data"), str):
        business = json.loads(b64d(outer["data"]))

    dim(f"解密 验签={actual[:8]}… error={business.get('error')}")
    return Decrypted(plaintext, business, expected, actual)


def parse_data_field(biz):
    """data 字段若是字符串则解析。"""
    if not isinstance(biz, dict):
        return biz
    data = biz.get("data")
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return None
    return data


def get_field(biz, name):
    """先顶层，再 data 子对象。"""
    if isinstance(biz, dict):
        v = biz.get(name)
        if v is not None:
            return v
        d = biz.get("data")
        if isinstance(d, dict):
            return d.get(name)
    return None
