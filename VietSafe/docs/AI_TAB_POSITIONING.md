# Định vị tab “Thực nghiệm dự báo” của VietSafe

Bản định vị được áp dụng theo quy trình chủ dự án duyệt ngày **12/10/2026**. Tài liệu này mô tả cách trình bày sản phẩm cho nhánh `feature/ai-forecast-integration`; không phải xác nhận đã có dự báo trực tuyến ở Hà Nội.

## 1. Tab này dùng để làm gì?

**Tab thể hiện năng lực thực nghiệm của module dự báo:** sử dụng mô hình nhóm đã huấn luyện để chạy dự báo trên dữ liệu quan trắc, xem kết quả tại từng thời điểm và đối chiếu với kết quả đánh giá nghiên cứu.

Vị trí máy huấn luyện và địa bàn dữ liệu là hai thông tin khác nhau:

- Mô hình được nhóm huấn luyện trên máy cá nhân; khi chạy web hiện tại, checkpoint được nạp và suy luận tại máy đó.
- Dữ liệu huấn luyện/kiểm thử đến từ các bộ nghiên cứu ở nước ngoài. Vì vậy, kết quả đo được phản ánh các bộ dữ liệu và điều kiện thử nghiệm ấy.
- Nhấn “Chạy dự báo” chỉ chạy suy luận bằng mô hình đã học, không huấn luyện lại.
- Một bản VietSafe chạy trên máy khác hoặc hosting không tự truy cập được checkpoint trên máy cá nhân. Nó phải được cung cấp artifact hợp lệ, hoặc kết nối tới một dịch vụ suy luận được thiết kế và triển khai riêng. PR hiện tại chọn cách cung cấp artifact cục bộ.

**Tên tab đề xuất: “Thực nghiệm dự báo”.** Nếu cần giữ điều hướng ngắn, có thể giữ “Dự báo” và gắn nhãn “Thực nghiệm” nổi bật ở đầu trang. Khuyến nghị dùng tên đầy đủ để người xem hiểu đúng ngay từ thanh điều hướng.

Không cần hạ thấp kết quả bằng cách gọi toàn bộ là “dữ liệu giả” hoặc “mô hình minh họa”. Bellinge/FloodNet là các thí nghiệm dùng quan trắc thật; điều cần nói rõ là dữ liệu lịch sử, địa bàn nước ngoài và phạm vi kiểm chứng.

## 2. Nội dung có thể đặt ngay trên giao diện

**Tiêu đề:** Thực nghiệm dự báo

**Mô tả ngắn:**

> Khám phá kết quả của các mô hình VietSafe đã huấn luyện trên dữ liệu quan trắc. Chọn điểm và thời điểm lịch sử để chạy dự báo, xem diễn biến và kết quả đánh giá.

**Dòng thông tin luôn thấy:**

> Dữ liệu nghiên cứu quốc tế · Thử nghiệm trên chuỗi quan trắc lịch sử · Chưa hiệu chỉnh cho Hà Nội

**Thông tin của lần chạy**, ví dụ với Bellinge:

| Trường hiển thị | Nội dung |
|---|---|
| Bài toán | Dự báo mực nước trong hệ thống thoát nước |
| Dữ liệu | Bellinge, Đan Mạch |
| Mô hình | HistGradientBoostingRegressor (HGB), sử dụng lịch sử nhiều điểm |
| Điểm quan trắc | ID cảm biến trong bộ dữ liệu |
| Thời điểm phát dự báo | Thời điểm lịch sử đã chọn, ghi rõ đồng hồ nguồn |
| Chân trời dự báo | Sau 30 phút và sau 60 phút |
| Đơn vị | Mét so với mốc của cảm biến |
| Cách chạy | Suy luận bằng mô hình đã huấn luyện |

**Nút chính:** “Chạy dự báo thử nghiệm”.

Với FloodNet, đổi tên bài toán thành **“Dự báo khả năng xuất hiện ngập mặt đường”**, ghi New York, xác suất %, ngưỡng sự kiện và cửa sổ 30/60 phút. Không dùng cùng một nhãn “mức ngập” cho mực nước Bellinge và xác suất FloodNet.

## 3. Bố cục đề xuất và trạng thái triển khai

```text
THỰC NGHIỆM DỰ BÁO
Nguồn dữ liệu · Địa bàn · Dữ liệu lịch sử · Phiên bản mô hình

[ Chạy dự báo thử nghiệm ]    [ Kết quả đánh giá nghiên cứu ]

Chọn bài toán → Chọn điểm → Chọn thời điểm → Chạy dự báo
Quan trắc đến mốc phát | Dự báo +30/+60 | Giải thích đơn vị
[ Xem quan trắc thực tế sau mốc phát để đối chiếu ]

Điều kiện áp dụng tại địa bàn mới / Lộ trình Hà Nội
```

