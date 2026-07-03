"""
app_controller.py — Controller layer (MVC)

Cầu nối giữa DataModel và MainWindow:
- Điều phối điều hướng (prev/next/go-to)
- Gửi lệnh phát nhạc qua AudioPlayer
- Xử lý save & reject, cập nhật View
- Phát signals để View refresh
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal, Slot, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from models.data_model import DataModel, SegmentRecord, REJECT_REASONS

if TYPE_CHECKING:
    pass


class AudioPlayer(QObject):
    """
    Bọc QMediaPlayer để phát file WAV.
    Cung cấp giao diện đơn giản: play, pause, replay, stop.
    """

    playback_state_changed = Signal(bool)   # True = đang phát
    position_changed = Signal(int)          # ms
    duration_changed = Signal(int)          # ms
    error_occurred = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(1.0)

        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.positionChanged.connect(self._emit_position)
        self._player.durationChanged.connect(self._emit_duration)
        self._player.errorOccurred.connect(self._on_error)

    def load(self, file_path: str) -> None:
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(file_path))

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def replay(self) -> None:
        self._player.setPosition(0)
        self._player.play()

    def set_position(self, pos_ms: int) -> None:
        self._player.setPosition(pos_ms)

    def toggle_play_pause(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
        else:
            self.play()

    @property
    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    @property
    def position(self) -> int:
        return self._player.position()

    @property
    def duration(self) -> int:
        return self._player.duration()

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self.playback_state_changed.emit(
            state == QMediaPlayer.PlaybackState.PlayingState
        )

    def _emit_position(self, pos) -> None:
        self.position_changed.emit(int(pos))

    def _emit_duration(self, dur) -> None:
        self.duration_changed.emit(int(dur))

    def _on_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        self.error_occurred.emit(f"Audio error: {error_string}")


class AppController(QObject):
    """
    Controller chính của ứng dụng.

    Signals phát ra để View lắng nghe:
      - segment_changed(index)  : yêu cầu View hiển thị segment mới
      - stats_updated(dict)     : cập nhật panel thống kê
      - status_message(str)     : hiển thị thông báo tạm thời
      - error_occurred(str)     : lỗi nghiêm trọng
    """

    # All signals — must be declared at class level for Qt metaclass
    segment_changed = Signal(int)
    stats_updated = Signal(dict)
    status_message = Signal(str)
    error_occurred = Signal(str)
    playback_state_changed = Signal(bool)
    position_changed = Signal(int)
    duration_changed = Signal(int)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._model = DataModel()
        self._player = AudioPlayer(self)

        # Forward audio player signals
        self._player.playback_state_changed.connect(self._on_playback_state_changed)
        self._player.position_changed.connect(self._on_position_changed)
        self._player.duration_changed.connect(self._on_duration_changed)
        self._player.error_occurred.connect(self.error_occurred)

        # Reference to View (set later via set_view)
        self._view = None

    # ------------------------------------------------------------------ #
    # Forward AudioPlayer signals to View
    # ------------------------------------------------------------------ #

    def _on_playback_state_changed(self, playing: bool) -> None:
        self.playback_state_changed.emit(playing)

    def _on_position_changed(self, pos: int) -> None:
        self.position_changed.emit(pos)

    def _on_duration_changed(self, dur: int) -> None:
        self.duration_changed.emit(dur)

    # ------------------------------------------------------------------ #
    # Public API — Setup
    # ------------------------------------------------------------------ #

    def set_view(self, view) -> None:
        self._view = view

    def load_project(self, csv_path: str, audio_dir: str) -> bool:
        """Nạp dự án và điều hướng đến segment đầu tiên cần xử lý."""
        try:
            self._model.load(csv_path, audio_dir)
            self._load_current_segment()
            self._emit_stats()
            self.status_message.emit(
                f"Đã tải {self._model.total} segments. "
                f"Tiếp tục tại #{self._model.current_index + 1}."
            )
            return True
        except Exception as exc:
            self.error_occurred.emit(str(exc))
            return False

    # ------------------------------------------------------------------ #
    # Public API — Navigation
    # ------------------------------------------------------------------ #

    @Slot()
    def navigate_previous(self) -> None:
        if not self._model.is_loaded:
            return
        if self._model.previous():
            self._load_current_segment()

    @Slot()
    def navigate_next(self) -> None:
        if not self._model.is_loaded:
            return
        if self._model.next():
            self._load_current_segment()
        else:
            self.status_message.emit("Đã đến cuối danh sách.")

    @Slot(int)
    def navigate_to(self, index: int) -> None:
        if not self._model.is_loaded:
            return
        if self._model.go_to(index):
            self._load_current_segment()

    @Slot(str)
    def set_filter(self, filter_status: str) -> None:
        if not self._model.is_loaded:
            return
        self._model.set_filter(filter_status)
        self._load_current_segment()

    # ------------------------------------------------------------------ #
    # Public API — Playback
    # ------------------------------------------------------------------ #

    @Slot()
    def toggle_play_pause(self) -> None:
        self._player.toggle_play_pause()

    @Slot()
    def replay(self) -> None:
        self._player.replay()

    @Slot(int)
    def set_audio_position(self, pos_ms: int) -> None:
        self._player.set_position(pos_ms)

    # ------------------------------------------------------------------ #
    # Public API — Label actions
    # ------------------------------------------------------------------ #

    @Slot(str)
    def save_transcript(self, transcript: str) -> None:
        """Lưu transcript và chuyển sang segment tiếp theo."""
        if not self._model.is_loaded:
            return
        if not transcript.strip():
            self.status_message.emit("⚠ Transcript không được để trống!")
            return
        self._player.stop()
        self._model.save_transcript(transcript)
        self._emit_stats()
        self.status_message.emit(
            f"✓ Đã lưu segment #{self._model.current_index + 1}"
        )
        self.navigate_next()

    @Slot(str)
    def reject_segment(self, reason: str) -> None:
        """
        Reject segment hiện tại.
        `reason` có thể là một hoặc nhiều lý do cách nhau bằng dấu phẩy,
        VD: 'Noise' hoặc 'Noise,Clipping'.
        """
        if not self._model.is_loaded:
            return
        # Validate từng phần của chuỗi lý do
        parts = [p.strip() for p in reason.split(",") if p.strip()]
        invalid = [p for p in parts if p not in REJECT_REASONS]
        if not parts or invalid:
            self.error_occurred.emit(
                f"Lý do reject không hợp lệ: {', '.join(invalid or ['(trống)'])}"
            )
            return
        self._player.stop()
        self._model.reject_segment(reason)
        self._emit_stats()
        self.status_message.emit(
            f"✗ Đã reject segment #{self._model.current_index + 1} — {reason}"
        )
        self.navigate_next()


    # ------------------------------------------------------------------ #
    # Public API — Queries
    # ------------------------------------------------------------------ #

    def current_record(self) -> Optional[SegmentRecord]:
        return self._model.current_record()

    def model(self) -> DataModel:
        return self._model

    def player(self) -> AudioPlayer:
        return self._player

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _load_current_segment(self) -> None:
        """Tải audio và phát, rồi phát signal để View cập nhật."""
        rec = self._model.current_record()
        if rec is None:
            self._player.stop()
            self.segment_changed.emit(-1)
            self.status_message.emit("Không có dữ liệu khớp với bộ lọc.")
            return
        if rec.audio_exists:
            self._player.load(rec.audio_path)
            self._player.play()
        else:
            self.error_occurred.emit(
                f"Không tìm thấy file audio:\n{rec.audio_path}"
            )
        self.segment_changed.emit(self._model.current_index)

    def emit_stats(self) -> None:
        """Public wrapper — View can call this to refresh stats panel."""
        self.stats_updated.emit(self._model.statistics())

    def _emit_stats(self) -> None:
        self.emit_stats()
