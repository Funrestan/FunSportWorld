"""学期完成度。"""
import json
from ..crypto.decrypt import parse_data_field
from ..logger import ok


SUMMARY_PATH = "/api/v55/runnings/recordssummary/semester"
PERSONAL_PATH = "/api/v41/running/getPersonalSemesterInfo"


class SemesterSummary:
    def __init__(self, sname="", semester_dis=0.0, semester_valid_dis=0.0,
                 semester_count=0, semester_valid_count=0):
        self.sname = sname
        self.semester_dis = semester_dis
        self.semester_valid_dis = semester_valid_dis
        self.semester_count = semester_count
        self.semester_valid_count = semester_valid_count


def query(client):
    biz = client.call("POST", SUMMARY_PATH, "{}")
    data = parse_data_field(biz)
    if not isinstance(data, dict):
        data = {}
    s = SemesterSummary(
        sname=data.get("sname", ""),
        semester_dis=data.get("semesterDis", 0.0),
        semester_valid_dis=data.get("semesterValidDis", 0.0),
        semester_count=data.get("semesterCount", 0),
        semester_valid_count=data.get("semesterValidCount", 0),
    )

    personal = None
    try:
        biz2 = client.call("POST", PERSONAL_PATH, json.dumps({"runMode": 1}))
        personal = parse_data_field(biz2)
    except Exception as e:
        ok(f"[semester] 个人完成度失败: {e}")

    if not s.sname and isinstance(personal, dict):
        s.sname = personal.get("sname", "")
    if s.semester_valid_count == 0 and isinstance(personal, dict):
        s.semester_valid_count = personal.get("semesterValid", 0)

    ok(f"学期 {s.sname} 有效 {s.semester_valid_count}/{s.semester_count} 次")
    return {"summary": s, "personal_raw": personal}
