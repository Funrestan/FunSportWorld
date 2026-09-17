"""OBS 上传。"""
import json
import requests

from ..crypto.decrypt import parse_data_field, get_field
from ..logger import log, ok, warn

OBS_SIGN_PATH = "/api/obs/temporary/url"


def sign_url(client, method, key):
    body = json.dumps({
        "bucketName": "iydsj-hbase-hot",
        "objectKey": key,
        "method": method,
        "contentType": "application/json",
    }, separators=(",", ":"))
    biz = client.call("POST", OBS_SIGN_PATH, body)
    data = parse_data_field(biz)
    signed = None
    if isinstance(data, dict):
        signed = data.get("signedUrl")
    if not signed:
        signed = get_field(biz, "signedUrl")
    if not signed:
        raise RuntimeError("OBS 签名缺 signedUrl")
    return signed


def put_object(signed_url, payload):
    r = requests.put(signed_url, data=payload,
                     headers={"Content-Type": "application/json"}, timeout=60)
    r.raise_for_status()
    log.info(f"[obs] PUT -> {r.status_code}")


def upload_both_keys(client, keys, payload):
    n = 0
    for key in keys:
        try:
            url = sign_url(client, "Put", key)
            put_object(url, payload)
            ok(f"[obs] {key} 上传成功")
            n += 1
        except Exception as e:
            warn(f"[obs] {key} 上传失败: {e}")
    return n
