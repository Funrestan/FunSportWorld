"""真实 Tk 控件的离线交互测试，所有网络接口都使用假数据。"""
import threading
import time
import tkinter as tk
from unittest.mock import Mock, patch

from tests.support import IsolatedCase
from funsport import config
from funsport.gui import App
from tests.plan_fixture import sample_plan, fake_client
from funsport.gui_services import run_parameters


class GuiTests(IsolatedCase):
    """验证窗口状态机，不测试第三方服务的有效性。"""

    def test_account_change_clears_all_views(self):
        """保存新账号或校园配置后，不保留上一个账号的详情和查询结果。"""
        self.app.rrid.set("123")
        self.app.set_report("old report")
        self.app.set_text(self.app.tools_text, "old semester")
        from funsport.gui_services import settings_snapshot
        snapshot = settings_snapshot()
        snapshot["reset_views"] = True
        self.app.apply_snapshot(snapshot)
        self.assertEqual(self.app.rrid.get(), "")
        self.assertNotIn("old", self.app.report_text.get("1.0", "end"))
        self.assertNotIn("old", self.app.tools_text.get("1.0", "end"))

    def setUp(self):
        """建立隔离窗口并将系统消息框替换为测试替身。"""
        super().setUp()
        self.root = tk.Tk()
        self.root.withdraw()
        self.map_patch = patch("funsport.gui.tkintermapview.TkinterMapView")
        self.map_patch.start()
        self.addCleanup(self.map_patch.stop)
        self.icon_patch = patch.object(App, "_icon_cache", {})
        self.icon_patch.start()
        self.addCleanup(self.icon_patch.stop)
        self.app = App(self.root)
        self.addCleanup(self.cleanup_window)
        self.error_patch = patch("funsport.gui.messagebox.showerror")
        self.errors = self.error_patch.start()
        self.addCleanup(self.error_patch.stop)

    def cleanup_window(self):
        """测试后终止本测试自己的 Tk 窗口并恢复日志处理器。"""
        if getattr(self.app, "worker", None):
            self.app.worker.join(timeout=5)
        self.app.busy = False
        self.app.close()

    def pump(self):
        """推进 Tk 事件循环直到后台任务和队列都结束。"""
        deadline = time.monotonic() + 5
        while self.app.busy or not self.app.events.empty():
            self.root.update()
            if time.monotonic() > deadline:
                self.fail("GUI task timed out")
            time.sleep(0.01)

    def preview_parameters(self):
        """直接注入预览时也包含生成按钮读取的诊断开关。"""
        params = run_parameters(self.app.values(self.app.run_vars))
        params["diagnostic_capture"] = bool(self.app.settings_vars["diagnostic_capture"].get())
        return params

    def test_startup_does_not_write_or_login(self):
        """启动只读配置，不创建身份、不保存配置、更不联网。"""
        self.assertFalse(config.CONFIG_FILE.exists())
        self.assertFalse(config.IDENTITY_FILE.exists())
        self.assertFalse(self.app.busy)
        self.assertEqual(len(self.app.tabs.tabs()), 4)
        self.assertFalse(self.app.settings_vars["diagnostic_capture"].get())

    def test_logout_cancel_never_requests(self):
        """用户取消退出确认时不发送请求、不删除本地会话。"""
        config.save_session({"uid": 1, "token": "fixture"})
        with patch("funsport.gui.messagebox.askyesno", return_value=False), \
                patch("funsport.gui.services.logout_account") as logout:
            self.app.logout()
            logout.assert_not_called()
        self.assertTrue(config.SESSION_FILE.exists())

    def test_logout_waits_for_server_and_clears_preview(self):
        """后台请求完成前保留会话；服务器成功后才清空界面和密码输入。"""
        config.save_session({"uid": 1, "token": "fixture"})
        self.app.settings_vars["password"].set("fixture-password")
        self.app.show_plan(sample_plan(), run_parameters(self.app.values(self.app.run_vars)))
        self.app.account_status.set("已登录")
        release = threading.Event()
        self.addCleanup(release.set)

        def request(*args):
            """阻塞假服务器响应以检查进行中状态，随后返回成功码。"""
            release.wait(3)
            return {"error": 10000}

        client = Mock(session_data={"uid": 1, "token": "fixture"})
        client.call.side_effect = request
        with patch("funsport.gui.messagebox.askyesno", return_value=True), \
                patch("funsport.api.client.ApiClient", return_value=client):
            self.app.logout()
            self.assertTrue(config.SESSION_FILE.exists())
            self.assertEqual(self.app.account_status.get(), "已登录")
            self.assertTrue(self.app.busy)
            self.app.logout()
            release.set()
            self.pump()
        client.call.assert_called_once_with("POST", "/api/v6/user/logout", "{}")
        client.http.close.assert_called_once()
        self.assertFalse(config.SESSION_FILE.exists())
        self.assertIsNone(self.app.plan)
        self.assertEqual(self.app.account_status.get(), "未登录")
        self.assertEqual(self.app.settings_vars["password"].get(), "")
        self.assertIn("服务器已确认退出", self.app.log_text.get("1.0", "end"))

    def test_logout_failure_preserves_account_view(self):
        """失败后恢复按钮但不清空当前方案，也不显示未登录。"""
        plan = sample_plan()
        self.app.show_plan(plan, run_parameters(self.app.values(self.app.run_vars)))
        self.app.account_status.set("已登录")
        with patch("funsport.gui.messagebox.askyesno", return_value=True), \
                patch("funsport.gui.services.logout_account", side_effect=RuntimeError("服务器退出未确认")):
            self.app.logout()
            self.pump()
        self.errors.assert_called_once()
        self.assertIs(self.app.plan, plan)
        self.assertEqual(self.app.account_status.get(), "已登录")
        self.assertFalse(self.app.busy)

    def test_logout_local_cleanup_failure_shows_partial_state(self):
        """服务器已退出但文件删除失败时，界面明确报告部分成功。"""
        self.app.show_plan(sample_plan(), run_parameters(self.app.values(self.app.run_vars)))
        result = {"local_cleared": False, "message": "服务器已确认退出，但本地清理失败"}
        with patch("funsport.gui.messagebox.showwarning") as warning:
            self.app.logout_done(result)
        warning.assert_called_once()
        self.assertIsNone(self.app.plan)
        self.assertIn("服务器已退出", self.app.account_status.get())

    def test_mode_controls(self):
        """自动模式禁用手动参数，时间模式只启用对应输入。"""
        self.assertTrue(self.app.manual_fields[0].instate(["disabled"]))
        self.app.run_vars["auto"].set(False)
        self.app.run_vars["time_mode"].set("before")
        self.app.sync_modes()
        self.assertFalse(self.app.manual_fields[0].instate(["disabled"]))
        self.assertFalse(self.app.before_entry.instate(["disabled"]))
        self.assertTrue(self.app.time_entry.instate(["disabled"]))

    def test_invalid_form_never_submits(self):
        """表单非法时不执行任何后台请求。"""
        self.app.run_vars["auto"].set(False)
        self.app.run_vars["dist"].set("NaN")
        with patch("funsport.gui.services.with_client") as client:
            self.app.submit_run()
            client.assert_not_called()
        self.errors.assert_called_once()

    def test_declined_confirmation_never_submits(self):
        """用户取消确认时不发送请求。"""
        self.app.show_plan(sample_plan(), self.preview_parameters())
        with patch("funsport.gui.messagebox.askyesno", return_value=False) as confirmation, \
                patch("funsport.gui.services.with_client") as client:
            self.app.submit_run()
            confirmation.assert_called_once()
            client.assert_not_called()

    def test_submission_displays_partial_status(self):
        """提交一次后显示结果与部分上传状态，不显示打卡已验证。"""
        result = {"rrid": 123, "dist": 1000, "dur": 400, "obs_ok": 1, "detail_ok": False}
        plan = sample_plan()
        self.app.show_plan(plan, self.preview_parameters())
        with patch("funsport.gui.messagebox.askyesno", return_value=True), \
                patch("funsport.gui.services.with_client", side_effect=lambda action: action(fake_client())), \
                patch("funsport.api.flow.submit_run_plan", return_value=result) as flow:
            self.app.submit_run()
            self.pump()
            flow.assert_called_once()
            self.assertIs(flow.call_args.args[1], plan)
        text = self.app.report_text.get("1.0", "end")
        self.assertIn("1/2", text)
        self.assertIn("未验证", text)
        self.assertEqual(self.app.rrid.get(), "123")

    def test_only_one_background_job(self):
        """首个任务未完成时，第二次点击不会产生第二个任务。"""
        release = threading.Event()
        self.addCleanup(release.set)
        self.app.start_job("test", lambda: release.wait(1))
        self.assertFalse(self.app.start_job("duplicate", lambda: None))
        self.assertTrue(all(button.instate(["disabled"]) for button in self.app.buttons))
        release.set()
        self.pump()
        self.assertTrue(all(not button.instate(["disabled"]) for button in self.app.buttons if button is not self.app.submit_button))
        self.assertTrue(self.app.submit_button.instate(["disabled"]))

    def test_generate_does_not_submit(self):
        """生成预览只执行准备阶段，提交按钮随后才启用。"""
        plan = sample_plan()
        with patch("funsport.gui.services.with_client", side_effect=lambda action: action(fake_client())), \
                patch("funsport.api.flow.prepare_run_plan", return_value=plan) as prepare, \
                patch("funsport.api.flow.submit_run_plan") as submit:
            self.app.generate_preview()
            self.pump()
            prepare.assert_called_once()
            submit.assert_not_called()
        self.assertIs(self.app.plan, plan)
        self.assertFalse(self.app.submit_button.instate(["disabled"]))

    def test_parameter_changes_invalidate_preview(self):
        """修改任何轨迹参数后旧方案失效，不能提交旧预览。"""
        self.app.show_plan(sample_plan(), run_parameters(self.app.values(self.app.run_vars)))
        self.app.run_vars["seed"].set("99")
        self.assertIsNone(self.app.plan)
        self.assertTrue(self.app.submit_button.instate(["disabled"]))
        self.assertEqual(self.app.metrics["distance"].get(), "--")

    def test_summary_uses_frozen_plan_values(self):
        """概览显示最终方案而非表单目标；换账号后不保留旧点位指标。"""
        plan = sample_plan()
        self.app.show_plan(plan, run_parameters(self.app.values(self.app.run_vars)))
        self.assertEqual(self.app.metrics["distance"].get(), "{:.2f}".format(plan.data()["track"]["totalDistance"] / 1000))
        self.assertEqual(self.app.metrics["points"].get(), str(len(plan.data()["points"])))
        self.app.clear_account_views()
        self.assertEqual(self.app.metrics["points"].get(), "--")

    def test_outside_toggle_keeps_same_preview(self):
        """时间外开关只改变提交许可，不重新生成已检查的轨迹。"""
        plan = sample_plan(outside=True)
        self.app.show_plan(plan, self.preview_parameters())
        with patch("funsport.gui.services.with_client") as client:
            self.app.submit_run()
            client.assert_not_called()
        self.app.run_vars["allow_outside"].set(True)
        self.assertIs(self.app.plan, plan)
        result = {"rrid": 123, "dist": 1000, "dur": 400, "obs_ok": 2, "detail_ok": False}
        with patch("funsport.gui.messagebox.askyesno", return_value=True), \
                patch("funsport.gui.services.with_client", side_effect=lambda action: action(fake_client())), \
                patch("funsport.api.flow.submit_run_plan", return_value=result) as submit:
            self.app.submit_run()
            self.pump()
        self.assertTrue(submit.call_args.args[2])

    def test_diagnostic_setting_is_passed_to_submit(self):
        plan = sample_plan()
        self.app.settings_vars["diagnostic_capture"].set(True)
        params = run_parameters(self.app.values(self.app.run_vars))
        params["diagnostic_capture"] = True
        self.app.show_plan(plan, params)
        self.assertIs(self.app.plan, plan)
        with patch("funsport.gui.messagebox.askyesno", return_value=True), \
                patch("funsport.gui.services.with_client", side_effect=lambda action: action(fake_client())), \
                patch("funsport.api.flow.submit_run_plan", return_value={
                    "rrid": 123, "dist": 1000, "dur": 400, "obs_ok": 2, "detail_ok": False}) as submit:
            self.app.submit_run()
            self.pump()
        self.assertTrue(submit.call_args.kwargs["diagnostic_capture"])

    def test_changing_diagnostic_setting_invalidates_existing_preview(self):
        plan = sample_plan()
        self.app.show_plan(plan, run_parameters(self.app.values(self.app.run_vars)))
        self.app.settings_vars["diagnostic_capture"].set(True)
        self.assertIsNone(self.app.plan)

    def test_map_refresh_preserves_preview(self):
        """瓦片地图刷新只重绘当前轨迹，不改变已经冻结的方案。"""
        plan = sample_plan()
        self.app.show_plan(plan, self.preview_parameters())
        self.app.map_widget.reset_mock()
        self.app.load_map()
        self.assertIs(self.app.plan, plan)
        self.app.map_widget.set_path.assert_called_once()
        self.assertEqual(self.app.map_widget.set_marker.call_count, len(plan.data()["points"]) + 2)
        self.assertIsNotNone(self.app.track_path)
        self.assertIn("高德瓦片", self.app.map_status.get())

    def test_local_preview_never_autoloads_map_or_enables_submit(self):
        """本地预览不自动加载底图；按钮与后端都不能把它当成在线方案。"""
        from funsport.run_plan import RunPlan
        data = sample_plan().data()
        data["preview_only"] = True
        data["window_ok"] = False
        data["policy"] = None
        plan = RunPlan.create(fake_client(), data)
        self.app.has_amap_key = True
        with patch("funsport.gui.services.with_client", side_effect=lambda action: action(fake_client())), \
                patch("funsport.api.flow.prepare_route_preview", return_value=plan) as prepare, \
                patch("funsport.map_preview.fetch_background") as background:
            self.app.generate_route_preview()
            self.pump()
            self.root.update()
            prepare.assert_called_once()
            background.assert_not_called()
        self.assertTrue(self.app.submit_button.instate(["disabled"]))
        self.assertFalse(self.app.run_vars["auto"].get())
        self.assertTrue(self.app.run_vars["use_map"].get())
        self.app.run_vars["allow_outside"].set(True)
        with patch("funsport.api.flow.submit_run_plan") as submit:
            self.app.submit_run()
            submit.assert_not_called()

    def test_error_restores_controls_and_redacts(self):
        """任务异常后恢复交互，且对话框和日志不含输入的密码。"""
        self.app.settings_vars["password"].set("test-secret")
        self.app.start_job("failing", Mock(side_effect=ValueError("password=test-secret")))
        self.pump()
        self.assertFalse(self.app.busy)
        self.assertNotIn("test-secret", str(self.errors.call_args))
        self.assertNotIn("test-secret", self.app.log_text.get("1.0", "end"))
        self.assertTrue(self.app.start_job("next", lambda: "done"))
        self.pump()

    def test_record_selection_and_unknown_status(self):
        """记录选择仅填 ID，未返回的达标状态显示未知。"""
        self.app.show_records([{"rrid": 123, "start_time": 1000, "total_dis": 1000, "total_time": 400}])
        iid = self.app.record_tree.get_children()[0]
        self.app.record_tree.selection_set(iid)
        self.app.select_record()
        self.assertEqual(self.app.rrid.get(), "123")
        self.assertIn("未知", self.app.record_tree.item(iid, "values"))

    def test_close_while_busy_is_blocked(self):
        """提交中不直接退出，避免用户无法判断记录是否已经写入。"""
        self.app.busy = True
        with patch("funsport.gui.messagebox.showinfo") as notice:
            self.app.close()
            notice.assert_called_once()
        self.assertTrue(self.root.winfo_exists())
        self.app.busy = False
