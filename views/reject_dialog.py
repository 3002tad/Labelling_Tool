"""
reject_dialog.py — Dialog chọn lý do Reject (View layer)

Hiển thị 4 lựa chọn: Noise, Overlap, Clipping, Unintelligible.
Trả về lý do đã chọn hoặc None nếu hủy.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QButtonGroup, QRadioButton, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut

from models.data_model import REJECT_REASONS

# Mô tả ngắn cho từng lý do
REASON_DESCRIPTIONS = {
    "Noise":           "Tiếng ồn nền quá lớn, khó nghe rõ nội dung",
    "Overlap":         "Nhiều giọng nói cùng lúc, chồng chéo lên nhau",
    "Clipping":        "Âm thanh bị cắt đầu/cuối hoặc bị méo",
    "Unintelligible":  "Không thể hiểu nội dung dù âm thanh rõ",
}

REASON_ICONS = {
    "Noise":           "🔊",
    "Overlap":         "👥",
    "Clipping":        "✂️",
    "Unintelligible":  "❓",
}


class RejectDialog(QDialog):
    """Modal dialog để người dùng chọn lý do reject một segment."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Từ chối segment")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._selected_reason: str | None = None
        self._setup_ui()
        self._apply_styles()

    # ------------------------------------------------------------------ #
    # UI Construction
    # ------------------------------------------------------------------ #

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Header ──────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("rejectHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 20, 24, 16)

        title = QLabel("Chọn lý do từ chối")
        title.setObjectName("rejectTitle")

        subtitle = QLabel("Segment này sẽ bị loại khỏi tập dữ liệu huấn luyện.")
        subtitle.setObjectName("rejectSubtitle")
        subtitle.setWordWrap(True)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        # ── Radio buttons ────────────────────────────────────────────────
        body = QFrame()
        body.setObjectName("rejectBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 8)
        body_layout.setSpacing(8)

        self._btn_group = QButtonGroup(self)
        self._radio_buttons: dict[str, QRadioButton] = {}

        for i, reason in enumerate(REJECT_REASONS, start=1):
            card = QFrame()
            card.setObjectName("reasonCard")
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(12)

            radio = QRadioButton()
            radio.setObjectName("reasonRadio")
            if i == 1:
                radio.setChecked(True)

            icon_lbl = QLabel(REASON_ICONS[reason])
            icon_lbl.setObjectName("reasonIcon")
            icon_lbl.setFixedWidth(28)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            name_lbl = QLabel(f"{i}. {reason}")
            name_lbl.setObjectName("reasonName")
            desc_lbl = QLabel(REASON_DESCRIPTIONS[reason])
            desc_lbl.setObjectName("reasonDesc")
            desc_lbl.setWordWrap(True)
            text_col.addWidget(name_lbl)
            text_col.addWidget(desc_lbl)

            card_layout.addWidget(radio)
            card_layout.addWidget(icon_lbl)
            card_layout.addLayout(text_col, stretch=1)

            self._btn_group.addButton(radio, i - 1)
            self._radio_buttons[reason] = radio
            body_layout.addWidget(card)

            # Click anywhere on card selects radio
            card.mousePressEvent = lambda _, r=radio: r.setChecked(True)

        root.addWidget(body)

        # ── Buttons ──────────────────────────────────────────────────────
        footer = QFrame()
        footer.setObjectName("rejectFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 12, 20, 16)
        footer_layout.setSpacing(10)

        self._btn_cancel = QPushButton("Hủy")
        self._btn_cancel.setObjectName("btnCancel")
        self._btn_cancel.setFixedHeight(38)
        self._btn_cancel.clicked.connect(self.reject)

        self._btn_confirm = QPushButton("Xác nhận Reject")
        self._btn_confirm.setObjectName("btnConfirm")
        self._btn_confirm.setFixedHeight(38)
        self._btn_confirm.setDefault(True)
        self._btn_confirm.clicked.connect(self._on_confirm)

        footer_layout.addWidget(self._btn_cancel)
        footer_layout.addStretch()
        footer_layout.addWidget(self._btn_confirm)

        root.addWidget(footer)

        # Keyboard shortcuts: 1-4 to select reason
        for i, reason in enumerate(REJECT_REASONS, start=1):
            sc = QShortcut(QKeySequence(str(i)), self)
            sc.activated.connect(lambda r=reason: self._radio_buttons[r].setChecked(True))

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #

    def _on_confirm(self) -> None:
        for reason, radio in self._radio_buttons.items():
            if radio.isChecked():
                self._selected_reason = reason
                break
        self.accept()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def selected_reason(self) -> str | None:
        return self._selected_reason

    @staticmethod
    def get_reason(parent=None) -> str | None:
        """Convenience static factory. Returns reason or None if cancelled."""
        dlg = RejectDialog(parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.selected_reason()
        return None

    # ------------------------------------------------------------------ #
    # Styles
    # ------------------------------------------------------------------ #

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background: #1e1e2e;
                border-radius: 12px;
            }
            #rejectHeader {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2d1b4e, stop:1 #1e1e2e);
                border-bottom: 1px solid #3a3a5c;
            }
            #rejectTitle {
                color: #cba6f7;
                font-size: 17px;
                font-weight: 700;
            }
            #rejectSubtitle {
                color: #a6adc8;
                font-size: 12px;
            }
            #rejectBody {
                background: #1e1e2e;
            }
            #reasonCard {
                background: #27273d;
                border: 1.5px solid #3a3a5c;
                border-radius: 8px;
            }
            #reasonCard:hover {
                background: #313150;
                border-color: #cba6f7;
            }
            #reasonIcon {
                font-size: 18px;
            }
            #reasonName {
                color: #cdd6f4;
                font-size: 13px;
                font-weight: 600;
            }
            #reasonDesc {
                color: #7f849c;
                font-size: 11px;
            }
            QRadioButton#reasonRadio {
                width: 16px;
            }
            QRadioButton#reasonRadio::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #6c7086;
                background: #1e1e2e;
            }
            QRadioButton#reasonRadio::indicator:checked {
                border-color: #cba6f7;
                background: #cba6f7;
            }
            #rejectFooter {
                background: #181825;
                border-top: 1px solid #3a3a5c;
            }
            #btnCancel {
                background: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 0 18px;
                font-size: 13px;
            }
            #btnCancel:hover { background: #45475a; }
            #btnConfirm {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f38ba8, stop:1 #eba0ac);
                color: #1e1e2e;
                border: none;
                border-radius: 6px;
                padding: 0 22px;
                font-size: 13px;
                font-weight: 700;
            }
            #btnConfirm:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f5a0b8, stop:1 #f0b5c0);
            }
        """)
