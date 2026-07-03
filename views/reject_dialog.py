"""
reject_dialog.py — Dialog chọn lý do Reject (View layer)

Hỗ trợ chọn NHIỀU lý do cùng lúc (CheckBox thay RadioButton).
Kết quả trả về dạng chuỗi "Noise,Clipping" hoặc None nếu hủy.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut

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
    """
    Modal dialog để người dùng chọn một hoặc nhiều lý do reject.
    Kết quả: chuỗi phân cách bằng dấu phẩy, VD: 'Noise,Clipping'
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Từ chối segment")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self._selected_reasons: list[str] = []
        self._cards: list[QFrame] = []
        self._focused_idx = 0
        self._setup_ui()
        self._apply_styles()
        self._update_focus()

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
        header_layout.setContentsMargins(24, 20, 24, 14)
        header_layout.setSpacing(4)

        title = QLabel("Chọn lý do từ chối")
        title.setObjectName("rejectTitle")

        subtitle = QLabel(
            "Có thể chọn nhiều lý do nếu segment gặp nhiều vấn đề cùng lúc."
        )
        subtitle.setObjectName("rejectSubtitle")
        subtitle.setWordWrap(True)

        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        # ── Checkboxes ───────────────────────────────────────────────────
        body = QFrame()
        body.setObjectName("rejectBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 14, 20, 8)
        body_layout.setSpacing(8)

        self._checkboxes: dict[str, QCheckBox] = {}

        for i, reason in enumerate(REJECT_REASONS, start=1):
            card = QFrame()
            card.setObjectName("reasonCard")
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(12)

            chk = QCheckBox()
            chk.setObjectName("reasonCheck")
            chk.stateChanged.connect(self._on_check_changed)

            icon_lbl = QLabel(REASON_ICONS[reason])
            icon_lbl.setObjectName("reasonIcon")
            icon_lbl.setFixedWidth(28)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)

            name_row = QHBoxLayout()
            name_lbl = QLabel(f"{reason}")
            name_lbl.setObjectName("reasonName")
            shortcut_lbl = QLabel(f"[{i}]")
            shortcut_lbl.setObjectName("reasonShortcut")
            name_row.addWidget(name_lbl)
            name_row.addWidget(shortcut_lbl)
            name_row.addStretch()

            desc_lbl = QLabel(REASON_DESCRIPTIONS[reason])
            desc_lbl.setObjectName("reasonDesc")
            desc_lbl.setWordWrap(True)

            text_col.addLayout(name_row)
            text_col.addWidget(desc_lbl)

            card_layout.addWidget(chk)
            card_layout.addWidget(icon_lbl)
            card_layout.addLayout(text_col, stretch=1)

            self._checkboxes[reason] = chk
            self._cards.append(card)
            body_layout.addWidget(card)

            # Click trên toàn card → toggle checkbox, update focus
            card.mousePressEvent = lambda _, c=chk, idx=i-1: (
                c.setChecked(not c.isChecked()),
                setattr(self, '_focused_idx', idx),
                self._update_focus()
            )

        root.addWidget(body)

        # ── Selected summary label ────────────────────────────────────────
        self._summary_lbl = QLabel("Chưa chọn lý do nào")
        self._summary_lbl.setObjectName("summaryLbl")
        self._summary_lbl.setContentsMargins(20, 6, 20, 0)
        root.addWidget(self._summary_lbl)

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

        self._btn_confirm = QPushButton("✗  Xác nhận Reject")
        self._btn_confirm.setObjectName("btnConfirm")
        self._btn_confirm.setFixedHeight(38)
        self._btn_confirm.setDefault(True)
        self._btn_confirm.setEnabled(False)   # disabled cho đến khi chọn ≥1
        self._btn_confirm.clicked.connect(self._on_confirm)

        footer_layout.addWidget(self._btn_cancel)
        footer_layout.addStretch()
        footer_layout.addWidget(self._btn_confirm)

        root.addWidget(footer)

        # Keyboard shortcuts 1–4 toggle tương ứng
        for i, reason in enumerate(REJECT_REASONS, start=1):
            sc = QShortcut(QKeySequence(str(i)), self)
            sc.activated.connect(
                lambda r=reason: self._checkboxes[r].setChecked(
                    not self._checkboxes[r].isChecked()
                )
            )

    # ------------------------------------------------------------------ #
    # Slots & Events
    # ------------------------------------------------------------------ #

    def _update_focus(self) -> None:
        """Cập nhật style highlight cho thẻ đang được focus."""
        for i, card in enumerate(self._cards):
            card.setProperty("focused", i == self._focused_idx)
            card.style().unpolish(card)
            card.style().polish(card)

    def keyPressEvent(self, event) -> None:
        from PySide6.QtGui import QKeyEvent
        if isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Up:
                self._focused_idx = (self._focused_idx - 1) % len(self._cards)
                self._update_focus()
                return
            elif event.key() == Qt.Key.Key_Down:
                self._focused_idx = (self._focused_idx + 1) % len(self._cards)
                self._update_focus()
                return
            elif event.key() == Qt.Key.Key_Space:
                reason = REJECT_REASONS[self._focused_idx]
                chk = self._checkboxes[reason]
                chk.setChecked(not chk.isChecked())
                return
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                reason = REJECT_REASONS[self._focused_idx]
                chk = self._checkboxes[reason]
                selected = [r for r, c in self._checkboxes.items() if c.isChecked()]
                if not selected:
                    chk.setChecked(True)
                    self._try_confirm()
                else:
                    self._try_confirm()
                return
        super().keyPressEvent(event)

    def _on_check_changed(self) -> None:
        selected = [r for r, c in self._checkboxes.items() if c.isChecked()]
        self._btn_confirm.setEnabled(len(selected) > 0)

        if selected:
            self._summary_lbl.setText(f"Đã chọn: {', '.join(selected)}")
            self._summary_lbl.setStyleSheet("color: #f38ba8; font-size: 12px; font-weight: 600;")
        else:
            self._summary_lbl.setText("Chưa chọn lý do nào")
            self._summary_lbl.setStyleSheet("color: #585b70; font-size: 12px;")

    def _on_confirm(self) -> None:
        self._selected_reasons = [
            r for r, c in self._checkboxes.items() if c.isChecked()
        ]
        self.accept()

    def _try_confirm(self) -> None:
        if self._btn_confirm.isEnabled():
            self._on_confirm()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def selected_reasons(self) -> list[str]:
        """Trả về danh sách lý do đã chọn."""
        return self._selected_reasons

    def selected_reasons_str(self) -> str:
        """Trả về chuỗi phân cách bằng dấu phẩy, VD: 'Noise,Clipping'."""
        return ",".join(self._selected_reasons)

    @staticmethod
    def get_reason(parent=None) -> str | None:
        """
        Convenience factory. Trả về chuỗi lý do hoặc None nếu hủy.
        Tương thích với code cũ đang gọi get_reason().
        """
        dlg = RejectDialog(parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.selected_reasons_str() or None
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
            #reasonCard:hover, #reasonCard[focused="true"] {
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
            #reasonShortcut {
                color: #585b70;
                font-size: 11px;
            }
            #reasonDesc {
                color: #7f849c;
                font-size: 11px;
            }

            QCheckBox#reasonCheck {
                spacing: 0;
            }
            QCheckBox#reasonCheck::indicator {
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 2px solid #6c7086;
                background: #1e1e2e;
            }
            QCheckBox#reasonCheck::indicator:hover {
                border-color: #cba6f7;
            }
            QCheckBox#reasonCheck::indicator:checked {
                border-color: #f38ba8;
                background: #f38ba8;
                image: url(none);
            }
            QCheckBox#reasonCheck::indicator:checked {
                border-color: #f38ba8;
                background: #f38ba8;
            }

            #summaryLbl {
                color: #585b70;
                font-size: 12px;
                padding-bottom: 4px;
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
            #btnConfirm:disabled {
                background: #313244;
                color: #585b70;
            }
        """)
