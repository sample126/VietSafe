# VietSafe — Prototype T-GCN đã tích hợp

## File đã thay đổi

- `public/index.html`: nạp các module nâng cấp.
- `public/app.js`: sửa nguồn tile bản đồ Hà Nội, fallback nhiều cấp và sơ đồ ngoại tuyến.
- `public/enhancements.css`: giao diện cho timeline, heatmap, vùng ngập, SOS, hành trình, độ tin cậy.
- `public/enhancements.js`: timeline 15/30/45/60 phút, lớp dữ liệu, SOS, cảnh báo gần, tùy chọn tuyến, theo dõi hành trình.
- `public/tgcn.js`: lớp T-GCN thử nghiệm, Risk Score, dự báo 15/30/60 phút và tự đề xuất đổi tuyến.
- `engine.py`: hỗ trợ `priority` và `avoid_flood` trong tính tuyến.
- `server.py`: đọc `priority` và `avoid_flood` ở `/api/routes`.
- `README.md`: bổ sung mô tả bản tích hợp.

## Trạng thái T-GCN

T-GCN hiện là **mô phỏng tích hợp UI/logic**, sử dụng snapshot và forecast sẵn có để biểu diễn luồng dự báo. Chưa có trọng số mô hình T-GCN đã huấn luyện. Các chỉ số MAE/RMSE/MAPE và confidence trên UI là dữ liệu thử nghiệm.

## Kiểm thử

- `node --check public/app.js`: PASS
- `node --check public/enhancements.js`: PASS
- `node --check public/tgcn.js`: PASS
- `python -m unittest discover -s tests -v`: 17/17 PASS
- HTTP smoke test: trang chủ, CSS/JS nâng cấp và `/api/routes?...priority=balanced&avoid_flood=1` đều phản hồi thành công.
