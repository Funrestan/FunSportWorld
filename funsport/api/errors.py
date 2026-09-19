"""保留接口上下文的业务错误，不包含请求正文、凭据或签名 URL。"""
from urllib.parse import urlsplit


class BusinessError(RuntimeError):
    """区分服务器业务拒绝与本地参数检查失败。"""

    def __init__(self, code, message, path):
        """记录业务码和去掉查询串的接口路径，并补充 11016 的操作边界。"""
        self.code = code
        self.path = urlsplit(str(path)).path
        self.message = str(message or "(无消息)")
        lines = ["业务错误 {}: {}".format(code, self.message), "接口：" + self.path]
        if str(code) == "11016":
            if self.path.endswith("/runModePolicy"):
                lines.append("失败阶段：获取跑步策略；本次操作尚未生成或提交记录。")
                lines.append("此请求没有轨迹开始时间字段，修改方案开始时间不会改变该请求。")
            elif self.path.endswith("/runnings/save/record"):
                lines.append("失败阶段：提交跑步记录；服务端返回了拒绝。")
            elif self.path.endswith("/get/1/distance/1"):
                lines.append("失败阶段：获取打卡点；本次查询没有提交跑步记录。")
            lines.append("跳过本地时间检查不会改变服务器的计分跑开放时段。")
            lines.append("只测试路线可使用轨迹预览（仍需高德服务）；在线计分操作请按官方 App 的跑步指标在开放时段进行。")
        super().__init__("\n".join(lines))
