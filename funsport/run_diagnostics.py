"""Opt-in local archive of run plans and the payloads used by one submission."""
import json
import logging
import re
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from . import config


_SECRET_KEYS = {"password", "passwd", "authorization", "signature", "originalsign",
                "key", "deviceid", "amapkey", "apikey", "privatekey", "cookie",
                "runec", "signedurl", "phone", "phonenumber", "mobile", "email"}
_ACTIVE_ARCHIVE = ContextVar("funsport_run_diagnostic_archive", default=None)


def _is_secret_key(key):
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return (normalized in _SECRET_KEYS
            or normalized.endswith(("token", "tokensign", "sign", "secret", "password", "passwd", "signature")))


def _redact_assignment(match):
    name = match.group("name")
    if not _is_secret_key(name):
        return match.group(0)
    return match.group("prefix") + "[redacted]"


def _redact(value):
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()
                if not _is_secret_key(key)}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        value = re.sub(
            r"(?i)(?P<prefix>[\"']?(?P<name>[a-z][a-z0-9_.-]*)[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^,}\s]+)",
            _redact_assignment, value)
        value = re.sub(r"(?i)(https?://[^?\s\"']+|(?<![a-z0-9_.-])/[\w./~%-]*)\?[^\s\"']+",
                       r"\1?[redacted]", value)
        return re.sub(r"\b1[3-9]\d{9}\b", "[phone]", value)
    return value


class _ArchiveLogHandler(logging.Handler):
    def __init__(self, archive):
        super().__init__(level=logging.DEBUG)
        self.archive = archive

    def emit(self, record):
        if current_archive() is self.archive:
            self.archive.append_log(record.getMessage())


class RunDiagnosticArchive:
    """Write opt-in diagnostics under .funsport/data without network credentials."""

    def __init__(self, plan_id="preview"):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        suffix = re.sub(r"[^A-Za-z0-9_-]", "", str(plan_id))[:32] or uuid4().hex[:8]
        self.directory = config.DATA_DIR / "data" / "run-diagnostics" / (stamp + "_" + suffix)
        self.directory.mkdir(parents=True, exist_ok=False)
        self._lock = threading.RLock()
        self._messages = []
        self.capture("communication.json", {"messages": self._messages})

    @classmethod
    def open_existing(cls, directory):
        """Reopen only archives located below this application's diagnostic root."""
        root = (config.DATA_DIR / "data" / "run-diagnostics").resolve()
        path = Path(directory).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise ValueError("诊断目录不在应用数据目录内") from None
        if not path.is_dir():
            raise ValueError("诊断目录不存在")
        archive = object.__new__(cls)
        archive.directory = path
        archive._lock = threading.RLock()
        journal = path / "communication.json"
        try:
            existing = json.loads(journal.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("诊断通信日志缺失或损坏") from exc
        if not isinstance(existing, dict) or not isinstance(existing.get("messages"), list):
            raise ValueError("诊断通信日志格式无效")
        archive._messages = existing["messages"]
        return archive

    def attach(self, logger):
        handler = _ArchiveLogHandler(self)
        logger.addHandler(handler)
        return handler

    @contextmanager
    def active(self):
        token = _ACTIVE_ARCHIVE.set(self)
        try:
            yield self
        finally:
            _ACTIVE_ARCHIVE.reset(token)

    def record_message(self, phase, method, path, request=None, response=None,
                       status=None, error=None, duration_ms=None):
        message = {
            "time": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "phase": phase,
            "method": method,
            "path": path,
            "request": request,
            "response": response,
            "status": status,
            "durationMs": duration_ms,
            "error": error,
        }
        with self._lock:
            self._messages.append(_redact(message))
            self.capture("communication.json", {"messages": self._messages})

    def capture(self, filename, value):
        path = self.directory / Path(filename).name
        try:
            text = json.dumps(_redact(value), ensure_ascii=False, indent=2, default=str)
            temporary = path.with_suffix(path.suffix + ".tmp")
            with self._lock:
                temporary.write_text(text + "\n", encoding="utf-8")
                temporary.replace(path)
            return path
        except OSError as exc:
            logging.getLogger("funsport").warning("诊断文件写入失败 %s: %s", path.name, exc)
            return None

    def append_log(self, message):
        line = "{} {}\n".format(datetime.now().isoformat(timespec="milliseconds"), message)
        try:
            with self._lock:
                with (self.directory / "run.log").open("a", encoding="utf-8") as stream:
                    stream.write(str(_redact(line)))
        except OSError:
            pass

    def capture_plan(self, data, plan_id):
        self.capture("plan.json", {
            "planId": plan_id,
            "policy": data.get("policy"),
            "track": data.get("track"),
            "points": data.get("points"),
            "route": data.get("route"),
            "checkpointDistances": data.get("checkpoint_distances"),
            "checkpointOrder": data.get("checkpoint_order"),
            "checkpointEvaluation": data.get("checkpoint_evaluation"),
            "runRules": data.get("run_rules"),
            "completion": data.get("completion"),
        })
        if data.get("checkpoint_evaluation") is not None:
            self.capture("checkpoint_evaluation.json", data["checkpoint_evaluation"])
        if data.get("completion") is not None:
            self.capture("completion.json", data["completion"])
        raw = data.get("five_point_json", "")
        try:
            wrapper = json.loads(raw)
            point_json = wrapper.get("fivePointJson")
            points = json.loads(point_json) if isinstance(point_json, str) else point_json
            message = {"wrapper": wrapper, "points": points}
        except (TypeError, ValueError, AttributeError):
            message = {"raw": raw, "parseError": True}
        self.capture("checkpoint_message.json", message)
        self.capture("manifest.json", {
            "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "planId": plan_id,
            "status": "preview_ready",
        })


def current_archive():
    return _ACTIVE_ARCHIVE.get()
