"""服务器退出与本地会话清理的隔离测试，不使用真实账号。"""
import io
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests.support import IsolatedCase
from funsport import config, gui_services as services
from funsport.api import login as api_login
from funsport.api.errors import BusinessError
from funsport.cli import cmds


class LogoutTests(IsolatedCase):
    """检查请求认证、清理先后顺序、失败保留以及 GUI/CLI 共用后端。"""

    def setUp(self):
        """在临时目录保存示例会话，所有客户端请求都由 Mock 替代。"""
        super().setUp()
        self.session = {"uid": 7, "token": "fixture-token", "username": "fixture-user"}
        config.save_session(self.session)
        self.client = SimpleNamespace(session_data=dict(self.session),
                                      call=Mock(return_value={"error": 10000}), http=Mock())
        logging = patch.object(api_login.log, "disabled", True)
        logging.start()
        self.addCleanup(logging.stop)

    def test_request_precedes_local_cleanup(self):
        """请求过程中本地凭据仍存在，收到成功后才清除文件和内存会话。"""
        config.save_config({"remember": True, "password": "fixture-password"})

        def successful_request(*args):
            """在假服务器返回前核对退出使用的仍是原账号会话。"""
            self.assertEqual(config.load_session(), self.session)
            self.assertEqual(self.client.session_data, self.session)
            return {"error": 10000}

        self.client.call.side_effect = successful_request
        result = api_login.logout(self.client)
        self.client.call.assert_called_once_with("POST", api_login.LOGOUT_PATH, "{}")
        self.assertTrue(result["local_cleared"])
        self.assertFalse(config.SESSION_FILE.exists())
        self.assertIsNone(self.client.session_data)
        self.assertEqual(config.load_config()["password"], "fixture-password")

    def test_logout_transport_uses_existing_uid_and_token(self):
        """保留真实客户端调用链，仅模拟加密和 HTTP，确认原会话用于认证。"""
        from funsport.api import client as client_api
        client = client_api.ApiClient.__new__(client_api.ApiClient)
        client.identity = {"device_id": "fixture-device"}
        client.session_data = dict(self.session)
        client.env_session = None
        client.http = Mock()
        client.http.request.return_value = SimpleNamespace(status_code=200, content=b"fixture")
        envelope = SimpleNamespace(json="encrypted-fixture", ts_ms=1, key_data=(1, 2))
        with patch.object(client_api, "build_header_for", return_value=("fixture-header", [])) as header, \
                patch.object(client_api, "build_envelope", return_value=envelope), \
                patch.object(client_api, "derive_paes_key", return_value=b"fixture"), \
                patch.object(client_api, "decrypt_response", return_value=SimpleNamespace(business={"error": 10000})):
            api_login.logout(client)
        header.assert_called_once_with(client.identity, 7, "fixture-token")
        client.http.request.assert_called_once()
        self.assertEqual(client.http.request.call_args.args, ("POST", config.HOST + api_login.LOGOUT_PATH))
        self.assertFalse(config.SESSION_FILE.exists())

    def test_rejected_logout_keeps_session(self):
        """业务拒绝不会清除会话或返回成功，并保留错误码。"""
        self.client.call.side_effect = BusinessError(10003, "fixture-private-detail", api_login.LOGOUT_PATH)
        before = config.SESSION_FILE.read_bytes()
        with self.assertRaises(BusinessError) as caught:
            api_login.logout(self.client)
        self.assertEqual(caught.exception.code, 10003)
        self.assertNotIn("fixture-private-detail", str(caught.exception))
        self.assertEqual(config.SESSION_FILE.read_bytes(), before)
        self.assertEqual(self.client.session_data, self.session)

    def test_timeout_keeps_session_and_reports_unknown(self):
        """网络超时不推断服务器状态、不自动重试，也不暴露底层秘密。"""
        self.client.call.side_effect = TimeoutError("token=fixture-token")
        with self.assertRaisesRegex(RuntimeError, "服务器是否退出未知") as caught:
            api_login.logout(self.client)
        self.assertNotIn("fixture-token", str(caught.exception))
        self.assertEqual(config.load_session(), self.session)
        self.client.call.assert_called_once()

    def test_unconfirmed_response_keeps_session(self):
        """空响应、异常结构及非成功码不能被误报为退出成功。"""
        for response in (None, [], {}, {"error": 10003}):
            with self.subTest(response=response):
                self.client.call.return_value = response
                with self.assertRaisesRegex(RuntimeError, "未确认成功"):
                    api_login.logout(self.client)
                self.assertEqual(config.load_session(), self.session)

    def test_missing_credentials_never_clears_or_requests(self):
        """认证字段不完整时无法远程退出，不能仅删除本地文件。"""
        for session in (None, {}, {"uid": 7}, {"token": "fixture-token"}):
            with self.subTest(session=session):
                self.client.session_data = session
                with self.assertRaises(ValueError):
                    api_login.logout(self.client)
        self.client.call.assert_not_called()
        self.assertEqual(config.load_session(), self.session)

    def test_server_success_local_failure_is_distinct(self):
        """磁盘删除失败单独报告：服务器已退出但本地文件仍保留。"""
        with patch.object(api_login, "clear_session", side_effect=OSError("private-path")):
            result = api_login.logout(self.client)
        self.assertFalse(result["local_cleared"])
        self.assertIn("服务器已确认退出", result["message"])
        self.assertNotIn("private-path", result["message"])
        self.assertEqual(config.load_session(), self.session)
        self.assertIsNone(self.client.session_data)

    def test_gui_service_closes_connection_success_and_failure(self):
        """适配层调用真实退出函数，成功或失败都关闭 HTTP 会话。"""
        for failure in (False, True):
            with self.subTest(failure=failure):
                config.save_session(self.session)
                self.client.session_data = dict(self.session)
                self.client.http.reset_mock()
                self.client.call.side_effect = TimeoutError() if failure else None
                with patch("funsport.api.client.ApiClient", return_value=self.client), \
                        patch.object(api_login, "login") as login:
                    if failure:
                        with self.assertRaises(RuntimeError):
                            services.logout_account()
                    else:
                        self.assertTrue(services.logout_account()["local_cleared"])
                    login.assert_not_called()
                self.client.http.close.assert_called_once()

    def test_cli_calls_shared_logout_and_closes_connection(self):
        """命令行同样等待服务器确认，失败会向上传递错误。"""
        for failure in (False, True):
            with self.subTest(failure=failure):
                config.save_session(self.session)
                self.client.session_data = dict(self.session)
                self.client.http.reset_mock()
                self.client.call.reset_mock()
                self.client.call.side_effect = TimeoutError() if failure else None
                with patch.object(cmds, "ApiClient", return_value=self.client):
                    if failure:
                        with self.assertRaises(RuntimeError):
                            cmds.cmd_logout(None)
                    else:
                        cmds.cmd_logout(None)
                self.client.call.assert_called_once_with("POST", api_login.LOGOUT_PATH, "{}")
                self.client.http.close.assert_called_once()
                self.assertEqual(config.SESSION_FILE.exists(), failure)

    def test_cli_failure_returns_nonzero(self):
        """CLI 退出失败的进程状态不是成功，日志不含底层请求秘密。"""
        from funsport.main import main
        self.client.call.side_effect = TimeoutError("fixture-token")
        with patch.object(cmds, "ApiClient", return_value=self.client), patch("sys.stderr", new=io.StringIO()) as stderr:
            with self.assertRaises(SystemExit) as caught:
                main(["logout"])
        self.assertEqual(caught.exception.code, 1)
        self.assertNotIn("fixture-token", stderr.getvalue())
        self.assertEqual(config.load_session(), self.session)

    def test_cli_local_cleanup_failure_closes_connection_and_fails(self):
        """CLI 服务器已退出但本地清理失败时，仍释放连接且不返回正常完成。"""
        with patch.object(cmds, "ApiClient", return_value=self.client), \
                patch.object(api_login, "clear_session", side_effect=OSError("fixture")):
            with self.assertRaisesRegex(RuntimeError, "服务器已确认退出"):
                cmds.cmd_logout(None)
        self.client.http.close.assert_called_once()

    def test_cli_missing_session_does_not_create_identity(self):
        """无会话的 CLI 退出不创建新设备身份，也不尝试远程请求。"""
        config.clear_session()
        with patch.object(cmds, "ApiClient") as factory:
            with self.assertRaises(ValueError):
                cmds.cmd_logout(None)
            factory.assert_not_called()
        self.assertFalse(config.IDENTITY_FILE.exists())

    def test_gui_service_without_session_never_logs_in(self):
        """已无会话时不能为了退出而自动创建身份、登录或发送请求。"""
        config.clear_session()
        with patch("funsport.api.client.ApiClient") as factory, patch.object(api_login, "login") as login:
            with self.assertRaises(ValueError):
                services.logout_account()
            factory.assert_not_called()
            login.assert_not_called()
        self.assertFalse(config.IDENTITY_FILE.exists())

    def test_new_account_login_preserves_old_session(self):
        """未退出旧账号时，不允许通过登录新账号覆盖退出所需凭据。"""
        with patch("funsport.api.client.ApiClient") as factory, patch.object(api_login, "login") as login:
            with self.assertRaisesRegex(ValueError, "先退出"):
                services.login_account("new-user", "new-password")
            factory.assert_not_called()
            login.assert_not_called()
        self.assertEqual(config.load_session(), self.session)
