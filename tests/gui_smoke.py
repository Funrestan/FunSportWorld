"""离线可视化验收：检查两个窗口大小的布局并保存截图。"""
import json
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from unittest.mock import patch

from tests.support import IMPORT_DATA
from tests.plan_fixture import sample_plan
from funsport.gui import App
from funsport.gui_services import run_parameters
from PIL import ImageGrab


def visible_widgets(widget):
    """递归收集当前页可见控件，用于检查是否超出窗口。"""
    for child in widget.winfo_children():
        if child.winfo_ismapped():
            yield child
            yield from visible_widgets(child)


def main():
    """使用完整离线方案渲染地图和明细，检查像素与控件边界。"""
    output = Path(__file__).resolve().parents[1] / ".artifacts"
    output.mkdir(exist_ok=True)
    with patch("requests.sessions.Session.request", side_effect=AssertionError("No network in visual smoke")):
        root = tk.Tk()
        app = App(root)
        root.attributes("-topmost", True)
        root.geometry("1120x820+20+20")
        app.run_vars["auto"].set(False)
        app.run_vars["use_map"].set(True)
        app.run_vars["dist"].set("1.6")
        app.run_vars["seed"].set("42")
        app.sync_modes()
        root.update()
        app.show_plan(sample_plan(), run_parameters(app.values(app.run_vars)))
        app.show_records([{"rrid": 12345, "start_time": 1789700400000, "total_dis": 2800,
                           "total_time": 1120, "complete": None}])
        results = []
        try:
            for width, height in ((1120, 820), (960, 760)):
                root.geometry("{}x{}+20+20".format(width, height))
                for index, name, preview_index in ((0, "run", 0), (0, "plan", 1),
                                                    (1, "records", None), (2, "tools", None), (3, "settings", None)):
                    app.tabs.select(index)
                    if preview_index is not None:
                        app.preview_tabs.select(preview_index)
                    root.update()
                    if name == "run":
                        app.fit_map()
                    time.sleep(0.15)
                    root.update()
                    left, top = root.winfo_rootx(), root.winfo_rooty()
                    right, bottom = left + root.winfo_width(), top + root.winfo_height()
                    overflow = []
                    for widget in visible_widgets(root):
                        x, y = widget.winfo_rootx(), widget.winfo_rooty()
                        if x < left - 2 or y < top - 2 or x + widget.winfo_width() > right + 2 or y + widget.winfo_height() > bottom + 2:
                            overflow.append(str(widget))
                        if isinstance(widget, (ttk.Label, ttk.Button, ttk.Entry, ttk.Checkbutton, ttk.Radiobutton)):
                            if widget.winfo_height() < widget.winfo_reqheight() - 1:
                                overflow.append(str(widget) + ": clipped text/control height")
                            parent = widget.master
                            if y + widget.winfo_height() > parent.winfo_rooty() + parent.winfo_height() + 2:
                                overflow.append(str(widget) + ": clipped by parent")
                    filename = output / "gui-{}x{}-{}.png".format(width, height, name)
                    image = ImageGrab.grab(window=root.winfo_id())
                    image.save(filename)
                    if name == "run":
                        assert app.canvas.find_withtag("route"), "Route is blank"
                        assert app.canvas.find_withtag("endpoints"), "Start/end markers missing"
                        route_pixels = sum(count for count, (red, green, blue) in image.convert("RGB").getcolors(image.width * image.height)
                                           if green > red + 40 and green > blue + 25)
                        assert route_pixels > 100, "Route pixels are blank"
                    results.append({"size": [width, height], "tab": name, "overflow": overflow})
            print(json.dumps(results, ensure_ascii=True))
            assert not any(item["overflow"] for item in results), "Some widgets overflow the window"
        finally:
            app.close()


if __name__ == "__main__":
    main()
