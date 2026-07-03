"""
stats_panel.py — Panel thống kê real-time (View layer)

Hiển thị:
  - Tổng / Đã gán / Reject / Pending
  - Tỷ lệ hoàn thành (progress bar + %)
  - Breakdown reject theo từng lý do
  - Tổng thời lượng đã gán nhãn
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QFrame
)
from PySide6.QtCore import Qt

from models.data_model import REJECT_REASONS


class _StatCard(QFrame):
    """Widget nhỏ hiển thị một con số với label."""

    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        self._value_lbl = QLabel("0")
        self._value_lbl.setObjectName("statValue")
        self._value_lbl.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 800;")
        self._value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._label_lbl = QLabel(label)
        self._label_lbl.setObjectName("statLabel")
        self._label_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_lbl.setStyleSheet("color: #7f849c; font-size: 11px;")

        layout.addWidget(self._value_lbl)
        layout.addWidget(self._label_lbl)

    def set_value(self, value: int | str) -> None:
        self._value_lbl.setText(str(value))


class _RejectReasonRow(QWidget):
    """Hàng hiển thị số lượng reject theo lý do + mini progress bar."""

    COLORS = {
        "Noise":          "#f38ba8",
        "Overlap":        "#fab387",
        "Clipping":       "#f9e2af",
        "Unintelligible": "#a6e3a1",
    }

    def __init__(self, reason: str, parent=None):
        super().__init__(parent)
        self._reason = reason
        color = self.COLORS.get(reason, "#cdd6f4")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        dot.setFixedWidth(14)

        reason_lbl = QLabel(reason)
        reason_lbl.setStyleSheet("color: #a6adc8; font-size: 12px;")
        reason_lbl.setFixedWidth(90)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFixedHeight(6)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background: #313244;
                border-radius: 3px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 3px;
            }}
        """)

        self._count_lbl = QLabel("0")
        self._count_lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 700;")
        self._count_lbl.setFixedWidth(30)
        self._count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(dot)
        layout.addWidget(reason_lbl)
        layout.addWidget(self._bar, stretch=1)
        layout.addWidget(self._count_lbl)

    def update_data(self, count: int, total_rejected: int) -> None:
        self._count_lbl.setText(str(count))
        pct = int(count / total_rejected * 100) if total_rejected > 0 else 0
        self._bar.setValue(pct)


