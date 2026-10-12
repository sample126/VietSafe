# Mô phỏng xuất hiện ngập và độ sâu theo điểm

Ngày 13/10/2026. Chế độ local, dữ liệu giả lập; không phải kết quả dự báo Hà Nội đã kiểm chứng.

## Chạy và sử dụng

Bấm `scripts/start-flood-simulator.cmd`, mở http://127.0.0.1:8791/flood-simulator.html.
Hoặc chạy server VietSafe bình thường và mở `/flood-simulator.html` ở cùng cổng.
Tab Thực nghiệm dự báo trên trang chính và trang `/forecast-lab.html` đều có liên kết vào.
Không cần cài thư viện ML, SWMM, GPU, tải dữ liệu hoặc kết nối Internet cho trang mô phỏng.

Chọn một trong bốn kịch bản, chỉnh thông số, bấm **Tính diễn biến ngập**.
Đầu ra: độ sâu tại đúng phút +30/+60; có xác nhận xuất hiện ngập trong toàn cửa sổ hay không;
thời điểm bắt đầu vượt ngưỡng và đủ thời gian duy trì; đường diễn biến mỗi phút;
so sánh nếu công suất thoát giảm một nửa; tải JSON/CSV có nhãn giả lập.
Sửa thông số làm ẩn kết quả cũ. Một yêu cầu cũ trả về muộn không được ghi đè trạng thái mới.

## Dữ liệu của hai bài toán

Một chuỗi độ sâu mặt đường liên tục có thể dùng tạo nhãn cho cả hai tác vụ:

| Dữ liệu | Khi dùng dữ liệu thực | Trong mô phỏng hiện tại |
|---|---|---|
| Mã điểm, tọa độ, mốc 0 | Xác định vị trí đo và độ sâu so với mặt đường | Một vùng trũng giả định, không gán tọa độ hoặc tên đường thật |
| Độ sâu hiện tại và lịch sử | Quan trắc 1–5 phút nếu có; cờ thiếu/chất lượng | Người dùng nhập độ sâu ban đầu; diễn biến do mô hình tính |
| Mưa quá khứ | Trạm/radar đồng bộ, rõ mm trong khoảng hay mm/h | Chưa mô hình hóa độ ẩm/lịch sử; trạng thái ban đầu do người dùng đặt |
| Mưa tương lai | Bản dự báo có issued_at/valid_time, biết tại lúc phát dự báo | 12 cường độ giả định, mỗi khoảng 5 phút |
| Đặc điểm khu vực | Diện tích hứng nước/vùng trũng, địa hình, mặt phủ | Các tham số người dùng điều chỉnh |
| Thoát nước, vận hành | Công trình, khả năng tiêu, bơm/cửa điều tiết, nước dâng | Công suất thoát hiệu dụng và tỷ lệ giảm do tắc nghẽn |
| Nhãn tương lai | Độ sâu thực đo để tạo nhãn khởi phát và hồi quy | Chuỗi do cân bằng nước sinh, không phải nhãn quan trắc |

Để học/đánh giá tại Hà Nội, thu cả lúc khô, mưa không ngập và nhiều trận độc lập.
Mỗi quan trắc có thời gian đo, thời gian nhận, đơn vị, mốc đo và cờ chất lượng.
Không thay số liệu thiếu bằng 0. Nhãn tương lai dùng để huấn luyện/đánh giá, không làm đầu vào dự báo.

## Mô hình đang thực sự chạy

`backend/vietsafe/forecasting/scenario.py`: mô hình khái niệm cân bằng nước một vùng trũng.
Mượn cách biểu diễn vùng trũng của nghiên cứu cũ `vietsafe-flood-ai`, nhưng triển khai bằng
thư viện chuẩn Python; **không gọi SWMM, không nạp checkpoint ExtraTrees/HGB/Bellinge/FloodNet**.
Không thay đổi số liệu hoặc kết quả nghiên cứu cũ.

Ở mỗi bước một giây:

- Dòng vào (m³/s) = mưa (mm/h) / 1000 / 3600 × diện tích hứng nước (ha) × 10000 × hệ số dòng chảy.
- Công suất hiệu dụng (m³/s) = công suất nhập (L/s) / 1000 × (1 − tỷ lệ tắc nghẽn / 100).
- Dòng thoát = công suất hiệu dụng × min(1, sqrt(độ sâu hiện tại / 0,1 m)); giới hạn bởi lượng nước có sẵn.
- Thể tích mới = thể tích cũ + nước vào − nước thoát. Độ sâu = thể tích / diện tích vùng trũng.

Đây là giả định quan hệ thoát nước, chưa được hiệu chỉnh từ đường đặc tính công trình địa phương.
Mưa và các đặc điểm khu vực là kịch bản điều kiện: "nếu mưa như vậy thì nước biến đổi thế nào".
Không thể dùng kết quả này làm bằng chứng dự báo thời tiết hoặc ngập ngoài thực địa.
Không có mạng cống, truyền dòng giữa các điểm, thời gian tập trung nước, tràn ra vùng bên cạnh,
mực nước sông, bơm hay bề mặt 2D. Mô hình không mô tả đầy đủ cả một tuyến đường.

