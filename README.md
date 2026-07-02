# 🎙 ASR Dataset Labeler

Ứng dụng desktop (PySide6) gán nhãn dữ liệu ASR từ các segment audio đã được cắt sẵn.

## Cấu trúc dự án (MVC)

```
ASR_Dataset_Label/
├── main.py                        # Entry point
├── requirements.txt
├── models/
│   ├── __init__.py
│   └── data_model.py              # Model: đọc/ghi CSV, trạng thái, thống kê
├── controllers/
│   ├── __init__.py
│   └── app_controller.py          # Controller: điều hướng, phát audio, xử lý nhãn
├── views/
│   ├── __init__.py
│   ├── main_window.py             # View: cửa sổ chính, toàn bộ UI
│   ├── stats_panel.py             # View: panel thống kê real-time
│   └── reject_dialog.py           # View: dialog chọn lý do reject
├── segments/                      # Thư mục chứa các file .wav
└── metadata.csv                   # File dữ liệu đầu vào/đầu ra
```

## Yêu cầu cài đặt

```bash
pip install PySide6 pandas
```

## Chạy ứng dụng

```bash
python main.py
```

Sau đó:
1. Nhấn **"Mở dự án"** → chọn `metadata.csv`
2. Chọn thư mục chứa file `.wav`
3. Ứng dụng tự động tiếp tục từ vị trí chưa xử lý

## Phím tắt

| Phím | Hành động |
|------|-----------|
| `Space` | Play / Pause |
| `Enter` | Lưu transcript & chuyển Next |
| `Ctrl+Enter` | Chỉ lưu (không chuyển) |
| `←` / `→` | Segment trước / tiếp |
| `Esc` | Mở dialog Reject |
| `Ctrl+R` | Phát lại từ đầu |

## Lý do Reject

| Lý do | Mô tả |
|-------|-------|
| Noise | Tiếng ồn nền quá lớn |
| Overlap | Nhiều giọng nói chồng chéo |
| Clipping | Âm thanh bị cắt hoặc méo |
| Unintelligible | Không thể hiểu nội dung |

## Cấu trúc metadata.csv sau khi gán nhãn

Cột bổ sung sau khi gán nhãn:

| Cột | Giá trị |
|-----|---------|
| `status` | `pending` / `labeled` / `rejected` |
| `reject_reason` | Tên lý do (chỉ khi rejected) |
| `transcript` | Nội dung transcript (chỉ khi labeled) |