| Thành phần | Trạng thái |
|---|---|
| API và bộ chạy checkpoint HGB cho Bellinge/FloodNet/SZ-Taxi | Đã có trong branch cục bộ |
| Chọn điểm/thời điểm, hiển thị dự báo, lịch sử đầu vào và tải JSON | Đã có trong branch cục bộ |
| Nhãn nghiên cứu, nguồn, đơn vị; không chuyển dự báo nước ngoài sang bản đồ Hà Nội | Đã có trong branch cục bộ |
| Đổi tên tab/nút theo câu chữ trong tài liệu này | Đã áp dụng “Thực nghiệm dự báo” và “Chạy dự báo thử nghiệm”; khối cũ ghi rõ là mô phỏng |
| Bảng kết quả nghiên cứu so sánh các mô hình | Kế hoạch bổ sung; chưa có endpoint/giao diện trong branch |
| Hiển thị quan trắc tương lai riêng để đối chiếu một lần dự báo | Kế hoạch bổ sung; API hiện tại chưa trả phần này |
| Dự báo bằng quan trắc trực tuyến tại Hà Nội | Giai đoạn sau; cần dữ liệu, mô hình phù hợp và kiểm định |

Với bài báo tập trung vào ngập, nên mở mặc định **Bellinge** và đặt **FloodNet** là thí nghiệm liên quan đến ngập mặt đường. **SZ-Taxi** nằm trong mục giao thông riêng của sản phẩm, không gộp vào kết quả bài báo ngập. Cách này giữ được module giao thông đã làm và vẫn có một câu chuyện nghiên cứu nhất quán.

## 4. Giải thích việc dự báo trên một ngày đã xảy ra

Ví dụ chọn một thời điểm T trong dữ liệu lịch sử:

1. Mô hình chỉ nhận quan trắc đã có tại hoặc trước T theo giao thức nghiên cứu.
2. Nó dự báo giá trị ở T + 30 và T + 60 phút, hoặc khả năng có sự kiện trong từng cửa sổ tương lai, tùy bài toán.
3. Nếu mở phần đối chiếu, quan trắc sau T chỉ dùng để đánh giá; phải được tải/hiển thị riêng và không trở thành đặc trưng đầu vào.

Đó là **dự báo hồi cứu**: chạy lại quy trình dự báo tại một mốc trong quá khứ để kiểm tra mô hình. Nó vẫn là phép thử dự báo có ý nghĩa, nhưng không nên gọi là “dự báo thời gian thực hôm nay”. Cần kiểm tra cả tính sẵn có của đầu vào và quy trình xử lý dữ liệu; việc tồn tại một chuỗi lịch sử không tự chứng minh điều kiện vận hành trực tuyến.

Trong biểu đồ, phân biệt ba phần bằng chú giải rõ: **quan trắc quá khứ**, **dự báo**, **quan trắc thực tế để đối chiếu**. Vẽ một đường dọc tại T. Phần đối chiếu nên là tùy chọn; không tự đưa nó vào API suy luận hoặc ẩn việc đã biết tương lai.

## 5. Trình bày kết quả bài báo trên web

Mục “Kết quả đánh giá nghiên cứu” nên đọc báo cáo/metrics đã đóng băng. Không phải mỗi người bấm nút là huấn luyện hoặc đánh giá lại toàn bộ nghiên cứu.

Với Bellinge, các hàng so sánh gồm:

- Giữ nguyên giá trị hiện tại (Persistence).
- Histogram-based Gradient Boosting Regressor (HGB) tại từng điểm.
- HGB có lịch sử toàn bộ điểm.
- Gated Recurrent Unit (GRU).
- Temporal Graph Convolutional Network (T-GCN) theo thiết lập nghiên cứu đã mô tả.

Các cột cần có: chân trời 30/60 phút, **Mean Absolute Error (MAE — sai số tuyệt đối trung bình)**, **Root Mean Squared Error (RMSE — căn bậc hai sai số bình phương trung bình)**, đơn vị và phạm vi tập kiểm thử. Với mạng nơ-ron, ghi rõ cách tổng hợp các lần chạy/seed theo đúng báo cáo, không chọn một lần chạy thuận lợi rồi coi đó là kết quả chung.

Để người xem hiểu, mô tả ngắn MAE là trung bình độ lệch tuyệt đối giữa dự báo và quan trắc trên các cặp được đánh giá; RMSE nhấn mạnh hơn những sai lệch lớn do bình phương sai số trước khi lấy trung bình và căn. **Sai số của một điểm tại một lần chạy không phải MAE/RMSE của toàn bộ tập test.** Không đổi MAE thành “độ chính xác %”.

Kết luận mẫu phù hợp với hồ sơ hiện có:

> Trong thiết lập thực nghiệm trên dữ liệu Bellinge, HGB sử dụng lịch sử nhiều điểm đạt MAE tổng thể thấp nhất trong các phương án được so sánh. Kết quả này là cơ sở lựa chọn mô hình thử nghiệm của nhóm; thứ hạng có thể khác theo thước đo, điều kiện quan trắc và địa bàn.

