"""HTTP 客户端。"""
import json
import requests
import time
from .errors import BusinessError

from ..crypto.envelope import EnvelopeSession, build_envelope
from ..crypto.decrypt import derive_paes_key
from ..crypto.decrypt import decrypt_response
from ..crypto.header import build_header_for, UA_IOS
from ..config import HOST, DISCOVERY
from ..logger import log, ok, err, dim
from ..run_diagnostics import current_archive


class ApiClient:
    def __init__(self, identity, session=None):
        self.identity = identity
        self.session_data = session
        self.env_session = EnvelopeSession()
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": UA_IOS, "appVersion": "7.3.40"})

    def uid(self):
        return self.session_data["uid"] if self.session_data else -1

    def token(self):
        return self.session_data["token"] if self.session_data else ""

    def call(self, method, path, body_plain="{}", host=None, extra_headers=None):
        """发送现有协议请求；日志只记录元数据，不输出凭据或业务响应。"""
        host = host or HOST
        url = host + path
        extra_headers = extra_headers or []

        header_plain, hp_extra = build_header_for(
            self.identity, self.uid(), self.token()
        )
        header_env = build_envelope(self.env_session, header_plain, "observed")
        body_env = build_envelope(self.env_session, body_plain, "insert", header_env.ts_ms + 1)
        archive = current_archive()
        try:
            request_body = json.loads(body_plain)
        except (TypeError, ValueError):
            request_body = body_plain

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "headerSign": header_env.json,
        }
        for k, v in hp_extra:
            headers[k] = v
        for k, v in extra_headers:
            headers[k] = v

        log.info(f"→ {method} {path.split('?')[0]}")
        started = time.monotonic()
        try:
            resp = self.http.request(method, url, data=body_env.json,
                                     headers=headers, timeout=30)
        except requests.RequestException as e:
            if archive:
                archive.record_message("app-api", method, path.split("?")[0],
                                        request_body, error=str(e),
                                        duration_ms=round((time.monotonic() - started) * 1000))
            err(f"网络错误: {e}")
            raise

        log.info(f"← HTTP {resp.status_code} len={len(resp.content)}")

        try:
            key = derive_paes_key(*body_env.key_data)
            dec = decrypt_response(resp.content, key)
        except Exception as e:
            if archive:
                archive.record_message("app-api", method, path.split("?")[0],
                                        request_body,
                                        response={"encryptedBytes": len(resp.content)},
                                        status=resp.status_code, error=str(e),
                                        duration_ms=round((time.monotonic() - started) * 1000))
            raise

        biz = dec.business
        if archive:
            archive.record_message("app-api", method, path.split("?")[0],
                                   request_body, response={"business": biz},
                                   status=resp.status_code,
                                   duration_ms=round((time.monotonic() - started) * 1000))
        err_code = biz.get("error", 0)
        if err_code != 10000:
            msg = biz.get("message") or biz.get("msg") or "(无消息)"
            problem = BusinessError(err_code, msg, path)
            err(str(problem))
            raise problem
        dim(f"响应业务码: {err_code}")
        return biz
