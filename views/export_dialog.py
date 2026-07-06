"""
export_dialog.py — Dialog xuất dữ liệu ASR (View layer)

Cho phép người dùng:
  - Chọn format: JSONL (NeMo/ESPnet/chuẩn) hoặc JSON (mảng)
  - Chọn kiểu đường dẫn audio: tuyệt đối / tương đối / chỉ tên file
  - Xem preview số lượng bản ghi sẽ xuất
  - Chọn file đích và thực hiện xuất
"""

from __future__ import annotations

import json
import os
import zipfile
from typing import Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QRadioButton, QButtonGroup,
    QFileDialog, QTextEdit, QCheckBox, QProgressBar,
    QWidget
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QKeySequence, QShortcut, QFont


# ═══════════════════════════════════════════════════════════════════════
# Worker thread để không block UI khi xuất file lớn
# ═══════════════════════════════════════════════════════════════════════

class _ExportWorker(QObject):
    """Chạy I/O xuất file trong background thread."""

    finished = Signal(int, str)   # (số bản ghi, đường dẫn file)
    error    = Signal(str)

    def __init__(self, records: list[dict], out_path: str, fmt: str, create_zip: bool = False, audio_files: list[tuple[str, str]] = None):
        super().__init__()
        self._records  = records
        self._out_path = out_path
        self._fmt      = fmt   # "jsonl" | "json"
        self._create_zip = create_zip
        self._audio_files = audio_files or []

    def run(self) -> None:
        try:
            count = self._write()
            self.finished.emit(count, self._out_path)
        except Exception as exc:
            self.error.emit(str(exc))

    def _write(self) -> int:
        os.makedirs(os.path.dirname(self._out_path) or ".", exist_ok=True)
        if self._fmt == "jsonl":
            with open(self._out_path, "w", encoding="utf-8") as f:
                for rec in self._records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        else:  # json
            with open(self._out_path, "w", encoding="utf-8") as f:
                json.dump(self._records, f, ensure_ascii=False, indent=2)
                
        if self._create_zip:
            zip_path = self._out_path + ".zip"
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(self._out_path, os.path.basename(self._out_path))
                for abs_path, rel_path in self._audio_files:
                    if os.path.isfile(abs_path):
                        zipf.write(abs_path, rel_path)
            self._out_path = zip_path  # Trả về đường dẫn file zip

        return len(self._records)


# ═══════════════════════════════════════════════════════════════════════
# Export Dialog
# ═══════════════════════════════════════════════════════════════════════

