"""Tkinter 桌面窗口：主线程负责界面，单个后台线程负责网络任务。"""
import logging
import queue
import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import tkintermapview
from PIL import Image, ImageDraw, ImageTk

from . import gui_services as services
from .run_plan import format_plan
from .track.wire import five_point_payload, bd09_to_gcj02
from .diagnostics import analyze_checkpoints, format_report, inspect_file
from .logger import log


def configure_theme(root):
    """统一桌面配色、控件密度与焦点反馈，使用系统字体且不增加依赖。"""
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure(".", font=("Microsoft YaHei UI", 10), background="#f5f7fa", foreground="#242c36")
    style.configure("TFrame", background="#f5f7fa")
    style.configure("TLabel", background="#f5f7fa")
    style.configure("Muted.TLabel", foreground="#667383")
    style.configure("Section.TLabel", font=("Microsoft YaHei UI", 10, "bold"))
    style.configure("Heading.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
    style.configure("Metric.TLabel", font=("Microsoft YaHei UI", 17, "bold"), foreground="#1975ba")
    style.configure("TButton", padding=(12, 7), background="#ffffff", bordercolor="#dbe1e8",
                    lightcolor="#ffffff", darkcolor="#ffffff", focuscolor="#dbe1e8", borderwidth=1)
    style.map("TButton", background=[("active", "#eaf0f5"), ("disabled", "#f0f2f5")],
              foreground=[("disabled", "#8d98a5")])
    style.configure("Accent.TButton", foreground="#ffffff", background="#137c65", borderwidth=0)
    style.map("Accent.TButton", background=[("disabled", "#dbe7e2"), ("active", "#0f6553")],
              foreground=[("disabled", "#80958d"), ("!disabled", "#ffffff")])
    style.configure("TEntry", padding=5, fieldbackground="#ffffff", bordercolor="#dbe1e8")
    style.map("TEntry", fieldbackground=[("disabled", "#edf0f4")], bordercolor=[("focus", "#137c65")])
    style.configure("TNotebook", borderwidth=0, bordercolor="#f5f7fa", lightcolor="#f5f7fa",
                    darkcolor="#f5f7fa", tabmargins=(0, 0, 0, 8))
    style.configure("TNotebook.Tab", padding=(18, 9), background="#e9edf2", borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", "#ffffff"), ("active", "#eef3f6")],
              foreground=[("selected", "#137c65")])
    style.configure("Treeview", rowheight=32, background="#ffffff", fieldbackground="#ffffff", borderwidth=0)
    style.configure("Treeview.Heading", padding=(8, 8), background="#eaf0f5", relief="flat")
    style.map("Treeview", background=[("selected", "#e0f0eb")], foreground=[("selected", "#174c40")])
    style.configure("Horizontal.TProgressbar", background="#137c65", troughcolor="#e8edf2", borderwidth=0)


class QueueLogHandler(logging.Handler):
    """将日志送入线程安全队列，不从工作线程操作窗口。"""

    def __init__(self, events):
        super().__init__()
        self.events = events

    def emit(self, record):
        self.events.put(("log", record.getMessage(), None))


class App:
    """连接表单、后台任务和已有 API，不在启动时发送网络请求。"""

    # 图标缓存（避免 PhotoImage 被 GC）
    _icon_cache = {}

    @classmethod
    def _make_circle_icon(cls, fill, size=28, outline="#ffffff",
                          outline_width=2, text=""):
        """橙色实心圆 + 白色编号（Canvas 版打卡点样式）。"""
        key = ("circle", fill, size, outline, outline_width, text)
        if key in cls._icon_cache:
            return cls._icon_cache[key]
        pad = outline_width
        img = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([pad, pad, pad + size, pad + size],
                  fill=fill, outline=outline, width=outline_width)
        if text:
            try:
                from PIL import ImageFont
                font = None
                for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf"):
                    try:
                        font = ImageFont.truetype(name, size=int(size * 0.55))
                        break
                    except Exception:
                        continue
                if font is None:
                    font = ImageFont.load_default()
                bbox = d.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                d.text((pad + (size - tw) / 2 - bbox[0],
                        pad + (size - th) / 2 - bbox[1]),
                       text, fill="white", font=font)
            except Exception:
                pass
        photo = ImageTk.PhotoImage(img)
        cls._icon_cache[key] = photo
        return photo

    @classmethod
    def _make_square_icon(cls, fill, size=26, outline="#ffffff",
                          outline_width=2, text=""):
        """方块 + 文字（Canvas 版起终点样式）。"""
        key = ("sq", fill, size, outline, outline_width, text)
        if key in cls._icon_cache:
            return cls._icon_cache[key]
        pad = outline_width
        img = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle([pad, pad, pad + size, pad + size],
                    fill=fill, outline=outline, width=outline_width)
        if text:
            try:
                from PIL import ImageFont
                font = None
                for name in ("msyh.ttc", "msyhbd.ttc", "simhei.ttf"):
                    try:
                        font = ImageFont.truetype(name, size=int(size * 0.65))
                        break
                    except Exception:
                        continue
                if font is None:
                    font = ImageFont.load_default()
                bbox = d.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                d.text((pad + (size - tw) / 2 - bbox[0],
                        pad + (size - th) / 2 - bbox[1]),
                       text, fill="white", font=font)
            except Exception:
                pass
        photo = ImageTk.PhotoImage(img)
        cls._icon_cache[key] = photo
        return photo

    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.buttons = []
        self.points = []
        self.plan = None
        self.preview_parameters = None
        self.preview_track = None
        # tkintermapview 元素引用
        self.map_widget = None
        self.track_path = None
        self.start_marker = None
        self.end_marker = None
        self.checkpoint_markers = []
        self.point_markers = []
        self.has_amap_key = False
        self.secrets = []
        self.run_vars, self.settings_vars = {}, {}
        self.old_handlers = list(log.handlers)
        self.log_handler = QueueLogHandler(self.events)
        log.handlers = [self.log_handler]
        root.title("FunSportWorld")
        root.geometry("1120x820")
        root.minsize(960, 760)
        root.configure(background="#f5f7fa")
        root.protocol("WM_DELETE_WINDOW", self.close)
        configure_theme(root)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        header = ttk.Frame(root, padding=(20, 14))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="FunSportWorld", style="Heading.TLabel").pack(side="left")
        ttk.Label(header, text="路线工作台", style="Muted.TLabel").pack(side="left", padx=18)
        self.account_status = tk.StringVar(value="未登录")
        ttk.Label(header, textvariable=self.account_status, style="Muted.TLabel").pack(side="right")
        self.tabs = ttk.Notebook(root)
        self.tabs.grid(row=1, column=0, padx=18, sticky="nsew")
        self.run_page = self.page("跑步")
        self.record_page = self.page("记录与诊断")
        self.tools_page = self.page("数据查询")
        self.settings_page = self.page("设置与登录")
        self.build_run()
        self.build_records()
        self.build_tools()
        self.build_settings()
        logs = ttk.Frame(root, padding=(18, 8))
        logs.grid(row=2, column=0, sticky="ew")
        logs.columnconfigure(0, weight=1)
        ttk.Label(logs, text="运行日志").grid(row=0, column=0, sticky="w")
        ttk.Button(logs, text="清空", command=self.clear_log).grid(row=0, column=1)
        self.log_text = ScrolledText(logs, height=4, wrap="word", state="disabled",
                                    font=("Consolas", 10), background="#ffffff", relief="flat")
        self.log_text.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        footer = ttk.Frame(root, padding=(18, 0, 18, 10))
        footer.grid(row=3, column=0, sticky="ew")
        self.status = tk.StringVar(value="就绪")
        ttk.Label(footer, textvariable=self.status).pack(side="left")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=150)
        self.progress.pack(side="right")
        try:
            self.apply_snapshot(services.settings_snapshot())
        except ValueError as exc:
            self.status.set("本地配置读取失败")
            self.append_log(str(exc))
        for key, var in self.run_vars.items():
            if key != "allow_outside":
                var.trace_add("write", self.invalidate_plan)
        for var in self.settings_vars.values():
            var.trace_add("write", self.invalidate_plan)
        self.refresh_submit_state()
        self.poll_id = root.after(80, self.poll)

    def page(self, title):
        frame = ttk.Frame(self.tabs, padding=(16, 10))
        self.tabs.add(frame, text=title)
        return frame

    def button(self, parent, text, command, accent=False):
        button = ttk.Button(parent, text=text, command=command,
                            style="Accent.TButton" if accent else "TButton")
        self.buttons.append(button)
        return button

    def entry(self, parent, row, label, store, key, default="", secret=False, padding=6):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=padding, padx=(0, 14))
        var = tk.StringVar(value=default)
        store[key] = var
        widget = ttk.Entry(parent, textvariable=var, width=21, show="*" if secret else "")
        widget.grid(row=row, column=1, sticky="ew", pady=padding)
        return widget

    def build_run(self):
        self.run_page.columnconfigure(1, weight=1)
        self.run_page.rowconfigure(0, weight=1)
        form = ttk.Frame(self.run_page)
        form.grid(row=0, column=0, sticky="nsw", padx=(0, 18))
        self.run_vars["auto"] = tk.BooleanVar(value=True)
        modes = ttk.Frame(form)
        modes.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Radiobutton(modes, text="自动参数", variable=self.run_vars["auto"], value=True,
                        command=self.sync_modes).pack(side="left")
        ttk.Radiobutton(modes, text="手动参数", variable=self.run_vars["auto"], value=False,
                        command=self.sync_modes).pack(side="left", padx=16)
        self.manual_fields = [self.entry(form, 1, "距离 / km", self.run_vars, "dist", "2.8", padding=3),
                              self.entry(form, 2, "配速 / 秒每公里", self.run_vars, "pace", "400", padding=3),
                              self.entry(form, 3, "步频 / 步每分钟", self.run_vars, "cadence", "160", padding=3)]
        self.run_vars["use_map"] = tk.BooleanVar(value=True)
        ttk.Label(form, text="高德步行 API", style="Muted.TLabel").grid(row=4, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Separator(form).grid(row=5, column=0, columnspan=2, sticky="ew", pady=4)
        self.run_vars["time_mode"] = tk.StringVar(value="config")
        times = ttk.Frame(form)
        times.grid(row=6, column=0, columnspan=2, sticky="ew", pady=4)
        for text, value in (("配置范围", "config"), ("固定提前", "before"), ("指定时间", "at")):
            ttk.Radiobutton(times, text=text, variable=self.run_vars["time_mode"], value=value,
                            command=self.sync_modes).pack(side="left", padx=(0, 8))
        self.before_entry = self.entry(form, 7, "提前 / 分钟", self.run_vars, "before", "60", padding=3)
        start = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
        self.time_entry = self.entry(form, 8, "开始时间", self.run_vars, "start_at", start, padding=3)
        self.entry(form, 9, "随机种子（0=自动）", self.run_vars, "seed", "0", padding=3)
        self.run_vars["allow_outside"] = tk.BooleanVar(value=False)
        outside_check = ttk.Checkbutton(form, text="跳过本地时间检查（测试）", variable=self.run_vars["allow_outside"])
        outside_check.grid(row=10, column=0, columnspan=2, sticky="w", pady=6)
        self.add_tooltip(outside_check, "仅跳过本地检查，服务器仍可能返回 11016")
        actions = ttk.Frame(form)
        actions.grid(row=11, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.button(actions, "在线预览", self.generate_preview, True).pack(side="left", expand=True, fill="x")
        route_preview = self.button(actions, "轨迹预览", self.generate_route_preview)
        route_preview.pack(side="left", expand=True, fill="x", padx=(6, 0))
        self.add_tooltip(route_preview, "使用缓存点位和高德路线；不访问运动服务，不可提交")
        self.submit_button = self.button(actions, "提交此方案", self.submit_run)
        self.submit_button.pack(side="left", expand=True, fill="x", padx=(6, 0))
        self.plan_status = tk.StringVar(value="尚未生成方案")
        ttk.Label(form, textvariable=self.plan_status, wraplength=305).grid(
            row=12, column=0, columnspan=2, sticky="w", pady=4)

        self.preview_tabs = ttk.Notebook(self.run_page)
        self.preview_tabs.grid(row=0, column=1, sticky="nsew")
        preview = ttk.Frame(self.preview_tabs, padding=(4, 8))
        details = ttk.Frame(self.preview_tabs, padding=8)
        self.preview_tabs.add(preview, text="地图预览")
        self.preview_tabs.add(details, text="方案明细")
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(2, weight=1)
        summary = ttk.Frame(preview)
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.metrics = {}
        for column, (key, label) in enumerate((("distance", "距离 / km"), ("duration", "时长 / 分:秒"), ("points", "打卡点"))):
            summary.columnconfigure(column, weight=1, uniform="metric")
            cell = ttk.Frame(summary)
            cell.grid(row=0, column=column, sticky="ew")
            ttk.Label(cell, text=label, style="Muted.TLabel").pack(anchor="w")
            self.metrics[key] = tk.StringVar(value="--")
            ttk.Label(cell, textvariable=self.metrics[key], style="Metric.TLabel").pack(anchor="w")
        bar = ttk.Frame(preview)
        bar.grid(row=1, column=0, sticky="ew")
        self.button(bar, "读取点位", self.load_points).pack(side="left")
        self.button(bar, "加载底图", self.load_map).pack(side="left", padx=4)
        fit_button = self.button(bar, "↔", self.fit_map)
        fit_button.configure(width=3)
        fit_button.pack(side="left")
        self.add_tooltip(fit_button, "适配全部轨迹与点位")
        zoom_out = self.button(bar, "-", lambda: self.change_zoom(-1))
        zoom_out.configure(width=3)
        zoom_out.pack(side="right")
        zoom_in = self.button(bar, "+", lambda: self.change_zoom(1))
        zoom_in.configure(width=3)
        zoom_in.pack(side="right", padx=4)
        self.add_tooltip(zoom_in, "放大地图")
        self.add_tooltip(zoom_out, "缩小地图")

        # ── tkintermapview 地图控件 ──
        map_frame = ttk.Frame(preview)
        map_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 8))
        map_frame.columnconfigure(0, weight=1)
        map_frame.rowconfigure(0, weight=1)
        self.map_widget = tkintermapview.TkinterMapView(map_frame, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True)
        self.map_widget.set_tile_server(
            "https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
            max_zoom=19,
        )
        self.map_widget.set_position(30.8885, 103.5965)
        self.map_widget.set_zoom(16)

        self.map_status = tk.StringVar(value="GCJ-02 / 高德瓦片")
        ttk.Label(preview, textvariable=self.map_status, wraplength=400,
                  style="Muted.TLabel").grid(row=3, column=0, sticky="ew")
        details.columnconfigure(0, weight=1)
        details.rowconfigure(0, weight=1)
        self.plan_text = ScrolledText(details, state="disabled", wrap="word", width=35, height=12,
                                      font=("Microsoft YaHei UI", 10), relief="flat")
        self.plan_text.grid(row=0, column=0, sticky="nsew")
        self.point_tree = self.table(details, ("名称", "顺序", "源通过状态", "最近采样距离 / m"), (130, 70, 110, 150), height=4)
        self.point_tree.master.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.sync_modes()

    def table(self, parent, columns, widths, height=6):
        frame = ttk.Frame(parent)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=height, selectmode="browse")
        for name, width in zip(columns, widths):
            tree.heading(name, text=name)
            tree.column(name, width=width, minwidth=70, stretch=True)
        vertical = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        return tree

    def build_records(self):
        self.record_page.columnconfigure(0, weight=1)
        self.record_page.rowconfigure(2, weight=1)
        bar = ttk.Frame(self.record_page)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.button(bar, "刷新记录", self.load_records).pack(side="left")
        ttk.Label(bar, text="记录 ID").pack(side="left", padx=(20, 8))
        self.rrid = tk.StringVar()
        ttk.Entry(bar, textvariable=self.rrid, width=19).pack(side="left")
        self.button(bar, "查询并诊断", self.diagnose_record).pack(side="left", padx=8)
        self.button(bar, "打开本地 JSON", self.open_diagnostic).pack(side="right")
        self.record_tree = self.table(self.record_page, ("开始时间", "距离 / m", "时长 / s", "服务端达标", "记录 ID"),
                                      (190, 110, 110, 110, 150), height=5)
        self.record_tree.master.grid(row=1, column=0, sticky="ew")
        self.record_tree.bind("<<TreeviewSelect>>", self.select_record)
        self.report_text = ScrolledText(self.record_page, wrap="word", state="disabled",
                                        font=("Microsoft YaHei UI", 10), relief="flat", height=10)
        self.report_text.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        self.set_report("尚未选择记录")

    def build_tools(self):
        self.tools_page.columnconfigure(0, weight=1)
        self.tools_page.rowconfigure(1, weight=1)
        bar = ttk.Frame(self.tools_page)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self.query_kind = tk.StringVar(value="学校跑步策略")
        ttk.Combobox(bar, textvariable=self.query_kind, state="readonly", width=24,
                     values=("学校跑步策略", "学期完成度", "个人日榜", "AI 运动项目")).pack(side="left")
        self.button(bar, "查询", self.query_data).pack(side="left", padx=10)
        self.tools_text = ScrolledText(self.tools_page, state="disabled", wrap="word",
                                       relief="flat", font=("Microsoft YaHei UI", 11))
        self.tools_text.grid(row=1, column=0, sticky="nsew")

    def build_settings(self):
        form = ttk.Frame(self.settings_page)
        form.pack(anchor="nw")
        self.entry(form, 0, "账号 / 手机号", self.settings_vars, "username")
        self.entry(form, 1, "密码", self.settings_vars, "password", secret=True)
        self.settings_vars["remember"] = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="记住密码（本地明文）", variable=self.settings_vars["remember"]).grid(
            row=2, column=1, sticky="w", pady=6)
        self.entry(form, 3, "城市", self.settings_vars, "city", "成都市")
        self.entry(form, 4, "纬度 / BD-09", self.settings_vars, "anchor_lat")
        self.entry(form, 5, "经度 / BD-09", self.settings_vars, "anchor_lon")
        self.entry(form, 6, "高德 Key", self.settings_vars, "amap_key", secret=True)
        self.settings_vars["clear_amap"] = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="清除已保存的高德 Key", variable=self.settings_vars["clear_amap"]).grid(
            row=7, column=1, sticky="w", pady=6)
        self.entry(form, 8, "最短提前 / 分钟", self.settings_vars, "start_before_min", "30")
        self.entry(form, 9, "最长提前 / 分钟", self.settings_vars, "start_before_max", "300")
        self.settings_vars["diagnostic_capture"] = tk.BooleanVar(value=False)
        diagnostic_check = ttk.Checkbutton(
            form, text="保存跑步通信消息汇总（开发用，一般用户不用开启）",
            variable=self.settings_vars["diagnostic_capture"])
        diagnostic_check.grid(row=10, column=1, sticky="w", pady=6)
        self.add_tooltip(diagnostic_check,
                         "记录在线预览、提交、OBS 和详情查询的请求与响应；包含精确位置，仅保存在本地，不额外发送逐点事件。")
        bar = ttk.Frame(form)
        bar.grid(row=11, column=0, columnspan=2, sticky="w", pady=14)
        self.button(bar, "保存设置", self.save_settings, True).pack(side="left")
        self.button(bar, "登录", self.login).pack(side="left", padx=10)
        self.button(bar, "退出登录", self.logout).pack(side="left")
        self.saved_status = tk.StringVar()
        ttk.Label(form, textvariable=self.saved_status).grid(
            row=0, column=2, rowspan=3, sticky="nw", padx=(28, 0), pady=6)

    def sync_modes(self):
        for widget in self.manual_fields:
            widget.configure(state="disabled" if self.run_vars["auto"].get() else "normal")
        if not self.run_vars["use_map"].get():
            self.run_vars["use_map"].set(True)
        mode = self.run_vars["time_mode"].get()
        self.before_entry.configure(state="normal" if mode == "before" else "disabled")
        self.time_entry.configure(state="normal" if mode == "at" else "disabled")

    def values(self, store):
        return {key: var.get() for key, var in store.items()}

    def apply_snapshot(self, snapshot):
        if snapshot.get("reset_views"):
            self.clear_account_views()
        for key, value in snapshot.items():
            if key in self.settings_vars:
                self.settings_vars[key].set(value)
        self.settings_vars["clear_amap"].set(False)
        self.has_amap_key = snapshot["has_amap_key"]
        self.account_status.set("已有本地会话（有效性待联网确认）" if snapshot["logged_in"] else "未登录")
        self.saved_status.set("已保存密码：{}    高德 Key：{}".format(
            "是" if snapshot["has_password"] else "否", "已配置" if snapshot["has_amap_key"] else "未配置"))

    def start_job(self, title, action, callback=None):
        if self.busy:
            return False
        self.secrets = [self.settings_vars[key].get() for key in ("username", "password", "amap_key")]
        self.busy = True
        self.status.set(title + "…")
        self.progress.start(12)
        for button in self.buttons:
            button.configure(state="disabled")
        self.locked_inputs = [widget for widget in self.input_widgets(self.root)
                              if not widget.instate(["disabled"])]
        for widget in self.locked_inputs:
            widget.state(["disabled"])

        def work():
            try:
                result = action()
                self.events.put(("done", result, callback))
            except (Exception, SystemExit) as exc:
                self.events.put(("error", str(exc), None))

        self.worker = threading.Thread(target=work, daemon=True, name="funsport-gui")
        self.worker.start()
        return True

    def input_widgets(self, parent):
        for widget in parent.winfo_children():
            if isinstance(widget, (ttk.Entry, ttk.Checkbutton, ttk.Radiobutton, ttk.Combobox)):
                yield widget
            yield from self.input_widgets(widget)

    def poll(self):
        for _ in range(150):
            try:
                kind, value, callback = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.append_log(value)
                continue
            self.busy = False
            self.progress.stop()
            for button in self.buttons:
                button.configure(state="normal")
            for widget in self.locked_inputs:
                widget.state(["!disabled"])
            if kind == "error":
                self.status.set("操作失败")
                self.show_error(value)
            else:
                self.status.set("操作完成")
                try:
                    if callback:
                        callback(value)
                    elif value is not None:
                        self.append_log(str(value))
                except Exception as exc:
                    self.show_error(str(exc))
            self.refresh_submit_state()
        self.poll_id = self.root.after(80, self.poll)

    def append_log(self, message):
        text = services.safe_text(message, self.secrets)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", datetime.now().strftime("%H:%M:%S ") + text + "\n")
        if int(self.log_text.index("end-1c").split(".")[0]) > 600:
            self.log_text.delete("1.0", "101.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def show_error(self, message):
        text = services.safe_text(message, self.secrets)
        self.append_log(text)
        messagebox.showerror("操作失败", text, parent=self.root)

    def save_settings(self):
        values = self.values(self.settings_vars)
        if values["remember"] and values["password"]:
            if not messagebox.askyesno("保存密码", "密码将明文保存在本机 .funsport 目录。继续？", parent=self.root):
                return
        self.start_job("保存设置", lambda: services.save_settings(values), self.apply_snapshot)

    def login(self):
        values = self.values(self.settings_vars)
        self.start_job("登录", lambda: services.login_account(values["username"], values["password"]), self.login_done)

    def login_done(self, result):
        self.settings_vars["password"].set("")
        self.account_status.set("已登录")
        self.clear_account_views()
        self.append_log(result)

    def logout(self):
        if self.busy:
            return
        if messagebox.askyesno("退出登录", "向服务器退出当前账号？\n服务器确认成功后清除本地会话；失败则保留会话。", parent=self.root):
            self.start_job("请求服务器退出", services.logout_account, self.logout_done)

    def logout_done(self, result):
        self.account_status.set("未登录" if result["local_cleared"] else "服务器已退出（本地清理失败）")
        self.settings_vars["password"].set("")
        self.clear_account_views()
        self.append_log(result["message"])
        self.status.set("已退出登录" if result["local_cleared"] else "服务器已退出，本地清理失败")
        if not result["local_cleared"]:
            messagebox.showwarning("退出后的本地清理失败", result["message"], parent=self.root)

    def clear_account_views(self):
        self.points = []
        self.invalidate_plan()
        self.point_tree.delete(*self.point_tree.get_children())
        self.record_tree.delete(*self.record_tree.get_children())
        self.rrid.set("")
        self.set_report("尚未选择记录")
        self.set_text(self.tools_text, "")
        self.clear_log()
        self.draw_points()

    def load_points(self):
        from .api.points import fetch_points
        self.start_job("读取打卡点", lambda: services.with_client(fetch_points), self.show_points)

    def show_points(self, points):
        normalized = five_point_payload(points, 0)
        self.invalidate_plan()
        self.points = normalized
        self.metrics["points"].set(str(len(normalized)))
        self.point_tree.delete(*self.point_tree.get_children())
        for point in normalized:
            self.point_tree.insert("", "end", values=(point.get("pointName", ""), point["position"], "是" if point["isPass"] else "否/未提供", "未生成"))
        self.fit_map()
        self.set_report(format_report(analyze_checkpoints({"pointsResModels": points})))
        if self.has_amap_key:
            self.root.after_idle(self.load_map)

    def draw_points(self, event=None):
        """按 Canvas 版原样式绘制：绿方块"起"、红方块"终"、橙圆+编号打卡点。"""
        import traceback
        try:
            if self.map_widget is None:
                return

            # 清除旧轨迹与标记
            for attr in ("track_path", "start_marker", "end_marker"):
                obj = getattr(self, attr, None)
                if obj is not None:
                    try:
                        obj.delete()
                    except Exception:
                        pass
                    setattr(self, attr, None)
            for attr in ("checkpoint_markers", "point_markers"):
                for m in getattr(self, attr, []) or []:
                    try:
                        m.delete()
                    except Exception:
                        pass
                setattr(self, attr, [])

            # ── 轨迹折线 ──
            coords = []
            if self.preview_track:
                for i, p in enumerate(self.preview_track.get("locations", []) or []):
                    if p.get("type") == -1:
                        continue
                    try:
                        glat, glng = bd09_to_gcj02(p["gLat"], p["gLng"])
                        coords.append((glat, glng))
                    except Exception as e:
                        print(f"[draw_points] 点 {i} 坐标转换失败: {e}", flush=True)

            print(f"[draw_points] coords 数量={len(coords)}", flush=True)
            if coords:
                self.track_path = self.map_widget.set_path(
                    coords, color="#00c18b", width=3
                )
                lats = [c[0] for c in coords]
                lngs = [c[1] for c in coords]
                self.map_widget.set_position((min(lats) + max(lats)) / 2,
                                             (min(lngs) + max(lngs)) / 2)
                span = max(max(lats) - min(lats), max(lngs) - min(lngs))
                if span > 0.05:
                    zoom = 13
                elif span > 0.02:
                    zoom = 14
                elif span > 0.01:
                    zoom = 15
                elif span > 0.005:
                    zoom = 16
                else:
                    zoom = 17
                self.map_widget.set_zoom(zoom)

            # ── 打卡点：橙色实心圆 + 白色编号 ──
            for index, point in enumerate(self.points, 1):
                lat, lng = point["glat"], point["glon"]
                icon = self._make_circle_icon(
                    "#bb7412", size=28, outline="#ffffff",
                    outline_width=2, text=str(index)
                )
                m = self.map_widget.set_marker(lat, lng, icon=icon)
                self.checkpoint_markers.append(m)
            print(f"[draw_points] 打卡点 {len(self.checkpoint_markers)} 个", flush=True)

            # ── 起点：绿方块"起" / 终点：红方块"终" ──
            if coords:
                start_icon = self._make_square_icon(
                    "#157448", size=26, outline="#ffffff",
                    outline_width=2, text="起"
                )
                end_icon = self._make_square_icon(
                    "#b13946", size=26, outline="#ffffff",
                    outline_width=2, text="终"
                )
                self.start_marker = self.map_widget.set_marker(
                    coords[0][0], coords[0][1], icon=start_icon
                )
                self.end_marker = self.map_widget.set_marker(
                    coords[-1][0], coords[-1][1], icon=end_icon
                )
                print("[draw_points] 起终点完成", flush=True)
        except Exception:
            print("[draw_points] 顶层异常：", flush=True)
            traceback.print_exc()

    def add_tooltip(self, widget, text):
        popup = []

        def leave(event=None):
            if popup:
                popup.pop().destroy()

        def enter(event=None):
            leave()
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.geometry("+{}+{}".format(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height() + 3))
            ttk.Label(tip, text=text, padding=5).pack()
            popup.append(tip)

        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def fit_map(self):
        """适配所有点位和轨迹。"""
        if self.map_widget is None:
            return
        coords = [(p["glat"], p["glon"]) for p in self.points]
        if self.preview_track:
            for p in self.preview_track.get("locations", []):
                if p.get("type") == -1:
                    continue
                try:
                    glat, glng = bd09_to_gcj02(p["gLat"], p["gLng"])
                    coords.append((glat, glng))
                except Exception:
                    pass
        if not coords:
            return
        lats = [c[0] for c in coords]
        lngs = [c[1] for c in coords]
        self.map_widget.set_position((min(lats) + max(lats)) / 2,
                                     (min(lngs) + max(lngs)) / 2)
        span = max(max(lats) - min(lats), max(lngs) - min(lngs))
        if span > 0.05:
            zoom = 13
        elif span > 0.02:
            zoom = 14
        elif span > 0.01:
            zoom = 15
        elif span > 0.005:
            zoom = 16
        else:
            zoom = 17
        self.map_widget.set_zoom(zoom)
        self.map_status.set("GCJ-02 / 高德瓦片 / 缩放 {}".format(zoom))
        self.draw_points()

    def change_zoom(self, delta):
        if self.map_widget is None or self.busy:
            return
        try:
            current = self.map_widget.zoom
        except Exception:
            current = 16
        new_zoom = max(1, min(19, current + delta))
        self.map_widget.set_zoom(new_zoom)
        self.map_status.set("GCJ-02 / 高德瓦片 / 缩放 {}".format(new_zoom))

    def load_map(self):
        """tkintermapview 自动加载瓦片，只需重绘。"""
        self.fit_map()

    def invalidate_plan(self, *args):
        had_plan = self.plan is not None
        self.plan = None
        self.preview_parameters = None
        self.preview_track = None
        for key, var in self.metrics.items():
            var.set(str(len(self.points)) if key == "points" and self.points else "--")
        if had_plan:
            self.plan_status.set("参数已变化，请重新生成方案")
            self.set_text(self.plan_text, "方案已失效")
            self.draw_points()
        self.refresh_submit_state()

    def refresh_submit_state(self):
        ready = (self.plan is not None and not self.plan.attempted and not self.busy
                 and not self.plan.data().get("preview_only"))
        self.submit_button.configure(state="normal" if ready else "disabled")

    def generate_preview(self):
        from .api.flow import prepare_run_plan
        try:
            params = services.run_parameters(self.values(self.run_vars))
        except ValueError as exc:
            self.show_error(str(exc))
            return
        params["diagnostic_capture"] = bool(self.settings_vars["diagnostic_capture"].get())
        self.invalidate_plan()
        self.start_job("生成在线方案预览",
                       lambda: services.with_client(lambda client: prepare_run_plan(client, **params)),
                       lambda plan: self.show_plan(plan, params))

    def generate_route_preview(self):
        from .api.flow import prepare_route_preview
        self.run_vars["auto"].set(False)
        self.run_vars["use_map"].set(True)
        self.sync_modes()
        try:
            params = services.run_parameters(self.values(self.run_vars))
        except ValueError as exc:
            self.show_error(str(exc))
            return
        params["diagnostic_capture"] = bool(self.settings_vars["diagnostic_capture"].get())
        local_params = {key: value for key, value in params.items()
                        if key in ("dist", "pace", "cadence", "start_ms", "before", "seed")}
        self.invalidate_plan()
        self.start_job("生成高德轨迹预览",
                       lambda: services.with_client(lambda client: prepare_route_preview(client, **local_params)),
                       lambda plan: self.show_plan(plan, params))

    def show_plan(self, plan, parameters):
        data = plan.data()
        self.plan = plan
        self.preview_parameters = dict(parameters)
        self.preview_parameters.pop("allow_outside_window", None)
        self.preview_track = data["track"]
        self.points = data["points"]
        self.metrics["distance"].set("{:.2f}".format(self.preview_track["totalDistance"] / 1000))
        minutes, seconds = divmod(int(self.preview_track["totalTime"]), 60)
        self.metrics["duration"].set("{}:{:02d}".format(minutes, seconds))
        self.metrics["points"].set(str(len(self.points)))
        self.point_tree.delete(*self.point_tree.get_children())
        for point, distance in zip(self.points, data["checkpoint_distances"]):
            self.point_tree.insert("", "end", values=(point["pointName"], point["position"],
                                                       "是" if point["isPass"] else "否/未提供", distance))
        self.set_text(self.plan_text, format_plan(plan))
        window_label = ("仅预览，不可提交" if data.get("preview_only") else "时段未提供" if not data["valid_time"] else
                        "有效时段内" if data["window_ok"] else "有效时段外")
        self.plan_status.set("方案 {}\n{:.0f} m / {} s / {}".format(plan.plan_id, data["track"]["totalDistance"],
            data["track"]["totalTime"], window_label))
        self.preview_tabs.select(0)
        self.fit_map()
        self.refresh_submit_state()

    def submit_run(self):
        from .api.flow import submit_run_plan
        if self.plan is None:
            self.show_error("请先生成并检查方案预览")
            return
        try:
            params = services.run_parameters(self.values(self.run_vars))
        except ValueError as exc:
            self.show_error(str(exc))
            return
        diagnostic_capture = bool(self.settings_vars["diagnostic_capture"].get())
        params["diagnostic_capture"] = diagnostic_capture
        outside = bool(params.pop("allow_outside_window", False))
        if params != self.preview_parameters:
            self.invalidate_plan()
            self.show_error("参数已变化，请重新生成方案")
            return
        plan = self.plan
        data = plan.data()
        if data.get("preview_only"):
            self.show_error("轨迹预览没有学校策略，不允许提交。请在开放时段重新生成在线方案。")
            return
        if not data["window_ok"] and not outside:
            self.show_error("方案不符合本地时段检查。测试开关只能跳过本地检查，不能改变服务器限制。")
            return
        notice = "\n已跳过本地时间检查；服务器限制仍生效，可能返回 11016。" if outside else ""
        if diagnostic_capture:
            notice += "\n本次会保存通信记录及精确路线/点位到本地诊断包。"
        completion = data.get("completion") or {}
        if completion.get("complete") is True:
            run_state = "本地判定为满足"
        elif completion.get("complete") is False:
            run_state = "本地判定为未满足（{}）".format(
                completion.get("unCompleteReason", "未知原因"))
        else:
            run_state = "本地判定未知"
        confirm_text = ("当前跑步状态为：{}。\n\n{}{}"
                        "\n\n将提交当前预览数据，不能在这里撤销。继续？").format(
                            run_state, format_plan(plan), notice)
        if not messagebox.askyesno("确认提交方案", confirm_text, parent=self.root):
            return
        self.start_job("提交方案 " + plan.plan_id,
                       lambda: services.with_client(lambda client: submit_run_plan(
                           client, plan, outside, diagnostic_capture=diagnostic_capture)),
                       self.run_done)

    def run_done(self, result):
        self.rrid.set(str(result["rrid"]))
        summary = "记录 ID：{}\n距离：{:.0f} m\n时长：{} s\nOBS 上传：{}/2\n详情读取：{}\n".format(
            result["rrid"], result["dist"], result["dur"], result["obs_ok"], "成功" if result["detail_ok"] else "失败")
        report = result.get("checkpoint_report")
        if report:
            summary += "\n" + format_report(report)
        else:
            summary += "\n打卡点显示未验证。"
        if result.get("diagnostic_dir"):
            summary += "\n诊断数据：{}".format(result["diagnostic_dir"])
        self.set_report(summary)
        self.tabs.select(self.record_page)
        self.append_log("提交阶段已结束，请查看记录与诊断；勿因显示缺失重复提交。")

    def load_records(self):
        from .api.records import fetch_records
        self.start_job("刷新记录", lambda: services.with_client(fetch_records), self.show_records)

    def show_records(self, rows):
        self.record_tree.delete(*self.record_tree.get_children())
        for record in rows:
            stamp = datetime.fromtimestamp(record["start_time"] / 1000).strftime("%Y-%m-%d %H:%M")
            complete = record.get("complete")
            state = "是" if complete is True else "否" if complete is False else "未知"
            self.record_tree.insert("", "end", values=(stamp, record["total_dis"], record["total_time"], state, record["rrid"]))
        self.status.set("已读取 {} 条记录".format(len(rows)))

    def select_record(self, event=None):
        selected = self.record_tree.selection()
        if selected:
            self.rrid.set(str(self.record_tree.item(selected[0], "values")[-1]))

    def diagnose_record(self):
        try:
            rrid = services.number(self.rrid.get(), "记录 ID", 1, 2 ** 53 - 1, True)
        except ValueError as exc:
            self.show_error(str(exc))
            return
        self.start_job("查询记录详情", lambda: services.fetch_record_report(rrid), self.show_diagnostic)

    def open_diagnostic(self):
        filename = filedialog.askopenfilename(parent=self.root, title="打开本地记录或 OBS JSON",
                                               filetypes=[("JSON", "*.json")])
        if filename:
            self.start_job("离线诊断", lambda: inspect_file(filename), self.show_diagnostic)

    def show_diagnostic(self, report):
        self.set_report(format_report(report))

    def set_report(self, text):
        self.set_text(self.report_text, text)

    def set_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", services.safe_text(text, self.secrets))
        widget.configure(state="disabled")

    def query_data(self):
        kind = self.query_kind.get()

        def query(client):
            if kind == "学校跑步策略":
                from .api.policy import fetch_policy
                policy = fetch_policy(client)
                windows = "\n".join(w["start"] + " ~ " + w["end"] for w in policy.valid_time)
                return "最低距离：{} m\n策略：{}\n有效时间：\n{}".format(policy.min_distance, policy.policy, windows or "未提供")
            if kind == "学期完成度":
                from .api.semester import query as semester
                summary = semester(client)["summary"]
                return "学期：{}\n有效次数：{} / {}\n有效里程：{:.2f} km".format(
                    summary.sname, summary.semester_valid_count, summary.semester_count, summary.semester_valid_dis / 1000)
            if kind == "个人日榜":
                from .api.rank import main_rank
                return "\n".join("{}   {}   {:.2f} km".format(r["sort"], r["name"], r["length"] / 1000)
                                 for r in main_rank(client, 1, 1)) or "暂无数据"
            from .api.ai import fetch_list
            return "\n".join("{}   {}".format(s["id"], s["name"]) for s in fetch_list(client)) or "暂无项目"

        self.start_job("查询" + kind, lambda: services.with_client(query), lambda text: self.set_text(self.tools_text, text))

    def close(self):
        if self.busy:
            messagebox.showinfo("任务正在运行", "请等待当前任务结束后关闭，避免无法确认提交结果。", parent=self.root)
            return
        self.root.after_cancel(self.poll_id)
        if self.map_widget is not None:
            try:
                self.map_widget.destroy()
            except Exception:
                pass
        log.handlers = self.old_handlers
        self.log_handler.close()
        self.root.destroy()


def launch():
    """启动桌面窗口；此函数本身不联网、不提交记录。"""
    root = tk.Tk()
    App(root)
    root.mainloop()
