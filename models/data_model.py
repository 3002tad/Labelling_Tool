"""
data_model.py — Model layer (MVC)

Quản lý toàn bộ dữ liệu: đọc/ghi metadata.csv, trạng thái từng segment,
thống kê và tìm vị trí tiếp tục.
"""

import os
import json
import pandas as pd
from enum import Enum
from typing import Optional, Dict, Any, List


class SegmentStatus(str, Enum):
    PENDING = "pending"
    LABELED = "labeled"
    REJECTED = "rejected"


class RejectReason(str, Enum):
    NOISE = "Noise"
    OVERLAP = "Overlap"
    CLIPPING = "Clipping"
    UNINTELLIGIBLE = "Unintelligible"


# Tất cả lý do reject hợp lệ (dùng để hiển thị trên UI)
REJECT_REASONS: List[str] = [r.value for r in RejectReason]

# Tên các cột sẽ được ghi vào CSV
COL_STATUS = "status"
COL_REJECT_REASON = "reject_reason"
COL_TRANSCRIPT = "transcript"


class SegmentRecord:
    """Biểu diễn một dòng trong metadata.csv."""

    def __init__(self, row: Dict[str, Any], audio_dir: str):
        self.segment_id: str = str(row.get("segment_id", ""))
        self.segment_index: int = int(row.get("segment_index", 0))
        self.source_file: str = str(row.get("source_file", ""))
        self.sample_rate: int = int(row.get("sample_rate", 16000))
        self.channels: int = int(row.get("channels", 1))
        self.start: float = float(row.get("start", 0.0))
        self.end: float = float(row.get("end", 0.0))
        self.duration: float = float(row.get("duration", 0.0))
        self.status: str = str(row.get(COL_STATUS, SegmentStatus.PENDING.value))
        self.reject_reason: str = str(row.get(COL_REJECT_REASON, ""))
        self.transcript: str = str(row.get(COL_TRANSCRIPT, ""))
        self.pre_label: str = ""

        # Ưu tiên tên file trong cột segment_id (file tồn tại trong audio_dir)
        candidate = os.path.join(audio_dir, self.segment_id)
        if os.path.isfile(candidate):
            self.audio_path: str = candidate
        else:
            # Fallback: thử tìm theo basename của audio_filepath gốc
            original = str(row.get("audio_filepath", ""))
            basename = os.path.basename(original)
            fallback = os.path.join(audio_dir, basename)
            self.audio_path = fallback if os.path.isfile(fallback) else candidate

    @property
    def is_labeled(self) -> bool:
        return self.status == SegmentStatus.LABELED.value

    @property
    def is_rejected(self) -> bool:
        return self.status == SegmentStatus.REJECTED.value

    @property
    def is_pending(self) -> bool:
        return self.status == SegmentStatus.PENDING.value

    @property
    def audio_exists(self) -> bool:
        return os.path.isfile(self.audio_path)


