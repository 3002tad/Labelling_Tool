"""
main.py — Entry point của ứng dụng ASR Dataset Labeler

Khởi tạo QApplication, thiết lập font và high-DPI, rồi chạy MainWindow.
"""

import sys
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from views.main_window import MainWindow


def main() -> int:
    # High-DPI support
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("ASR Dataset Labeler")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("VNPT")

    # Default font (Segoe UI trên Windows, fallback Inter/sans-serif)
    font = QFont("Segoe UI", 10)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
