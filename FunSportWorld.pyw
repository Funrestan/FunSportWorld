"""Windows 双击入口；启动失败时显示错误窗口而非静默退出。"""


def main():
    """加载 GUI；缺失依赖时显示简洁提示，不输出配置或凭据。"""
    try:
        from funsport.gui import launch
        launch()
    except Exception as exc:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("FunSportWorld 启动失败", "请确认已安装 requirements.txt 中的依赖。\n错误类型：" + type(exc).__name__, parent=root)
        root.destroy()


if __name__ == "__main__":
    main()
