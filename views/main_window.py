"""
main_window.py — View layer (MVC)

MainWindow là lớp View duy nhất của ứng dụng. Nó:
  - Xây dựng toàn bộ giao diện (dark theme, Catppuccin Mocha palette)
  - Kết nối signals từ AppController để cập nhật UI
  - Gửi hành động người dùng lên Controller (không xử lý logic)
  - Quản lý phím tắt toàn cục
"""

import os
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QProgressBar,
    QFileDialog, QSplitter, QFrame, QSlider,
    QStatusBar, QMessageBox, QSizePolicy, QToolButton,
    QScrollArea, QComboBox
)
from PySide6.QtCore import Qt, QTimer, Slot, QSize, Signal
from PySide6.QtGui import (
    QFont, QKeySequence, QShortcut, QIcon, QColor,
    QPalette, QFontDatabase, QMouseEvent, QKeyEvent
)

from controllers.app_controller import AppController
from models.data_model import SegmentRecord, SegmentStatus
from views.stats_panel import StatsPanel
from views.reject_dialog import RejectDialog
from views.export_dialog import ExportDialog


class ClickableSlider(QSlider):
    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            val = self.minimum() + ((self.maximum() - self.minimum()) * ev.position().x()) / self.width()
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))
            ev.accept()
        super().mousePressEvent(ev)

class TranscriptTextEdit(QTextEdit):
    """Custom TextEdit để chặn phím Enter/Ctrl+Enter, nhưng cho phép Shift+Enter xuống dòng."""
    
    save_next_requested = Signal()
    save_only_requested = Signal()

    def keyPressEvent(self, ev: QKeyEvent) -> None:
        if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            mods = ev.modifiers()
            if mods == Qt.KeyboardModifier.ControlModifier:
                self.save_only_requested.emit()
                return
            elif mods == Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(ev)
                return
            elif mods == Qt.KeyboardModifier.NoModifier:
                self.save_next_requested.emit()
                return
        super().keyPressEvent(ev)

class WaveformBar(QWidget):
    """Thanh progress đơn giản thay thế waveform — nhẹ & không cần thư viện ngoài."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self._slider = ClickableSlider(Qt.Orientation.Horizontal, self)
        self._slider.setRange(0, 1000)
        self._slider.setValue(0)
        self._slider.setObjectName("audioSlider")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.addWidget(self._slider)

    @property
    def slider(self) -> QSlider:
        return self._slider


class SegmentInfoPanel(QFrame):
    """Panel hiển thị thông tin metadata của segment hiện tại."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("segmentInfoPanel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(24)

        self._fields: dict[str, QLabel] = {}
        spec = [
            ("segment_id",   "Segment ID",    "#89b4fa"),
            ("source_file",  "Nguồn",         "#a6e3a1"),
            ("time_range",   "Thời điểm",     "#fab387"),
            ("duration",     "Độ dài",        "#f9e2af"),
            ("sample_rate",  "Sample rate",   "#cba6f7"),
            ("status",       "Trạng thái",    "#94e2d5"),
        ]
        for key, label, color in spec:
            col = QVBoxLayout()
            col.setSpacing(2)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 600;")
            val = QLabel("—")
            val.setStyleSheet("color: #cdd6f4; font-size: 12px;")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            col.addWidget(lbl)
            col.addWidget(val)
            layout.addLayout(col)
            self._fields[key] = val

        layout.addStretch()

    def update_record(self, rec: SegmentRecord, index: int, total: int) -> None:
        self._fields["segment_id"].setText(rec.segment_id)
        self._fields["source_file"].setText(rec.source_file)
        self._fields["time_range"].setText(
            f"{rec.start:.2f}s → {rec.end:.2f}s"
        )
        self._fields["duration"].setText(f"{rec.duration:.2f}s")
        self._fields["sample_rate"].setText(f"{rec.sample_rate:,} Hz")

        status_map = {
            SegmentStatus.PENDING.value:  ("⏳ Pending",  "#f9e2af"),
            SegmentStatus.LABELED.value:  ("✅ Đã gán",   "#a6e3a1"),
            SegmentStatus.REJECTED.value: ("❌ Rejected",  "#f38ba8"),
        }
        text, color = status_map.get(rec.status, ("?", "#cdd6f4"))
        self._fields["status"].setText(text)
        self._fields["status"].setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")