class StatsPanel(QWidget):
    """Panel thống kê toàn bộ dự án."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statsPanel")
        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # ── Title ────────────────────────────────────────────────────────
        title = QLabel("📊 Thống kê")
        title.setObjectName("statsPanelTitle")
        root.addWidget(title)

        # ── Summary cards (2×2 grid) ─────────────────────────────────────
        from PySide6.QtWidgets import QGridLayout
        cards_grid = QGridLayout()
        cards_grid.setSpacing(6)
        cards_grid.setContentsMargins(0, 0, 0, 0)

        self._card_total    = _StatCard("Tổng",   "#89b4fa")
        self._card_labeled  = _StatCard("Đã gán", "#a6e3a1")
        self._card_rejected = _StatCard("Reject", "#f38ba8")
        self._card_pending  = _StatCard("Còn lại","#f9e2af")

        cards_grid.addWidget(self._card_total,    0, 0)
        cards_grid.addWidget(self._card_labeled,  0, 1)
        cards_grid.addWidget(self._card_rejected, 1, 0)
        cards_grid.addWidget(self._card_pending,  1, 1)

        root.addLayout(cards_grid)

        # ── Overall progress ─────────────────────────────────────────────
        progress_frame = QFrame()
        progress_frame.setObjectName("progressFrame")
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(12, 10, 12, 10)
        progress_layout.setSpacing(6)

        prog_header = QHBoxLayout()
        prog_lbl = QLabel("Tiến độ hoàn thành")
        prog_lbl.setStyleSheet("color: #cdd6f4; font-size: 12px; font-weight: 600;")
        self._pct_lbl = QLabel("0.0%")
        self._pct_lbl.setStyleSheet("color: #89b4fa; font-size: 14px; font-weight: 800;")
        prog_header.addWidget(prog_lbl)
        prog_header.addStretch()
        prog_header.addWidget(self._pct_lbl)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedHeight(10)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setObjectName("mainProgressBar")

        progress_layout.addLayout(prog_header)
        progress_layout.addWidget(self._progress_bar)
        root.addWidget(progress_frame)

        # ── Reject breakdown ─────────────────────────────────────────────
        reject_frame = QFrame()
        reject_frame.setObjectName("rejectFrame")
        reject_layout = QVBoxLayout(reject_frame)
        reject_layout.setContentsMargins(12, 10, 12, 10)
        reject_layout.setSpacing(4)

        reject_title = QLabel("Phân loại Reject")
        reject_title.setStyleSheet("color: #f38ba8; font-size: 12px; font-weight: 600;")
        reject_layout.addWidget(reject_title)

        self._reason_rows: dict[str, _RejectReasonRow] = {}
        for reason in REJECT_REASONS:
            row = _RejectReasonRow(reason)
            self._reason_rows[reason] = row
            reject_layout.addWidget(row)

        root.addWidget(reject_frame)

        # ── Duration stats ───────────────────────────────────────────────
        dur_frame = QFrame()
        dur_frame.setObjectName("durationFrame")
        dur_layout = QVBoxLayout(dur_frame)
        dur_layout.setContentsMargins(12, 10, 12, 10)
        dur_layout.setSpacing(4)

        dur_title = QLabel("Thời lượng")
        dur_title.setStyleSheet("color: #89dceb; font-size: 12px; font-weight: 600;")
        dur_layout.addWidget(dur_title)

        self._dur_total_lbl   = QLabel("Tổng: --")
        self._dur_labeled_lbl = QLabel("Đã gán: --")
        for lbl in (self._dur_total_lbl, self._dur_labeled_lbl):
            lbl.setStyleSheet("color: #a6adc8; font-size: 12px;")
            dur_layout.addWidget(lbl)

        root.addWidget(dur_frame)
        root.addStretch()

    def update_stats(self, stats: dict) -> None:
        """Cập nhật toàn bộ panel từ dict thống kê."""
        self._card_total.set_value(stats["total"])
        self._card_labeled.set_value(stats["labeled"])
        self._card_rejected.set_value(stats["rejected"])
        self._card_pending.set_value(stats["pending"])

        pct = stats["completion_pct"]
        self._pct_lbl.setText(f"{pct}%")
        self._progress_bar.setValue(int(pct * 10))

        total_rej = stats["rejected"]
        for reason, row in self._reason_rows.items():
            count = stats["reject_by_reason"].get(reason, 0)
            row.update_data(count, total_rej)

        total_s  = stats["total_duration_s"]
        label_s  = stats["labeled_duration_s"]
        self._dur_total_lbl.setText(f"Tổng: {self._fmt_dur(total_s)}")
        self._dur_labeled_lbl.setText(f"Đã gán: {self._fmt_dur(label_s)}")

    @staticmethod
    def _fmt_dur(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h}h {m:02d}m {s:02d}s"
        return f"{m}m {s:02d}s"

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            #statsPanel { background: transparent; }
            #statsPanelTitle {
                color: #cba6f7;
                font-size: 14px;
                font-weight: 700;
                padding-bottom: 4px;
            }
            #statCard {
                background: #27273d;
                border: 1px solid #3a3a5c;
                border-radius: 8px;
            }
            #progressFrame, #rejectFrame, #durationFrame {
                background: #27273d;
                border: 1px solid #3a3a5c;
                border-radius: 8px;
            }
            #mainProgressBar {
                background: #313244;
                border-radius: 5px;
                border: none;
            }
            #mainProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #89b4fa, stop:1 #cba6f7);
                border-radius: 5px;
            }
        """)
