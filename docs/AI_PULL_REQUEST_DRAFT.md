# Nội dung Pull Request

**Title:** feat(ai): tích hợp tab Thực nghiệm dự báo và các mô hình HGB đã huấn luyện

**Base:** main

**Compare:** feature/ai-forecast-integration

## Thay đổi

Các mô hình VietSafe trước đây chạy ở thư mục nghiên cứu và server demo riêng. PR này đưa phần suy luận vào cấu trúc backend/frontend từ PR #2: người dùng mở tab **Thực nghiệm dự báo**, chọn bộ dữ liệu, điểm quan trắc và thời điểm lịch sử, chạy checkpoint đã huấn luyện, xem kết quả và tải JSON ngay từ server VietSafe.

Ba bài toán giữ nguyên ý nghĩa đầu ra: Bellinge dự báo mực nước trong hệ thống thoát nước (m); FloodNet New York dự báo xác suất xuất hiện ngập mặt đường; SZ-Taxi dự báo tốc độ theo thang dữ liệu gốc chưa xác minh km/h. Khối theo quy tắc trên bản đồ Hà Nội được ghi rõ **Kịch bản bản đồ — mô phỏng**.

## Cấu trúc triển khai

- `backend/vietsafe/forecasting/`: hợp đồng, service và ba adapter suy luận độc lập; giữ đúng thứ tự đặc trưng và tiền xử lý của thí nghiệm cũ.
- `web/controllers/ai_controller.py`: `/api/ai/catalog`, `/api/ai/sites`, `/api/ai/times`, POST `/api/ai/predict` qua router hiện có.
- `frontend/forecast-lab.html`, JS/CSS riêng: chọn bài toán/điểm/thời gian, hiển thị lịch sử đầu vào và các chân trời dự báo, xuất JSON; bỏ qua phản hồi cũ khi đổi lựa chọn.
- Nạp mô hình theo nhu cầu, kiểm tra SHA-256 và phiên bản sklearn, cache tại máy. Thiếu cấu hình/artifact trả trạng thái rõ ràng; ứng dụng cơ sở vẫn chạy không cần thư viện ML.
- `requirements-ai.txt`, `scripts/start-ai.ps1` và tài liệu chạy/review. Runtime không huấn luyện hoặc tải dữ liệu.

## Phạm vi

Đây là suy luận trên dữ liệu lịch sử quốc tế, chưa kiểm định tại Hà Nội. Không đưa đầu ra nghiên cứu vào cảnh báo công cộng, đóng đường hoặc lựa chọn tuyến. Không commit checkpoint, dữ liệu, SQLite hoặc nhật ký máy cá nhân.

Hợp đồng sáu đặc trưng và đầu ra road-risk ở PR #4 chưa khớp với các checkpoint này; cần phối hợp nhóm dữ liệu để mở rộng hợp đồng trước khi nối nguồn trực tuyến. Bảng so sánh metrics và chức năng xem quan trắc tương lai để đối chiếu là phần bổ sung tiếp theo, chưa nằm trong PR.

## Kiểm chứng

- Backend: 69 test đạt, gồm 8 test đối chiếu artifact thật và 10 test HTTP/hợp đồng AI.
- Giao diện VietSafe hiện có: 34 kiểm tra đạt.
- Trang AI với checkpoint thật: 21 kiểm tra đạt; khi chưa cấu hình artifact: 5 kiểm tra đạt.
- Bellinge: đối chiếu 12 mốc × 4 cảm biến × 2 chân trời với kết quả đã lưu.
- SZ-Taxi: đối chiếu 12 mốc × 156 đoạn × 3 chân trời; FloodNet đối chiếu xác suất đã hiệu chỉnh.

Môi trường: Python 3.13.5, scikit-learn 1.6.1, Node 24.19.0. Đây là kiểm tra tích hợp và giữ nguyên kết quả thí nghiệm; không phải một đánh giá mô hình mới. Test artifact được bỏ qua khi máy không có dữ liệu, hướng dẫn chạy ở `docs/AI_FORECAST.md`.

## Điểm cần review

- Nhóm AI: thứ tự đặc trưng, đơn vị, điều kiện chất lượng và kết quả đối chiếu checkpoint.
- Nhóm dữ liệu: trường đầu vào cần bổ sung và hợp đồng phiên bản tiếp theo với PR #4.
- Nhóm kiến trúc/giao diện: phân chia trách nhiệm, điều hướng, trạng thái thiếu dữ liệu và cách phân biệt thí nghiệm với kịch bản bản đồ.

Chi tiết: `docs/AI_INTEGRATION_PLAN.md`, `docs/AI_TAB_POSITIONING.md`, `docs/AI_FORECAST.md`.