class ExportDialog(QDialog):
    """
    Dialog cấu hình và thực hiện xuất dataset ASR.

    Nhận vào `records_provider` — callable trả về list[SegmentRecord]
    đã được lọc (chỉ labeled).
    """

    export_done = Signal(int, str)   # (count, path) — để MainWindow dùng

    def __init__(self, model, audio_dir: str, parent=None):
        super().__init__(parent)
        self._model     = model
        self._audio_dir = audio_dir

        self.setWindowTitle("Xuất Dataset ASR")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._thread: QThread | None = None
        self._worker: _ExportWorker | None = None

        self._setup_ui()
        self._apply_styles()
        self._refresh_preview()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_body())
        root.addWidget(self._build_footer())

    def _build_header(self) -> QFrame:
        h = QFrame()
        h.setObjectName("expHeader")
        lay = QVBoxLayout(h)
        lay.setContentsMargins(24, 18, 24, 14)
        lay.setSpacing(4)

        title = QLabel("📤 Xuất Dataset ASR")
        title.setObjectName("expTitle")

        sub = QLabel(
            "Xuất các segment đã gán nhãn (có thể bao gồm cả segment bị từ chối)."
        )
        sub.setObjectName("expSubtitle")
        sub.setWordWrap(True)

        lay.addWidget(title)
        lay.addWidget(sub)
        return h

    def _build_body(self) -> QFrame:
        body = QFrame()
        body.setObjectName("expBody")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(20, 16, 20, 8)
        lay.setSpacing(14)

        # ── Format ──────────────────────────────────────────────────────
        lay.addWidget(self._section_label("📄 Định dạng xuất"))
        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(10)

        self._rbtn_jsonl = QRadioButton(
            "JSONL  —  chuẩn NeMo / ESPnet / Kaldi"
        )
        self._rbtn_jsonl.setObjectName("fmtRadio")
        self._rbtn_jsonl.setChecked(True)

        self._rbtn_json  = QRadioButton("JSON  —  mảng đối tượng")
        self._rbtn_json.setObjectName("fmtRadio")

        fg = QButtonGroup(self)
        fg.addButton(self._rbtn_jsonl)
        fg.addButton(self._rbtn_json)

        fmt_row.addWidget(self._rbtn_jsonl)
        fmt_row.addWidget(self._rbtn_json)
        fmt_row.addStretch()
        lay.addLayout(fmt_row)

        # ── Audio path style ─────────────────────────────────────────────
        lay.addWidget(self._section_label("📁 Kiểu đường dẫn audio"))
        self._path_group = QButtonGroup(self)
        path_specs = [
            ("absolute", "Tuyệt đối  —  /full/path/to/audio.wav"),
            ("relative", "Tương đối với thư mục CSV  —  segments/audio.wav"),
            ("filename", "Chỉ tên file  —  audio.wav"),
        ]
        self._path_radios: dict[str, QRadioButton] = {}
        for key, label in path_specs:
            rb = QRadioButton(label)
            rb.setObjectName("fmtRadio")
            if key == "absolute":
                rb.setChecked(True)
            self._path_group.addButton(rb)
            self._path_radios[key] = rb
            rb.toggled.connect(self._refresh_preview)
            lay.addWidget(rb)

        # ── Extra fields ─────────────────────────────────────────────────
        lay.addWidget(self._section_label("➕ Tùy chọn & Trường bổ sung"))
        
        self._chk_include_rejected = QCheckBox("Bao gồm các segment bị Reject")
        self._chk_include_rejected.setObjectName("extraChk")
        self._chk_include_rejected.setChecked(False)
        self._chk_include_rejected.toggled.connect(self._refresh_preview)
        lay.addWidget(self._chk_include_rejected)
        
        self._chk_duration   = QCheckBox("duration  (giây)")
        self._chk_segment_id = QCheckBox("segment_id")
        self._chk_source     = QCheckBox("source_file")

        self._chk_duration.setChecked(True)
        self._chk_segment_id.setChecked(True)
        self._chk_source.setChecked(False)

        self._chk_zip = QCheckBox("Nén thành file ZIP (chứa kết quả và Audio)")
        self._chk_zip.setChecked(False)
        self._chk_zip.setObjectName("extraChk")
        lay.addWidget(self._chk_zip)

        for chk in (self._chk_duration, self._chk_segment_id, self._chk_source):
            chk.setObjectName("extraChk")
            chk.toggled.connect(self._refresh_preview)
            lay.addWidget(chk)

        # ── Preview ──────────────────────────────────────────────────────
        lay.addWidget(self._section_label("👁 Xem trước (3 bản ghi đầu)"))

        self._preview_count = QLabel("")
        self._preview_count.setObjectName("previewCount")
        lay.addWidget(self._preview_count)

        self._preview_box = QTextEdit()
        self._preview_box.setObjectName("previewBox")
        self._preview_box.setReadOnly(True)
        self._preview_box.setFixedHeight(120)
        self._preview_box.setFont(QFont("Consolas", 10))
        lay.addWidget(self._preview_box)

        # ── Progress ─────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setObjectName("expProgress")
        self._progress.setRange(0, 0)    # indeterminate
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        lay.addWidget(self._progress)

        return body

    def _build_footer(self) -> QFrame:
        f = QFrame()
        f.setObjectName("expFooter")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(20, 12, 20, 16)
        lay.setSpacing(10)

        self._btn_cancel = QPushButton("Đóng")
        self._btn_cancel.setObjectName("btnCancel")
        self._btn_cancel.setFixedHeight(38)
        self._btn_cancel.clicked.connect(self.reject)

        self._btn_export = QPushButton("📤  Chọn file & Xuất")
        self._btn_export.setObjectName("btnExport")
        self._btn_export.setFixedHeight(38)
        self._btn_export.clicked.connect(self._on_export_clicked)

        lay.addWidget(self._btn_cancel)
        lay.addStretch()
        lay.addWidget(self._btn_export)
        return f

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionLabel")
        return lbl

    # ------------------------------------------------------------------ #
    # Logic
    # ------------------------------------------------------------------ #

    def _build_records(self, max_preview: int | None = None) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
        """Tạo list dict từ các segment và danh sách file audio."""
        from models.data_model import SegmentStatus

        records: list[dict] = []
        audio_files: list[tuple[str, str]] = []
        stats = self._model
        csv_dir = os.path.dirname(stats._csv_path or "") if stats._csv_path else ""
        include_rejected = self._chk_include_rejected.isChecked()

        for rec in stats._records:
            if rec.status == SegmentStatus.LABELED.value:
                pass
            elif rec.status == SegmentStatus.REJECTED.value and include_rejected:
                pass
            else:
                continue

            # Đường dẫn audio
            path_mode = next(
                (k for k, rb in self._path_radios.items() if rb.isChecked()),
                "absolute"
            )
            if path_mode == "absolute":
                audio_path = os.path.abspath(rec.audio_path).replace("\\", "/")
            elif path_mode == "relative":
                audio_path = os.path.relpath(rec.audio_path, csv_dir).replace("\\", "/")
            else:
                audio_path = os.path.basename(rec.audio_path)

            entry: dict[str, Any] = {
                "audio_filepath": audio_path,
                "text": rec.transcript,
            }
            if rec.status == SegmentStatus.REJECTED.value:
                entry["status"] = "rejected"
                entry["reject_reason"] = rec.reject_reason
            
            if self._chk_duration.isChecked():
                entry["duration"] = round(rec.duration, 3)
            if self._chk_segment_id.isChecked():
                entry["segment_id"] = rec.segment_id
            if self._chk_source.isChecked():
                entry["source_file"] = rec.source_file

            records.append(entry)
            
            # audio_path in json might be absolute. Inside zip, we'll store it by basename if absolute.
            zip_audio_path = audio_path if path_mode != "absolute" else os.path.basename(audio_path)
            audio_files.append((rec.audio_path, zip_audio_path))

            if max_preview is not None and len(records) >= max_preview:
                break

        return records, audio_files

    def _refresh_preview(self) -> None:
        """Cập nhật ô preview."""
        from models.data_model import SegmentStatus
        try:
            include_rejected = self._chk_include_rejected.isChecked()
            valid_count = 0
            for r in self._model._records:
                if r.status == SegmentStatus.LABELED.value:
                    valid_count += 1
                elif r.status == SegmentStatus.REJECTED.value and include_rejected:
                    valid_count += 1
                    
            self._preview_count.setText(
                f"Tổng sẽ xuất: <b>{valid_count}</b> bản ghi"
            )
            self._preview_count.setTextFormat(Qt.TextFormat.RichText)
            self._btn_export.setEnabled(valid_count > 0)

            preview_recs, _ = self._build_records(max_preview=3)
            if not preview_recs:
                self._preview_box.setPlainText("(Chưa có segment nào được gán nhãn)")
                return

            lines = []
            fmt = "jsonl" if self._rbtn_jsonl.isChecked() else "json"
            if fmt == "jsonl":
                for r in preview_recs:
                    lines.append(json.dumps(r, ensure_ascii=False))
                if valid_count > 3:
                    lines.append(f"... ({valid_count - 3} bản ghi nữa)")
            else:
                lines.append("[")
                for i, r in enumerate(preview_recs):
                    sep = "," if i < len(preview_recs) - 1 or valid_count > 3 else ""
                    lines.append("  " + json.dumps(r, ensure_ascii=False) + sep)
                if valid_count > 3:
                    lines.append(f"  ... ({valid_count - 3} bản ghi nữa)")
                lines.append("]")

            self._preview_box.setPlainText("\n".join(lines))
        except Exception as e:
            self._preview_box.setPlainText(f"Lỗi preview: {e}")

    def _on_export_clicked(self) -> None:
        fmt  = "jsonl" if self._rbtn_jsonl.isChecked() else "json"
        ext  = "JSONL Files (*.jsonl)" if fmt == "jsonl" else "JSON Files (*.json)"
        name = "asr_dataset.jsonl"    if fmt == "jsonl" else "asr_dataset.json"

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Lưu file xuất", name, f"{ext};;All Files (*)"
        )
        if not out_path:
            return

        # Build full record list
        all_records, audio_files = self._build_records()
        if not all_records:
            return

        # Chạy export trong background thread
        create_zip = getattr(self, '_chk_zip', None) and self._chk_zip.isChecked()
        self._set_busy(True)
        self._thread = QThread(self)
        self._worker = _ExportWorker(all_records, out_path, fmt, create_zip, audio_files)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_export_done)
        self._worker.error.connect(self._on_export_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _on_export_done(self, count: int, path: str) -> None:
        self._set_busy(False)
        self.export_done.emit(count, path)
        # Hiển thị kết quả trong preview
        self._preview_count.setText(
            f"✅ Đã xuất <b>{count}</b> bản ghi → <code>{path}</code>"
        )

    def _on_export_error(self, msg: str) -> None:
        self._set_busy(False)
        self._preview_count.setText(f"❌ Lỗi: {msg}")

    def _set_busy(self, busy: bool) -> None:
        self._btn_export.setEnabled(not busy)
        self._btn_cancel.setEnabled(not busy)
        self._progress.setVisible(busy)

    # ------------------------------------------------------------------ #
    # Styles
    # ------------------------------------------------------------------ #

    def _apply_styles(self) -> None:
        self.setStyleSheet("""
            QDialog { background: #1e1e2e; }

            #expHeader {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #1c2d3a, stop:1 #1e1e2e);
                border-bottom: 1px solid #3a3a5c;
            }
            #expTitle {
                color: #89dceb;
                font-size: 17px;
                font-weight: 700;
            }
            #expSubtitle { color: #a6adc8; font-size: 12px; }

            #expBody { background: #1e1e2e; }

            #sectionLabel {
                color: #cba6f7;
                font-size: 12px;
                font-weight: 700;
                margin-top: 4px;
            }

            QRadioButton#fmtRadio {
                color: #cdd6f4;
                font-size: 12px;
                spacing: 8px;
            }
            QRadioButton#fmtRadio::indicator {
                width: 15px; height: 15px;
                border-radius: 8px;
                border: 2px solid #6c7086;
                background: #1e1e2e;
            }
            QRadioButton#fmtRadio::indicator:checked {
                border-color: #89dceb;
                background: #89dceb;
            }

            QCheckBox#extraChk {
                color: #cdd6f4;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox#extraChk::indicator {
                width: 15px; height: 15px;
                border-radius: 4px;
                border: 2px solid #6c7086;
                background: #1e1e2e;
            }
            QCheckBox#extraChk::indicator:checked {
                border-color: #89dceb;
                background: #89dceb;
            }

            #previewCount {
                color: #a6adc8;
                font-size: 12px;
            }
            #previewBox {
                background: #11111b;
                color: #a6e3a1;
                border: 1px solid #3a3a5c;
                border-radius: 6px;
                padding: 6px;
            }

            #expProgress {
                background: #313244;
                border-radius: 3px;
                border: none;
            }
            #expProgress::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #89dceb, stop:1 #89b4fa);
                border-radius: 3px;
            }

            #expFooter {
                background: #181825;
                border-top: 1px solid #3a3a5c;
            }
            #btnCancel {
                background: #313244; color: #cdd6f4;
                border: 1px solid #45475a; border-radius: 6px;
                padding: 0 18px; font-size: 13px;
            }
            #btnCancel:hover { background: #45475a; }
            #btnCancel:disabled { color: #585b70; }

            #btnExport {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #1c3a4a, stop:1 #1c2d3a);
                color: #89dceb;
                border: 1.5px solid #89dceb;
                border-radius: 6px;
                padding: 0 22px;
                font-size: 13px;
                font-weight: 700;
            }
            #btnExport:hover {
                background: #89dceb;
                color: #1e1e2e;
            }
            #btnExport:disabled {
                background: #313244;
                color: #585b70;
                border-color: #45475a;
            }
        """)
