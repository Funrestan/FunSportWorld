"""违规通报名单。"""
import json
from ..config import DISCOVERY
from ..crypto.decrypt import parse_data_field
from ..logger import ok


CHEATLIST_PATH = "/api/v78/cheat/cheatlist"


class CheatReport:
    def __init__(self, self_info, lst):
        self.self_info = self_info
        self.list = lst

    def is_clean(self):
        return self.self_info is None

    def self_brief(self):
        if self.is_clean():
            return "干净"
        v = self.self_info
        reason = v.get("reason") or v.get("punishReason") or v.get("cause") or ""
        name = v.get("name", "")
        return f"{name} {reason}".strip()


def query(client, page=1):
    unid = int(client.session_data["unid"]) if client.session_data else 0
    body = json.dumps({"pageNum": page, "pageSize": 20, "unid": unid})
    biz = client.call("POST", CHEATLIST_PATH, body, host=DISCOVERY)
    data = parse_data_field(biz)
    lst = []
    self_info = None
    if isinstance(data, dict):
        lst = data.get("list") or []
        self_info = data.get("self")
    ok(f"违规自查 self={'null' if self_info is None else '非空'} 全校 {len(lst)} 条")
    return CheatReport(self_info, lst)