## Định nghĩa sự kiện và độ sâu

Mặc định: ngưỡng 5 cm, duy trì ít nhất 10 phút theo bước tính 1 giây. Đây là quy ước thử nghiệm.
Xác nhận một đợt chỉ khi toàn bộ thời gian duy trì nằm trong cửa sổ 30 hoặc 60 phút.
Ví dụ: vượt ngưỡng lúc phút 25, đủ 10 phút lúc phút 35 => chưa xác nhận ở cửa sổ 30, có ở 60.
Nếu đã đạt ngưỡng ngay lúc bắt đầu, không báo một đợt khởi phát mới; vẫn dự báo diễn biến độ sâu.
Sự kiện có thể xảy ra rồi rút trước phút 60: nhãn sự kiện trong cửa sổ và độ sâu tại phút 60 là hai đại lượng khác nhau.

Một lần chạy xác định không tạo ra xác suất. API trả `probability: null`.
Đường so sánh công suất giảm 50% là độ nhạy tham số; không là khoảng tin cậy.

## API và tổ chức code

- `GET /api/flood-simulation/catalog`: 4 kịch bản tổng hợp, giới hạn thông số và nguồn dữ liệu.
- `POST /api/flood-simulation/predict`: JSON gồm đủ 8 thông số số học và `rain_mm_h` dài 12.
  Theo quy tắc POST hiện có: header `X-VietSafe: local`, Origin cùng ứng dụng.
- Sai loại, thiếu/thừa trường, NaN/Infinity, ngoài giới hạn, diện tích bất hợp lý => HTTP 400.
- Trả 61 thời điểm, hai hạn dự báo, cân bằng thể tích, thông số/nguồn/giới hạn và phiên bản.
- Không ghi phản ánh, không thay kịch bản bản đồ chung, không gửi cảnh báo hay thay tuyến đi.

Controller: `backend/vietsafe/web/controllers/flood_scenario_controller.py`.
Giao diện: `frontend/flood-simulator.html`, `frontend/css/flood-simulator.css`,
`frontend/js/views/flood-simulator.js`.

## Khi có dữ liệu thực: AI chạy ở đâu?

Huấn luyện và suy luận là hai công việc riêng:

1. Trên máy nghiên cứu: chuẩn hóa dữ liệu Hà Nội, chia theo trận/thời gian, huấn luyện ứng viên,
   kiểm chứng cả báo sai/bỏ sót và sai số độ sâu; lưu checkpoint, bộ đặc trưng và thông tin phiên bản.
2. Ở backend Python của VietSafe: thêm adapter cho model địa phương, kiểm tra dữ liệu mới,
   nạp checkpoint phù hợp và gọi predict/predict_proba khi nhận yêu cầu. Không học lại mỗi lần bấm web.
3. Frontend hiển thị đầu ra và nguồn rõ ràng: mô phỏng, nghiên cứu quốc tế hoặc mô hình địa phương đã kiểm chứng.

Backend có thể chạy ngay trên máy cá nhân (local) hoặc trên máy chủ khi triển khai web.
GitHub lưu mã nguồn; GitHub không tự chạy dự báo và không cần lưu bộ dữ liệu/model lớn vào repo.
Nghiên cứu hiện có ở `forecasting/service.py` nạp artifact từ thư mục cục bộ theo `VIETSAFE_AI_RESEARCH_ROOT`.
Adapter AI Hà Nội/chức năng upload dữ liệu mới chưa được triển khai trong thay đổi này.
Không ghép dữ liệu giả lập này vào tập kiểm tra quan trắc của bài báo.

## Kiểm tra

Backend: `cd backend` rồi `python -m unittest tests.test_flood_scenario -v`.
Frontend: `node frontend/tests/flood-simulator-smoke.mjs` (cần dev dependencies, biến `PYTHON` nếu cần).
Kiểm tra trường hợp khô, rút nước, tắc hoàn toàn, công suất suy giảm, bảo toàn nước,
mốc xác nhận sự kiện, kiểm tra đầu vào, API, phản hồi muộn và file xuất.

Đã kiểm tra ngày 13/10/2026: 13 test backend của mô phỏng, 20 kiểm tra giao diện
mô phỏng và 34 kiểm tra hồi quy giao diện hiện có đều đạt. Lượt toàn bộ backend trước
khi thêm test sự kiện rút nước chạy 81 test, đạt 73 và bỏ qua 8 test artifact nghiên cứu
do không bật biến xác minh artifact. Test bổ sung đã chạy cùng bộ 13 test mô phỏng và đạt.
Đã xem giao diện ở chiều rộng 1366 và 390 px, kiểm tra không tràn ngang và biểu đồ tự co giãn.
