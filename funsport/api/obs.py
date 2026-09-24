"""OBS 上传。"""
import json
import requests
import time
from urllib.parse import urlsplit

from ..crypto.decrypt import parse_data_field, get_field
from ..logger import log, ok, warn
from ..run_diagnostics import current_archive

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
    archive = current_archive()
    started = time.monotonic()
    parts = urlsplit(signed_url)
    path = "{}{}".format(parts.netloc, parts.path)
    try:
        request_body = json.loads(payload.decode("utf-8"))
    except (AttributeError, UnicodeError, ValueError):
        request_body = {"bytes": len(payload)}
    try:
        r = requests.put(signed_url, data=payload,
                         headers={"Content-Type": "application/json"}, timeout=60)
        if archive:
            try:
                response_body = r.text[:16000]
            except Exception:
                response_body = {"bytes": len(r.content)}
            archive.record_message("obs-upload", "PUT", path, request=request_body,
                                   response={"body": response_body, "bytes": len(r.content)},
                                   status=r.status_code,
                                   error="HTTP {}".format(r.status_code) if r.status_code >= 400 else None,
                                   duration_ms=round((time.monotonic() - started) * 1000))
        r.raise_for_status()
        log.info(f"[obs] PUT -> {r.status_code}")
    except requests.RequestException as exc:
        if archive and "r" not in locals():
            archive.record_message("obs-upload", "PUT", path, request=request_body,
                                   error=str(exc),
                                   duration_ms=round((time.monotonic() - started) * 1000))
        raise


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