Nếu đưa số liệu, phải lấy từ `results/test_metrics.json` và báo cáo đã xác minh. Ví dụ HGB toàn mạng có MAE khoảng 0,809 cm ở +30 phút và 1,435 cm ở +60 phút; **RMSE +60 phút của HGB tại điểm nhỉnh hơn HGB toàn mạng**, nên không dùng nhãn “tốt nhất mọi tiêu chí”. Các sai số này là sai số mực nước cảm biến, không phải sai số dự báo độ ngập đường tại Hà Nội.

Phần đánh giá FloodNet cần dùng các chỉ số phân loại/xác suất tương ứng trong hồ sơ của chính nó; không đặt cạnh MAE mực nước để xếp hạng chung.

## 6. Tab hiện có trên bản đồ Hà Nội cần trình bày thế nào?

Code hiện có trước tích hợp chứa dự báo theo kịch bản quy tắc trên các đoạn đường Hà Nội. Code AI mới dùng các bộ dữ liệu quốc tế khác. Hai nguồn kết quả này cần được nhận biết ngay trên giao diện.

Đề xuất: lấy phần **Thực nghiệm dự báo** làm nội dung chính của tab. Nếu giữ khối cũ để kiểm tra UX, đặt trong mục riêng **“Kịch bản bản đồ — mô phỏng”**, ghi rõ là quy tắc/kịch bản và chưa phải kết quả của mô hình nghiên cứu. Không vẽ mực nước Bellinge hoặc xác suất FloodNet lên tọa độ Hà Nội; không để người xem chọn đường Hà Nội rồi nhận số từ checkpoint nước ngoài.

Đây là chỉnh sửa tên và cách sắp xếp nội dung; không cần viết lại kiến trúc dự án. Giữ `data-view="forecast"`/ID kỹ thuật để giảm xung đột; đổi nhãn người dùng nhìn thấy và bố cục bên trong.

## 7. Cách giới thiệu khi trình bày sản phẩm

> “VietSafe có một khu vực thực nghiệm dành cho module dự báo. Tại đây, chúng tôi chạy các mô hình đã huấn luyện trên dữ liệu quan trắc công khai và trình bày kết quả theo từng điểm, thời điểm và chân trời dự báo. Nghiên cứu hiện tại đánh giá các phương pháp dự báo mực nước trên dữ liệu Bellinge của Đan Mạch; phần ngập mặt đường có thí nghiệm riêng trên FloodNet ở New York. Những kết quả này giúp chúng tôi lựa chọn phương pháp và xây dựng module phần mềm có thể tiếp nhận nguồn dữ liệu phù hợp. Bước tiếp theo là thu thập, chuẩn hóa dữ liệu tại Hà Nội, hiệu chỉnh mô hình và kiểm định tại địa phương trước khi cung cấp dự báo vận hành.”

Nếu được hỏi “Vì sao sản phẩm hướng tới Hà Nội nhưng kết quả ở nước ngoài?”:

> “Chúng tôi sử dụng các bộ dữ liệu có quan trắc và thông tin đi kèm để thực hiện một đánh giá có thể kiểm chứng. Module phần mềm đã được chuẩn bị để tích hợp vào VietSafe, còn việc triển khai tại Hà Nội cần được đánh giá bằng dữ liệu Hà Nội. Chúng tôi tách rõ bằng chứng nghiên cứu hiện có và mục tiêu triển khai.”

Cách diễn đạt này nhấn mạnh điều nhóm đã làm được mà không biến mục tiêu tương lai thành kết quả hiện tại. **Khả năng tái sử dụng kiến trúc và quy trình không đồng nghĩa checkpoint đang có đã áp dụng tốt cho mọi thành phố.**

## 8. Chốt phạm vi PR và thứ tự triển khai đề xuất

**PR tích hợp đầu tiên:** code suy luận hiện có, hợp đồng/API, điểm vào trang nghiên cứu, trạng thái thiếu dữ liệu, kiểm thử, hướng dẫn cấp artifact và câu chữ phân biệt nghiên cứu/kịch bản bản đồ. Đã được chủ dự án cho phép hoàn thiện, kiểm tra và xuất bản branch/PR; việc merge vẫn cần review.

**Phần bổ sung tiếp theo:** bảng đánh giá các mô hình từ metrics đã lưu và đối chiếu dự báo–quan trắc ở từng lần chạy. Có thể là PR riêng để nhóm review rõ phạm vi; không ghi là chức năng đã hoàn thành trong PR đầu.

**Giai đoạn triển khai địa phương:** hợp đồng dữ liệu với nhóm Data, đầu vào quan trắc/độ trễ/chất lượng, ánh xạ sensor/road, hiệu chỉnh hoặc huấn luyện mô hình phù hợp, đánh giá độc lập rồi mới nối cảnh báo vận hành.

Hướng dẫn Git và nhánh hiện tại: [AI_INTEGRATION_PLAN.md](AI_INTEGRATION_PLAN.md). **Branch được xuất bản theo quy trình đã duyệt; không tự merge vào main.**