class MainWindow(QMainWindow):
    """
    Cửa sổ chính — lớp View trong MVC.

    Không chứa logic nghiệp vụ; chỉ:
      1. Xây dựng và style UI.
      2. Nhận signals từ AppController và cập nhật các widget.
      3. Chuyển tiếp input của người dùng lên Controller.
    """

    def __init__(self):
        super().__init__()
        self._controller = AppController(self)
        self._controller.set_view(self)

        self._setup_window()
        self._setup_ui()
        self._apply_global_styles()
        self._connect_signals()
        self._setup_shortcuts()

        # Timer để cập nhật slider audio theo thời gian thực
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(80)
        self._update_timer.timeout.connect(self._refresh_time_labels)

        self.show()
        self._show_welcome()

    # ================================================================== #
    # Window setup
    # ================================================================== #

    def _setup_window(self) -> None:
        self.setWindowTitle("ASR Dataset Labeler")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

    # ================================================================== #
    # UI Construction
    # ================================================================== #

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left sidebar (stats) ─────────────────────────────────────────
        sidebar = self._build_sidebar()
        root.addWidget(sidebar)

        # ── Main content area ────────────────────────────────────────────
        content = self._build_main_content()
        root.addWidget(content, stretch=1)

        # ── Status bar ───────────────────────────────────────────────────
        self._status_bar = QStatusBar()
        self._status_bar.setObjectName("mainStatusBar")
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Chào mừng! Nhấn 'Mở dự án' để bắt đầu.")

    # ------------------------------------------------------------------ #
    # Sidebar
    # ------------------------------------------------------------------ #

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(300)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(12)

        # Logo / title
        logo_lbl = QLabel("🎙 ASR Labeler")
        logo_lbl.setObjectName("appLogo")
        layout.addWidget(logo_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sidebarSep")
        layout.addWidget(sep)

        # Open project button
        self._btn_open = QPushButton("📂  Mở dự án")
        self._btn_open.setObjectName("btnOpen")
        self._btn_open.setFixedHeight(38)
        self._btn_open.clicked.connect(self._on_open_project)
        layout.addWidget(self._btn_open)

        # Export button
        self._btn_export_data = QPushButton("📤  Xuất Dataset")
        self._btn_export_data.setObjectName("btnExportData")
        self._btn_export_data.setFixedHeight(38)
        self._btn_export_data.setEnabled(False)   # enabled sau khi mở dự án
        self._btn_export_data.clicked.connect(self._on_export_data)
        layout.addWidget(self._btn_export_data)

        # Stats panel (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("statsScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._stats_panel = StatsPanel()
        scroll.setWidget(self._stats_panel)
        layout.addWidget(scroll, stretch=1)

        # Filter combo box
        filter_row = QHBoxLayout()
        filter_lbl = QLabel("Lọc:")
        filter_lbl.setStyleSheet("color: #7f849c; font-size: 12px;")
        self._filter_combo = QComboBox()
        self._filter_combo.setObjectName("filterCombo")
        self._filter_combo.setFixedHeight(30)
        self._filter_combo.addItem("Tất cả", "all")
        self._filter_combo.addItem("Chưa gán (Pending)", "pending")
        self._filter_combo.addItem("Đã gán (Labeled)", "labeled")
        self._filter_combo.addItem("Bị loại (Rejected)", "rejected")
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(filter_lbl)
        filter_row.addWidget(self._filter_combo, stretch=1)
        layout.addLayout(filter_row)

        # Navigate to index
        nav_row = QHBoxLayout()
        nav_lbl = QLabel("Đến #")
        nav_lbl.setStyleSheet("color: #7f849c; font-size: 12px;")
        self._jump_input = QTextEdit()
        self._jump_input.setObjectName("jumpInput")
        self._jump_input.setFixedHeight(30)
        self._jump_input.setPlaceholderText("VD: 42")
        self._jump_input.setAcceptRichText(False)
        btn_jump = QPushButton("Go")
        btn_jump.setObjectName("btnJump")
        btn_jump.setFixedHeight(30)
        btn_jump.clicked.connect(self._on_jump)
        nav_row.addWidget(nav_lbl)
        nav_row.addWidget(self._jump_input, stretch=1)
        nav_row.addWidget(btn_jump)
        layout.addLayout(nav_row)

        return sidebar

    # ------------------------------------------------------------------ #
    # Main content
    # ------------------------------------------------------------------ #

    def _build_main_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("mainContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── Header: segment info + progress ─────────────────────────────
        layout.addWidget(self._build_header())

        # ── Segment info panel ───────────────────────────────────────────
        self._info_panel = SegmentInfoPanel()
        layout.addWidget(self._info_panel)

        # ── Audio player area ────────────────────────────────────────────
        layout.addWidget(self._build_audio_player())

        # ── Transcript input ─────────────────────────────────────────────
        layout.addWidget(self._build_transcript_area(), stretch=1)

        # ── Action buttons ───────────────────────────────────────────────
        layout.addWidget(self._build_action_buttons())

        # ── Keyboard shortcuts hint ──────────────────────────────────────
        layout.addWidget(self._build_shortcut_hint())

        return content

    def _build_header(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        self._title_lbl = QLabel("Chưa mở dự án")
        self._title_lbl.setObjectName("mainTitle")

        self._progress_lbl = QLabel("")
        self._progress_lbl.setObjectName("progressLabel")
        self._progress_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._overall_bar = QProgressBar()
        self._overall_bar.setObjectName("overallBar")
        self._overall_bar.setRange(0, 1000)
        self._overall_bar.setValue(0)
        self._overall_bar.setFixedHeight(6)
        self._overall_bar.setTextVisible(False)
        self._overall_bar.setFixedWidth(140)

        layout.addWidget(self._title_lbl)
        layout.addStretch()
        layout.addWidget(self._overall_bar)
        layout.addWidget(self._progress_lbl)
        return w

    def _build_audio_player(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("audioPlayerFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # Time row
        time_row = QHBoxLayout()
        self._pos_lbl = QLabel("0:00")
        self._pos_lbl.setObjectName("timeLbl")
        self._dur_lbl = QLabel("0:00")
        self._dur_lbl.setObjectName("timeLbl")
        self._dur_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        time_row.addWidget(self._pos_lbl)
        time_row.addStretch()
        time_row.addWidget(self._dur_lbl)

        # Waveform / slider
        self._wave_bar = WaveformBar()
        self._wave_bar.slider.sliderMoved.connect(self._on_seek)

        layout.addLayout(time_row)
        layout.addWidget(self._wave_bar)

        # Controls row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)

        self._btn_prev = self._make_ctrl_btn("◀◀", "Segment trước", "btnCtrl")
        self._btn_replay = self._make_ctrl_btn("↺", "Phát lại", "btnCtrl")
        self._btn_play = self._make_ctrl_btn("▶", "Play / Pause", "btnPlay")
        self._btn_play.setFixedSize(52, 52)
        self._btn_next = self._make_ctrl_btn("▶▶", "Segment tiếp", "btnCtrl")

        ctrl_row.addStretch()
        ctrl_row.addWidget(self._btn_prev)
        ctrl_row.addWidget(self._btn_replay)
        ctrl_row.addWidget(self._btn_play)
        ctrl_row.addWidget(self._btn_next)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        # Speed control row
        speed_row = QHBoxLayout()
        speed_row.setSpacing(8)

        speed_icon = QLabel("🏎 Tốc độ:")
        speed_icon.setStyleSheet("color: #7f849c; font-size: 11px;")

        slow_lbl = QLabel("0.5x")
        slow_lbl.setStyleSheet("color: #585b70; font-size: 10px;")

        self._speed_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setObjectName("speedSlider")
        self._speed_slider.setRange(50, 100)   # 50 = 0.5x, 100 = 1.0x
        self._speed_slider.setValue(100)
        self._speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._speed_slider.setTickInterval(10)
        self._speed_slider.setFixedWidth(160)
        self._speed_slider.setFixedHeight(24)
        self._speed_slider.valueChanged.connect(self._on_speed_slider_changed)

        fast_lbl = QLabel("1.0x")
        fast_lbl.setStyleSheet("color: #585b70; font-size: 10px;")

        self._speed_lbl = QLabel("1.0x")
        self._speed_lbl.setObjectName("speedLabel")
        self._speed_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._speed_lbl.setFixedWidth(44)
        self._speed_lbl.setStyleSheet(
            "color: #cba6f7; font-size: 12px; font-weight: 700;"
        )

        self._btn_speed_reset = QPushButton("↺ 1x")
        self._btn_speed_reset.setObjectName("btnCtrl")
        self._btn_speed_reset.setToolTip("Về tốc độ gốc (1.0x)")
        self._btn_speed_reset.setFixedSize(42, 26)
        self._btn_speed_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_speed_reset.clicked.connect(self._on_speed_reset)

        speed_row.addStretch()
        speed_row.addWidget(speed_icon)
        speed_row.addWidget(slow_lbl)
        speed_row.addWidget(self._speed_slider)
        speed_row.addWidget(fast_lbl)
        speed_row.addWidget(self._speed_lbl)
        speed_row.addWidget(self._btn_speed_reset)
        speed_row.addStretch()
        layout.addLayout(speed_row)

        return frame

    def _build_transcript_area(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("transcriptFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        hdr = QHBoxLayout()
        lbl = QLabel("📝 Transcript")
        lbl.setObjectName("transcriptLabel")
        self._char_count_lbl = QLabel("0 ký tự")
        self._char_count_lbl.setObjectName("charCountLbl")
        hdr.addWidget(lbl)
        hdr.addStretch()
        hdr.addWidget(self._char_count_lbl)
        layout.addLayout(hdr)

        self._transcript_edit = TranscriptTextEdit()
        self._transcript_edit.setObjectName("transcriptEdit")
        self._transcript_edit.setPlaceholderText(
            "Nhập transcript tại đây... (Enter: Lưu & Next | Ctrl+Enter: Chỉ lưu | Shift+Enter: Xuống dòng)"
        )
        self._transcript_edit.setAcceptRichText(False)
        self._transcript_edit.textChanged.connect(self._on_transcript_changed)
        self._transcript_edit.save_next_requested.connect(self._on_save_next)
        self._transcript_edit.save_only_requested.connect(self._on_save_only)
        layout.addWidget(self._transcript_edit, stretch=1)

        return frame

    def _build_action_buttons(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._btn_reject = QPushButton("✗  Reject  (Esc)")
        self._btn_reject.setObjectName("btnReject")
        self._btn_reject.setFixedHeight(44)
        self._btn_reject.clicked.connect(self._on_reject)

        self._btn_save_only = QPushButton("💾  Lưu  (Ctrl+Enter)")
        self._btn_save_only.setObjectName("btnSaveOnly")
        self._btn_save_only.setFixedHeight(44)
        self._btn_save_only.clicked.connect(self._on_save_only)

        self._btn_save_next = QPushButton("✓  Lưu & Next  (Enter)")
        self._btn_save_next.setObjectName("btnSaveNext")
        self._btn_save_next.setFixedHeight(44)
        self._btn_save_next.clicked.connect(self._on_save_next)

        layout.addWidget(self._btn_reject)
        layout.addStretch()
        layout.addWidget(self._btn_save_only)
        layout.addWidget(self._btn_save_next)
        return w

    def _build_shortcut_hint(self) -> QLabel:
        lbl = QLabel(
            "⌨  Space: Play/Pause   |   Enter: Lưu & Next   |   Ctrl+Enter: Chỉ lưu   |   "
            "←/→: Prev/Next   |   Esc: Reject   |   Ctrl+R: Replay"
        )
        lbl.setObjectName("shortcutHint")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl

    @staticmethod
    def _make_ctrl_btn(text: str, tooltip: str, obj_name: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(obj_name)
        btn.setToolTip(tooltip)
        btn.setFixedSize(44, 44)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    # ================================================================== #
    # Signal connections
    # ================================================================== #

    def _connect_signals(self) -> None:
        ctrl = self._controller

        # Controller → View
        ctrl.segment_changed.connect(self._on_segment_changed)
        ctrl.stats_updated.connect(self._stats_panel.update_stats)
        ctrl.stats_updated.connect(self._on_stats_for_header)
        ctrl.status_message.connect(self._on_status_message)
        ctrl.error_occurred.connect(self._on_error)
        ctrl.playback_state_changed.connect(self._on_playback_state)
        ctrl.position_changed.connect(self._on_position_changed)
        ctrl.duration_changed.connect(self._on_duration_changed)

        # Buttons → Controller
        self._btn_play.clicked.connect(ctrl.toggle_play_pause)
        self._btn_replay.clicked.connect(ctrl.replay)
        self._btn_prev.clicked.connect(ctrl.navigate_previous)
        self._btn_next.clicked.connect(ctrl.navigate_next)

        # Slider → Controller
        self._wave_bar.slider.sliderMoved.connect(self._on_seek)

    # ================================================================== #
    # Shortcuts
    # ================================================================== #

    def _setup_shortcuts(self) -> None:
        # Space: Play/Pause (only when transcript NOT focused)
        sc_space = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        sc_space.setContext(Qt.ShortcutContext.ApplicationShortcut)
        sc_space.activated.connect(self._on_space)

        # Enter: Save & Next
        sc_enter = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        sc_enter.activated.connect(self._on_enter_shortcut)

        # Ctrl+Enter: Save only
        sc_ctrl_enter = QShortcut(QKeySequence("Ctrl+Return"), self)
        sc_ctrl_enter.activated.connect(self._on_save_only)

        # Left: Previous
        sc_left = QShortcut(QKeySequence(Qt.Key.Key_Left), self)
        sc_left.activated.connect(self._controller.navigate_previous)

        # Right: Next
        sc_right = QShortcut(QKeySequence(Qt.Key.Key_Right), self)
        sc_right.activated.connect(self._controller.navigate_next)

        # Esc: Reject
        sc_esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        sc_esc.activated.connect(self._on_reject)

        # Ctrl+R: Replay
        sc_replay = QShortcut(QKeySequence("Ctrl+R"), self)
        sc_replay.activated.connect(self._controller.replay)

    # ================================================================== #
    # Slots — Controller events
    # ================================================================== #

    @Slot(int)
    def _on_segment_changed(self, index: int) -> None:
        if index == -1:
            self._title_lbl.setText("Không có segment nào khớp với bộ lọc")
            self._transcript_edit.blockSignals(True)
            self._transcript_edit.setPlainText("")
            self._transcript_edit.blockSignals(False)
            self._update_char_count()
            self._wave_bar.slider.setValue(0)
            self._pos_lbl.setText("0:00")
            self._dur_lbl.setText("0:00")
            self._update_timer.stop()
            return

        rec = self._controller.current_record()
        if rec is None:
            return
        total = self._controller.model().total

        self._info_panel.update_record(rec, index, total)
        self._title_lbl.setText(
            f"Segment {index + 1} / {total}  ·  {rec.segment_id}"
        )

        # Restore previous transcript if already labeled/rejected
        # If no transcript exists, fill with pre_label
        self._transcript_edit.blockSignals(True)
        if rec.transcript:
            self._transcript_edit.setPlainText(rec.transcript)
        else:
            self._transcript_edit.setPlainText(getattr(rec, "pre_label", ""))
        self._transcript_edit.blockSignals(False)
        self._update_char_count()

        # Reset audio slider
        self._wave_bar.slider.setValue(0)
        self._pos_lbl.setText("0:00")
        self._dur_lbl.setText("0:00")
        self._update_timer.start()

        # Highlight rejected/labeled
        self._set_transcript_highlight(rec.status)

    @Slot(dict)
    def _on_stats_for_header(self, stats: dict) -> None:
        pct = stats["completion_pct"]
        done = stats["done"]
        total = stats["total"]
        self._progress_lbl.setText(f"{done}/{total} ({pct}%)")
        self._overall_bar.setValue(int(pct * 10))

    @Slot(str)
    def _on_status_message(self, msg: str) -> None:
        self._status_bar.showMessage(msg, 4000)

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Lỗi", msg)

    @Slot(bool)
    def _on_playback_state(self, is_playing: bool) -> None:
        self._btn_play.setText("⏸" if is_playing else "▶")
        if is_playing:
            self._update_timer.start()
        else:
            self._update_timer.stop()

    @Slot(int)
    def _on_position_changed(self, pos_ms: int) -> None:
        player = self._controller.player()
        dur = player.duration
        if dur > 0 and not self._wave_bar.slider.isSliderDown():
            self._wave_bar.slider.setValue(int(pos_ms / dur * 1000))
        self._pos_lbl.setText(self._ms_to_str(pos_ms))

    @Slot(int)
    def _on_duration_changed(self, dur_ms: int) -> None:
        self._dur_lbl.setText(self._ms_to_str(dur_ms))

    @Slot(int)
    def _on_seek(self, value: int) -> None:
        dur = self._controller.player().duration
        if dur > 0:
            pos_ms = int((value / 1000) * dur)
            self._controller.set_audio_position(pos_ms)

    # ================================================================== #
    # Slots — User actions
    # ================================================================== #

    def _on_open_project(self) -> None:
        csv_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file metadata.csv", "",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not csv_path:
            return
        audio_dir = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục chứa file .wav",
            os.path.dirname(csv_path)
        )
        if not audio_dir:
            return
        self._controller.load_project(csv_path, audio_dir)
        self._btn_export_data.setEnabled(True)

    def _on_export_data(self) -> None:
        model = self._controller.model()
        if not model.is_loaded:
            return
        dlg = ExportDialog(model, model._audio_dir or "", self)
        dlg.export_done.connect(
            lambda count, path: self._on_status_message(
                f"📤 Đã xuất {count} bản ghi → {path}"
            )
        )
        dlg.exec()

    def _on_save_next(self) -> None:
        transcript = self._transcript_edit.toPlainText()
        self._controller.save_transcript(transcript)

    def _on_save_only(self) -> None:
        transcript = self._transcript_edit.toPlainText()
        if not transcript.strip():
            self._on_status_message("⚠ Transcript không được để trống!")
            return
        model = self._controller.model()
        model.save_transcript(transcript)
        self._controller.emit_stats()
        self._on_status_message(
            f"✓ Đã lưu segment #{model.current_index + 1}"
        )
        # Refresh display without navigating
        self._on_segment_changed(model.current_index)

    def _on_reject(self) -> None:
        if not self._controller.model().is_loaded:
            return
        reason = RejectDialog.get_reason(self)
        if reason:
            self._controller.reject_segment(reason)

    def _on_jump(self) -> None:
        text = self._jump_input.toPlainText().strip()
        try:
            idx = int(text) - 1
            self._controller.navigate_to(idx)
        except ValueError:
            self._on_status_message("⚠ Vui lòng nhập số nguyên hợp lệ.")

    def _on_filter_changed(self, index: int) -> None:
        data = self._filter_combo.itemData(index)
        if data:
            self._controller.set_filter(data)

    # Speed control helpers

    def _on_speed_slider_changed(self, value: int) -> None:
        rate = value / 100.0
        self._controller.set_playback_rate(rate)
        self._speed_lbl.setText(f"{rate:.2f}x")

    def _on_speed_reset(self) -> None:
        self._speed_slider.setValue(100)
        self._controller.set_playback_rate(1.0)
        self._speed_lbl.setText("1.00x")

    def _on_transcript_changed(self) -> None:
        self._update_char_count()

    def _on_seek(self, value: int) -> None:
        player = self._controller.player()
        dur = player.duration
        if dur > 0:
            player._player.setPosition(int(value / 1000 * dur))

    # Keyboard helpers
    def _on_space(self) -> None:
        # Only toggle play/pause if transcript edit is NOT focused
        if self._transcript_edit.hasFocus():
            return
        self._controller.toggle_play_pause()

    def _on_enter_shortcut(self) -> None:
        # Only trigger save & next if transcript edit is NOT focused
        # (when focused, Enter inserts newline — user uses the button)
        if self._transcript_edit.hasFocus():
            return
        self._on_save_next()

    # ================================================================== #
    # UI helpers
    # ================================================================== #

    def _update_char_count(self) -> None:
        n = len(self._transcript_edit.toPlainText())
        self._char_count_lbl.setText(f"{n} ký tự")

    def _refresh_time_labels(self) -> None:
        player = self._controller.player()
        pos = player.position
        dur = player.duration
        self._pos_lbl.setText(self._ms_to_str(pos))
        self._dur_lbl.setText(self._ms_to_str(dur))
        if dur > 0 and not self._wave_bar.slider.isSliderDown():
            self._wave_bar.slider.setValue(int(pos / dur * 1000))

    @staticmethod
    def _ms_to_str(ms: int) -> str:
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def _set_transcript_highlight(self, status: str) -> None:
        colors = {
            SegmentStatus.LABELED.value:  "#1e3a2f",
            SegmentStatus.REJECTED.value: "#3a1e1e",
            SegmentStatus.PENDING.value:  "#1e1e2e",
        }
        bg = colors.get(status, "#1e1e2e")
        self._transcript_edit.setStyleSheet(
            f"QTextEdit#transcriptEdit {{ background: {bg}; }}"
        )

    def _show_welcome(self) -> None:
        self._status_bar.showMessage(
            "🎙 ASR Dataset Labeler — Nhấn 'Mở dự án' để bắt đầu gán nhãn."
        )

    # ================================================================== #
    # Global stylesheet
    # ================================================================== #

    def _apply_global_styles(self) -> None:  # noqa: C901
        self.setStyleSheet("""
/* ═══════════════════════════════════════════════════════════════════════
   Global — Catppuccin Mocha dark theme
   ═══════════════════════════════════════════════════════════════════════ */
* {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QMainWindow, QWidget {
    background: #1e1e2e;
    color: #cdd6f4;
}

/* ── Sidebar ────────────────────────────────────────────────────────── */
#sidebar {
    background: #181825;
    border-right: 1px solid #313244;
}
#appLogo {
    color: #cba6f7;
    font-size: 20px;
    font-weight: 800;
    padding: 4px 0;
}
#sidebarSep { color: #313244; }

#statsScroll {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: #181825;
    width: 6px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 3px;
}

/* ── Open button ────────────────────────────────────────────────────── */
#btnOpen {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #89b4fa, stop:1 #cba6f7);
    color: #1e1e2e;
    border: none;
    border-radius: 8px;
    font-weight: 700;
    font-size: 13px;
}
#btnOpen:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #a0c4ff, stop:1 #d5b0ff);
}

/* ── Export button ──────────────────────────────────────────────────── */
#btnExportData {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1c3a4a, stop:1 #1c2d3a);
    color: #89dceb;
    border: 1px solid #89dceb;
    border-radius: 8px;
    font-weight: 700;
    font-size: 13px;
}
#btnExportData:hover {
    background: #89dceb;
    color: #1e1e2e;
}
#btnExportData:disabled {
    background: #313244;
    color: #585b70;
    border-color: #45475a;
}

/* ── Jump input ─────────────────────────────────────────────────────── */
#jumpInput {
    background: #27273d;
    border: 1px solid #3a3a5c;
    border-radius: 6px;
    color: #cdd6f4;
    padding: 2px 6px;
}
#btnJump {
    background: #313244;
    color: #89b4fa;
    border: 1px solid #45475a;
    border-radius: 6px;
    font-weight: 600;
}
#btnJump:hover { background: #45475a; }

/* ── Main content ───────────────────────────────────────────────────── */
#mainContent { background: #1e1e2e; }

#mainTitle {
    color: #cba6f7;
    font-size: 16px;
    font-weight: 700;
}
#progressLabel {
    color: #89b4fa;
    font-size: 13px;
    font-weight: 600;
    min-width: 120px;
}
#overallBar {
    background: #313244;
    border-radius: 3px;
    border: none;
}
#overallBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #89b4fa, stop:1 #cba6f7);
    border-radius: 3px;
}

/* ── Segment info panel ─────────────────────────────────────────────── */
#segmentInfoPanel {
    background: #27273d;
    border: 1px solid #3a3a5c;
    border-radius: 10px;
}

/* ── Audio player ───────────────────────────────────────────────────── */
#audioPlayerFrame {
    background: #27273d;
    border: 1px solid #3a3a5c;
    border-radius: 10px;
}
#timeLbl { color: #7f849c; font-size: 12px; }

#audioSlider {
    height: 24px;
}
#audioSlider::groove:horizontal {
    background: #45475a;
    height: 4px;
    border-radius: 2px;
}
#audioSlider::handle:horizontal {
    background: #cba6f7;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
#audioSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #89b4fa, stop:1 #cba6f7);
    border-radius: 2px;
}

/* ── Control buttons ────────────────────────────────────────────────── */
#btnCtrl {
    background: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 22px;
    font-size: 16px;
}
#btnCtrl:hover { background: #45475a; }
#btnCtrl:pressed { background: #585b70; }

#btnPlay {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #89b4fa, stop:1 #cba6f7);
    color: #1e1e2e;
    border: none;
    border-radius: 26px;
    font-size: 20px;
    font-weight: 800;
}
#btnPlay:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #a0c4ff, stop:1 #d5b0ff);
}
#btnPlay:pressed { background: #6e9fd6; }

/* ── Transcript area ────────────────────────────────────────────────── */
#transcriptFrame {
    background: #27273d;
    border: 1px solid #3a3a5c;
    border-radius: 10px;
}
#transcriptLabel {
    color: #89b4fa;
    font-size: 13px;
    font-weight: 700;
}
#charCountLbl { color: #585b70; font-size: 11px; }

QTextEdit#transcriptEdit {
    background: #1e1e2e;
    color: #cdd6f4;
    border: 1.5px solid #3a3a5c;
    border-radius: 8px;
    padding: 10px;
    font-size: 14px;
    line-height: 1.6;
    selection-background-color: #4a4a7a;
}
QTextEdit#transcriptEdit:focus {
    border-color: #cba6f7;
}

/* ── Action buttons ─────────────────────────────────────────────────── */
#btnReject {
    background: #2d1c1c;
    color: #f38ba8;
    border: 1.5px solid #f38ba8;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 700;
    min-width: 160px;
}
#btnReject:hover {
    background: #f38ba8;
    color: #1e1e2e;
}
#btnReject:pressed { background: #c07090; }

#btnSaveOnly {
    background: #1c2a3a;
    color: #89b4fa;
    border: 1.5px solid #89b4fa;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 700;
    min-width: 160px;
}
#btnSaveOnly:hover {
    background: #89b4fa;
    color: #1e1e2e;
}
#btnSaveOnly:pressed { background: #6a90c8; }

#btnSaveNext {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1e3a2a, stop:1 #1a3322);
    color: #a6e3a1;
    border: 1.5px solid #a6e3a1;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 700;
    min-width: 180px;
}
#btnSaveNext:hover {
    background: #a6e3a1;
    color: #1e1e2e;
}
#btnSaveNext:pressed { background: #80c07a; }

/* ── Shortcut hint ──────────────────────────────────────────────────── */
#shortcutHint {
    color: #45475a;
    font-size: 11px;
    padding: 4px 0;
}

/* ── Status bar ─────────────────────────────────────────────────────── */
#mainStatusBar {
    background: #181825;
    color: #7f849c;
    border-top: 1px solid #313244;
    font-size: 12px;
}
""")