class DataModel:
    """
    Model chứa toàn bộ logic nghiệp vụ:
    - Load / save metadata.csv
    - Truy cập từng segment theo index
    - Cập nhật trạng thái (labeled / rejected)
    - Tính thống kê real-time
    - Tìm vị trí tiếp tục từ lần trước
    """

    def __init__(self):
        self._csv_path: Optional[str] = None
        self._audio_dir: Optional[str] = None
        self._df: Optional[pd.DataFrame] = None
        self._records: List[SegmentRecord] = []
        self._current_index: int = 0
        self._filter: str = "all"
        self._filtered_indices: List[int] = []
        self._current_idx_in_filter: int = -1

    # ------------------------------------------------------------------ #
    # Public API — Load
    # ------------------------------------------------------------------ #

    def load(self, csv_path: str, audio_dir: str) -> None:
        """Nạp dữ liệu từ file CSV và thư mục audio."""
        if not os.path.isfile(csv_path):
            raise FileNotFoundError(f"Không tìm thấy file: {csv_path}")
        if not os.path.isdir(audio_dir):
            raise NotADirectoryError(f"Thư mục không tồn tại: {audio_dir}")

        self._csv_path = csv_path
        self._audio_dir = audio_dir
        self._df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)

        # Đảm bảo các cột nhãn luôn tồn tại
        for col, default in [
            (COL_STATUS, SegmentStatus.PENDING.value),
            (COL_REJECT_REASON, ""),
            (COL_TRANSCRIPT, ""),
        ]:
            if col not in self._df.columns:
                self._df[col] = default

        # Load pre_labels if exists
        pre_labels = {}
        pre_labels_path = os.path.join(os.path.dirname(csv_path), "pre_labels.json")
        if not os.path.isfile(pre_labels_path):
            pre_labels_path = os.path.join(os.path.dirname(csv_path), "pre_label.json")
        if os.path.isfile(pre_labels_path):
            try:
                with open(pre_labels_path, "r", encoding="utf-8") as f:
                    pre_labels = json.load(f)
            except Exception:
                pass

        # Xây danh sách SegmentRecord
        self._records = []
        for _, row in self._df.iterrows():
            rec = SegmentRecord(row.to_dict(), audio_dir)
            if rec.segment_id in pre_labels and "text" in pre_labels[rec.segment_id]:
                rec.pre_label = pre_labels[rec.segment_id]["text"]
            self._records.append(rec)

        # Apply default filter
        self.set_filter("all")

        # Tiếp tục từ vị trí chưa xử lý đầu tiên
        self._current_index = self._find_resume_index()
        try:
            self._current_idx_in_filter = self._filtered_indices.index(self._current_index)
        except ValueError:
            pass

    def _find_resume_index(self) -> int:
        """Trả về index của segment pending đầu tiên; nếu hết thì trả về 0."""
        for i, rec in enumerate(self._records):
            if rec.is_pending:
                return i
        return 0

    # ------------------------------------------------------------------ #
    # Public API — Navigation
    # ------------------------------------------------------------------ #

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def total(self) -> int:
        return len(self._records)

    def set_filter(self, filter_status: str) -> None:
        """filter_status: 'all', 'pending', 'labeled', 'rejected'"""
        self._filter = filter_status
        self._apply_filter()

    def _apply_filter(self) -> None:
        self._filtered_indices = []
        for i, rec in enumerate(self._records):
            if self._filter == "all" or rec.status == self._filter:
                self._filtered_indices.append(i)
        
        if not self._filtered_indices:
            self._current_idx_in_filter = -1
            self._current_index = -1
        else:
            found = False
            for f_idx, real_idx in enumerate(self._filtered_indices):
                if real_idx >= self._current_index:
                    self._current_idx_in_filter = f_idx
                    self._current_index = real_idx
                    found = True
                    break
            if not found:
                self._current_idx_in_filter = len(self._filtered_indices) - 1
                self._current_index = self._filtered_indices[-1]

    def go_to(self, index: int) -> bool:
        """Chuyển đến segment theo index. Trả về True nếu hợp lệ."""
        if 0 <= index < self.total:
            self._current_index = index
            try:
                self._current_idx_in_filter = self._filtered_indices.index(index)
            except ValueError:
                self.set_filter("all")
            return True
        return False

    def next(self) -> bool:
        if self._current_idx_in_filter + 1 < len(self._filtered_indices):
            self._current_idx_in_filter += 1
            self._current_index = self._filtered_indices[self._current_idx_in_filter]
            return True
        return False

    def previous(self) -> bool:
        if self._current_idx_in_filter - 1 >= 0:
            self._current_idx_in_filter -= 1
            self._current_index = self._filtered_indices[self._current_idx_in_filter]
            return True
        return False

    def current_record(self) -> Optional[SegmentRecord]:
        if not self._records or self._current_index < 0 or self._current_index >= len(self._records):
            return None
        return self._records[self._current_index]

    # ------------------------------------------------------------------ #
    # Public API — Label / Reject
    # ------------------------------------------------------------------ #

    def save_transcript(self, transcript: str) -> None:
        """Gán nhãn transcript cho segment hiện tại và lưu CSV."""
        rec = self.current_record()
        if rec is None:
            return
        rec.transcript = transcript.strip()
        rec.status = SegmentStatus.LABELED.value
        rec.reject_reason = ""
        self._flush_record(self._current_index)
        self._save_csv()

    def reject_segment(self, reason: str) -> None:
        """
        Đánh dấu segment hiện tại là rejected và lưu CSV.
        `reason` có thể là một lý do đơn hoặc nhiều lý do cách nhau bằng dấu phẩy,
        VD: 'Noise' hoặc 'Noise,Clipping'.
        """
        rec = self.current_record()
        if rec is None:
            return
        rec.status = SegmentStatus.REJECTED.value
        rec.reject_reason = reason
        rec.transcript = ""
        self._flush_record(self._current_index)
        self._save_csv()

    # ------------------------------------------------------------------ #
    # Public API — Statistics
    # ------------------------------------------------------------------ #

    def statistics(self) -> Dict[str, Any]:
        """Trả về dict thống kê real-time."""
        total = self.total
        labeled = sum(1 for r in self._records if r.is_labeled)
        rejected = sum(1 for r in self._records if r.is_rejected)
        pending = total - labeled - rejected
        done = labeled + rejected
        completion = (done / total * 100) if total > 0 else 0.0

        reject_by_reason: Dict[str, int] = {r: 0 for r in REJECT_REASONS}
        for rec in self._records:
            if rec.is_rejected and rec.reject_reason:
                # Hỗ trợ cả lý do đơn lẫn nhiều lý do ("Noise,Clipping")
                for part in rec.reject_reason.split(","):
                    part = part.strip()
                    if part in reject_by_reason:
                        reject_by_reason[part] += 1

        total_duration = sum(r.duration for r in self._records)
        labeled_duration = sum(r.duration for r in self._records if r.is_labeled)

        return {
            "total": total,
            "labeled": labeled,
            "rejected": rejected,
            "pending": pending,
            "done": done,
            "completion_pct": round(completion, 1),
            "reject_by_reason": reject_by_reason,
            "total_duration_s": total_duration,
            "labeled_duration_s": labeled_duration,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _flush_record(self, index: int) -> None:
        """Ghi lại trạng thái của SegmentRecord vào DataFrame."""
        if self._df is None:
            return
        rec = self._records[index]
        self._df.at[index, COL_STATUS] = rec.status
        self._df.at[index, COL_REJECT_REASON] = rec.reject_reason
        self._df.at[index, COL_TRANSCRIPT] = rec.transcript

    def _save_csv(self) -> None:
        """Lưu toàn bộ DataFrame ra CSV (atomically)."""
        if self._df is None or self._csv_path is None:
            return
        tmp_path = self._csv_path + ".tmp"
        self._df.to_csv(tmp_path, index=False, encoding="utf-8")
        os.replace(tmp_path, self._csv_path)

    # ------------------------------------------------------------------ #
    # Utility
    # ------------------------------------------------------------------ #

    @property
    def is_loaded(self) -> bool:
        return self._df is not None and len(self._records) > 0

    def get_record(self, index: int) -> Optional[SegmentRecord]:
        if 0 <= index < self.total:
            return self._records[index]
        return None
