"""
MV卡拉OK制作器 - 桌面应用入口
"""
import sys
import os
import traceback
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# 添加当前目录到系统路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.main_window import MainWindow


def _global_exception_hook(exc_type, exc_value, exc_tb):
    """未捕获异常的全局处理器 — 打印完整错误以供调试"""
    print("\n" + "=" * 60, file=sys.stderr)
    print(" FATAL EXCEPTION:", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.stderr)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def main():
    """主函数"""
    # 安装全局异常钩子
    sys.excepthook = _global_exception_hook

    # 启用高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("MV卡拉OK制作器")

    # 设置样式
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
