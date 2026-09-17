"""个人信息。"""
import json
from ..crypto.decrypt import parse_data_field
from ..logger import ok


HOME_PAGE_INFO_PATH = "/api/v41/user/HomePageInfo"
PERSONAL_SEMESTER_PATH = "/api/v41/running/getPersonalSemesterInfo"
SEMESTER_COMPLETED_PATH = "/api/v44/runnings/personalSemesterCompleted"


class MyInfo:
    def __init__(self, profile, home_page, personal_semester, summary, completed):
        self.profile = profile
        self.home_page = home_page
        self.personal_semester = personal_semester
        self.summary = summary
        self.completed = completed


def fetch_my_info(client):
    profile = client.session_data.get("profile") if client.session_data else None

    try:
        biz = client.call("GET", HOME_PAGE_INFO_PATH, "{}")
        home_page = parse_data_field(biz)
    except Exception:
        home_page = None

    try:
        biz = client.call("POST", PERSONAL_SEMESTER_PATH,
                          json.dumps({"runMode": 1}))
        personal = parse_data_field(biz)
    except Exception:
        personal = None

    try:
        from .semester import SUMMARY_PATH
        biz = client.call("POST", SUMMARY_PATH, "{}")
        summary = parse_data_field(biz)
    except Exception:
        summary = None

    completed = None
    try:
        from .records import fetch_records
        rows = fetch_records(client)
        if rows:
            biz = client.call("POST", SEMESTER_COMPLETED_PATH,
                              json.dumps({"rrid": rows[0]["rrid"]}))
            completed = parse_data_field(biz)
    except Exception:
        pass

    ok("[user] 我的页数据已更新")
    return MyInfo(profile, home_page, personal, summary, completed)
