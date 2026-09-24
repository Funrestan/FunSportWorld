"""配置保护、输入校验、日志脱敏和 CLI 入口回归测试。"""
import io
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from tests.support import IsolatedCase
from funsport import config, gui_services as services


class ServiceTests(IsolatedCase):
    """只使用临时配置和假客户端。"""

    def test_clear_coordinates_invalidates_cache(self):
        """清空坐标也清空校园缓存，不回填被用户删除的旧坐标。"""
        services.save_settings(self.form())
        config.save_json(config.POINTS_CACHE, {"points": [1]})
        snapshot = services.save_settings(self.form(anchor_lat="", anchor_lon=""))
        self.assertEqual(snapshot["anchor_lat"], "")
        self.assertFalse(config.POINTS_CACHE.exists())
        self.assertTrue(snapshot["reset_views"])

    def test_captcha_fields_are_redacted(self):
        """失败消息中的验证码凭据同样脱敏。"""
        text = json.dumps({"passToken": "pt-example", "captchaOutput": "co-example",
                           "lotNumber": "ln-example", "genTime": "gt-example"})
        result = services.safe_text(text)
        for value in ("pt-example", "co-example", "ln-example", "gt-example"):
            self.assertNotIn(value, result)

    def form(self, **changes):
        """构造一个有效的设置表单供测试修改。"""
        values = {"username": "example", "password": "", "remember": False, "city": "测试市",
                  "anchor_lat": "30.6", "anchor_lon": "104.1", "amap_key": "",
                  "start_before_min": "30", "start_before_max": "300"}
        values.update(changes)
        return values

    def test_preserve_unknown_settings_and_password(self):
        """保留未知字段、既有设备身份和同账号未改动的密码。"""
        config.save_config({"username": "example", "password": "example-secret", "remember": True, "extra": 99})
        config.save_identity({"device_id": "same-device", "extra": 22})
        snapshot = services.save_settings(self.form(remember=True))
        self.assertEqual(services.read_object(config.CONFIG_FILE)["extra"], 99)
        self.assertEqual(services.read_object(config.CONFIG_FILE)["password"], "example-secret")
        self.assertEqual(services.read_object(config.IDENTITY_FILE)["device_id"], "same-device")
        self.assertEqual(snapshot["password"], "")

    def test_forget_password(self):
        """取消记住密码时真正清除本地密码，不只改变复选框。"""
        config.save_config({"username": "example", "password": "example-secret", "remember": True})
        services.save_settings(self.form())
        self.assertEqual(services.read_object(config.CONFIG_FILE)["password"], "")

    def test_account_change_after_logout_clears_cache(self):
        """已经退出后切换账号清除旧学校点位与旧密码，避免跨账号复用。"""
        config.save_config({"username": "old", "password": "old-secret", "remember": True})
        config.save_json(config.POINTS_CACHE, {"points": []})
        config.save_json(config.DATA_DIR / "campus_loop_bd.json", {"points": []})
        services.save_settings(self.form(remember=True))
        self.assertFalse(config.SESSION_FILE.exists())
        self.assertFalse(config.POINTS_CACHE.exists())
        self.assertFalse((config.DATA_DIR / "campus_loop_bd.json").exists())
        self.assertEqual(services.read_object(config.CONFIG_FILE)["password"], "")

    def test_account_change_requires_server_logout_before_writes(self):
        """存在旧会话时禁止切换设置，所有配置与缓存均不变。"""
        config.save_config({"username": "old", "password": "old-secret", "remember": True})
        config.save_identity({"device_id": "fixture-device"})
        config.save_session({"uid": 1, "token": "fake"})
        config.save_json(config.POINTS_CACHE, {"points": ["fixture"]})
        paths = [config.CONFIG_FILE, config.IDENTITY_FILE, config.SESSION_FILE, config.POINTS_CACHE]
        before = {path: path.read_bytes() for path in paths}
        with self.assertRaisesRegex(ValueError, "先点击.*退出登录"):
            services.save_settings(self.form(remember=True))
        self.assertEqual({path: path.read_bytes() for path in paths}, before)

    def test_saving_current_session_account_is_not_switching(self):
        """先登录后首次保存同账号设置不要求退出，也不删除现有会话。"""
        session = {"uid": 1, "token": "fake", "username": "example"}
        config.save_session(session)
        services.save_settings(self.form())
        self.assertEqual(config.load_session(), session)

    def test_corrupt_config_is_not_overwritten(self):
        """配置损坏时拒绝覆盖，并保证原始字节不变。"""
        config.CONFIG_FILE.write_bytes(b"{broken")
        with self.assertRaises(ValueError):
            services.save_settings(self.form())
        self.assertEqual(config.CONFIG_FILE.read_bytes(), b"{broken")
        self.assertFalse(config.IDENTITY_FILE.exists())

    def test_invalid_form_does_not_write(self):
        """所有字段校验都应在写盘之前完成。"""
        for change in ({"anchor_lon": ""}, {"anchor_lat": "NaN"},
                       {"start_before_min": "301"}, {"city": ""}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                services.save_settings(self.form(**change))
        self.assertFalse(config.CONFIG_FILE.exists())
        self.assertFalse(config.IDENTITY_FILE.exists())

    def test_atomic_write_failure_preserves_original(self):
        """原子替换失败时保留原文件并清理临时文件。"""
        config.save_config({"keep": 1})
        original = config.CONFIG_FILE.read_bytes()
        with patch("funsport.config.os.replace", side_effect=OSError("simulated")):
            with self.assertRaises(OSError):
                config.save_config({"keep": 2})
        self.assertEqual(config.CONFIG_FILE.read_bytes(), original)
        self.assertEqual(list(self.data.iterdir()), [config.CONFIG_FILE])

    def test_invalid_number(self):
        """数字输入拒绝 NaN、无穷、越界和小数整数值。"""
        for value in ("NaN", "inf", "0", "101", "2.5", "text"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                services.number(value, "测试", 1, 100, True)

    def test_run_parameters(self):
        """手动字段与自动字段分离，只有所选时间模式产生参数。"""
        manual = services.run_parameters({"auto": False, "dist": "2.8", "pace": "400", "cadence": "160",
                                          "seed": "42", "time_mode": "before", "before": "60"})
        self.assertEqual(manual["dist"], 2.8)
        self.assertEqual(manual["before"], 60)
        auto = services.run_parameters({"auto": True, "dist": "invalid", "time_mode": "config"})
        self.assertTrue(auto["use_map"])
        self.assertNotIn("dist", auto)
        self.assertNotIn("before", auto)

    def test_diagnostic_capture_setting_defaults_off_and_persists(self):
        self.assertFalse(services.settings_snapshot()["diagnostic_capture"])
        saved = services.save_settings(self.form(diagnostic_capture=True))
        self.assertTrue(saved["diagnostic_capture"])
        self.assertTrue(services.read_object(config.CONFIG_FILE)["diagnostic_capture"])
        saved = services.save_settings(self.form(diagnostic_capture=False))
        self.assertFalse(saved["diagnostic_capture"])

    def test_start_time(self):
        """指定时间只接受过去三天内的正确日期格式。"""
        valid = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        self.assertIn("start_ms", services.run_parameters({"auto": True, "time_mode": "at", "start_at": valid}))
        for value in ("tomorrow", "2000-01-01 00:00", "2099-01-01 00:00"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                services.run_parameters({"auto": True, "time_mode": "at", "start_at": value})

    def test_missing_session_does_not_login(self):
        """只读按钮在无会话时提示登录，不自动触发验证码流程。"""
        with patch("funsport.api.login.login") as login:
            with self.assertRaises(ValueError):
                services.with_client(lambda client: None)
            login.assert_not_called()

    def test_client_closes_after_failure(self):
        """业务失败时也释放 HTTP 会话。"""
        config.save_session({"uid": 1, "token": "fake"})
        client = Mock()
        action = Mock(side_effect=ValueError("expected"))
        with patch("funsport.api.client.ApiClient", return_value=client):
            with self.assertRaises(ValueError):
                services.with_client(action)
        client.http.close.assert_called_once()

    def test_snapshot_does_not_expose_secrets(self):
        """状态快照仅返回是否配置，不返回密码、地图 Key 或令牌。"""
        config.save_config({"password": "secret-value", "amap_key": "key-value"})
        config.save_session({"uid": 1, "token": "token-value"})
        text = json.dumps(services.settings_snapshot())
        for secret in ("secret-value", "key-value", "token-value"):
            self.assertNotIn(secret, text)

    def test_log_redaction(self):
        """日志遮蔽显式秘密、手机号、JSON 令牌和签名 URL 查询串。"""
        value = 'password=example-secret token=token-secret\nhttps://example.test/object?signature=opaque 13812345678'
        result = services.safe_text(value, ("example-secret",))
        for secret in ("example-secret", "token-secret", "opaque", "13812345678"):
            self.assertNotIn(secret, result)

    def test_main_entrypoints(self):
        """无参数和 gui 启动窗口，help 保持命令行输出。"""
        from funsport.main import main
        with patch("funsport.main.cmd_gui") as gui:
            main([])
            main(["gui"])
            self.assertEqual(gui.call_count, 2)
        with patch("sys.stdout", new=io.StringIO()) as stream:
            main(["help"])
            self.assertIn("FunSportWorld CLI", stream.getvalue())
