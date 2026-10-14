# Kế hoạch tích hợp module dự báo VietSafe

Ngày chuẩn bị: 11/10/2026. **Chủ dự án đã duyệt quy trình xuất bản branch và Pull Request ngày 12/10/2026.**

Cập nhật định vị ngày **12/10/2026** theo yêu cầu chủ dự án: tab dành cho mô hình đã huấn luyện tại máy và kết quả thực nghiệm trên dữ liệu nước ngoài. Đã đổi tên tab thành **“Thực nghiệm dự báo”**, đổi nút chạy và tách nhãn khối cũ **“Kịch bản bản đồ — mô phỏng”**. Nội dung và phạm vi các bước tiếp theo nằm ở [AI_TAB_POSITIONING.md](AI_TAB_POSITIONING.md).

## 1. Mục tiêu của nhánh

Đưa phần suy luận của các mô hình đã xây dựng vào cấu trúc backend/frontend hiện tại của VietSafe, để cả nhóm có một cách chạy và một giao diện kiểm tra chung. Đây là bước tích hợp phần mềm của nghiên cứu, chưa phải hoàn thành hệ thống dự báo trực tuyến tại Hà Nội.

Nhánh `feature/ai-forecast-integration` được tạo từ `origin/main` ở commit `d6119d23c54c12f0f85d65833256270fd355557b`, sau khi PR #2 của **hoang10Ar** đã merge. Checkout riêng giúp giữ nguyên thư mục làm việc cũ của nhóm. Code không chép trở lại `server.py`/`public/` cũ.

Tham chiếu đã đọc:

- `VIETSAFE_AI_CONTEXT.md` và `VIETSAFE_AI_HANDOFF_2026-10-07.md` trong workspace nghiên cứu; ưu tiên trạng thái cập nhật ngày 07/10.
- [PR #2 — Restructure folder architecture for better team collaboration](https://github.com/sample126/VietSafe/pull/2).
- [PR #4 — Integration/07 quality handoff](https://github.com/sample126/VietSafe/pull/4), còn mở tại thời điểm kiểm tra, head `6ae0a51b4fa16eabe00696796b1ff3d475a2b625`. Chỉ đọc hợp đồng, chưa merge/cherry-pick code của nhánh này.

## 2. Phạm vi đã triển khai để review

| Phần | Code | Hành vi |
|---|---|---|
| Hợp đồng đầu ra | `backend/vietsafe/forecasting/contracts.py` | Tách đại lượng, đơn vị, nguồn, thời điểm, chế độ nghiên cứu và phiên bản |
| Nạp và điều phối | `forecasting/service.py`, `artifact_manifest.json` | Cấu hình artifact bằng biến môi trường; xác minh SHA-256; nạp một lần; thiếu dữ liệu trả trạng thái rõ ràng |
| Mô hình mực nước | `forecasting/bellinge.py` | HGB toàn mạng, lịch sử 24 bước × 5 phút, dự báo mực nước 30/60 phút |
| Mô hình xuất hiện ngập | `forecasting/floodnet.py` | HGB phân loại + sigmoid, 42 đặc trưng, xác suất ngập trong 30/60 phút |
| Mô hình tốc độ | `forecasting/sztaxi.py` | HGB lân cận, lịch sử 12 bước × 15 phút, tốc độ 15/30/60 phút |
| API | `web/controllers/ai_controller.py` | Danh mục, điểm, thời điểm và chạy dự báo; dùng router hiện có |
| Giao diện | `frontend/forecast-lab.html`, `js/views/ai-forecast.js`, `css/ai-forecast.css` | Chọn bài toán → điểm → thời điểm → kết quả, đồ thị lịch sử và tải JSON |
| Điểm vào từ web | Khối mới trong tab Dự báo ở `frontend/index.html` | Mở trang AI cùng server, cùng frontend; không cần chạy server demo thứ hai |
| Khởi động | `scripts/start-ai.ps1`, `requirements-ai.txt` | Cách chạy riêng cho tùy chọn AI, vẫn dùng `python -m vietsafe` |
| Kiểm tra | `backend/tests/test_ai*.py`, `frontend/tests/ai-smoke.mjs` | API, thiếu cấu hình, đơn vị, dữ liệu quá khứ, đối chiếu checkpoint, thao tác giao diện |

Luồng xử lý:

```text
Trang Dự báo của VietSafe
  → Trang Thực nghiệm dự báo
  → /api/ai/*
  → Controller HTTP → Service → Bộ xử lý của từng bài toán
  → Checkpoint và dữ liệu cục bộ đã xác minh
  → Kết quả có nguồn + đơn vị + thời điểm + phiên bản
```

Ứng dụng cơ sở tiếp tục chạy bằng thư viện chuẩn. Các thư viện ML là tùy chọn, chỉ được nạp khi bật mô hình. Các tệp dữ liệu và checkpoint không đưa vào Git; repository chứa code, hướng dẫn và mã băm để xác nhận đúng bộ artifact.

## 3. Những điểm khoa học cần giữ đúng

| Bộ dữ liệu | Dự báo thực sự | Không được diễn giải thành |
|---|---|---|
| Bellinge | Mực nước tại cảm biến trong hệ thống thoát nước, đơn vị mét | Độ ngập trên mặt đường Hà Nội |
| FloodNet NYC | Xác suất bắt đầu một đợt có độ sâu ≥ 5 cm liên tiếp hai khoảng 5 phút trong cửa sổ tương lai, với hiện tại dưới ngưỡng | Số mét ngập hoặc xác suất ngập của địa chỉ bất kỳ |
| SZ-Taxi | Tốc độ theo thang dữ liệu gốc | km/h đã được xác nhận, hoặc nhãn tai nạn/ùn tắc đã kiểm chứng |

Chọn HGB đã có checkpoint và kết quả đối chiếu. GRU/T-GCN vẫn thuộc bộ so sánh nghiên cứu; lần tích hợp đầu chưa đưa toàn bộ mô hình vào runtime. Không huấn luyện lại, không chỉnh ngưỡng theo tập test, không tuyên bố có mô hình mới. Mô phỏng SWMM giả định ở bản demo cũ vẫn là một nguồn thí nghiệm riêng; chưa nhập thành dữ liệu ngập thực tế.

Các cửa sổ trình diễn được lấy từ dữ liệu lịch sử đã đánh giá. Đặc biệt, danh sách Bellinge giữ các mốc đã đủ nhãn tương lai trong benchmark, nên đây là tập phát lại đã tuyển chọn, không phải thống kê độ sẵn sàng ngoài thực địa. Chỉ đầu vào tại hoặc trước mốc phát dự báo đi vào mô hình; phản hồi API không kèm nhãn/quan trắc tương lai. FloodNet có ví dụ mặc định chọn sau khi biết kết quả, chỉ để minh họa.

## 4. Kết nối với PR #4 của nhóm dữ liệu

Hợp đồng hiện có trong PR #4 chưa thể đưa thẳng vào các checkpoint này:

| Hợp đồng PR #4 | Yêu cầu của mô hình hiện tại | Việc cần thống nhất |
|---|---|---|
| Sáu đặc trưng mưa, độ ẩm đất, cao độ; bước 30 phút | Bellinge cần mực nước nhiều cảm biến, mặt nạ thiếu dữ liệu, mưa 5 phút và lịch sử 24 bước | Bổ sung loại đầu vào mực nước; quy tắc thời gian, mốc cao độ và chất lượng |
| Không có chuỗi độ ngập mặt đường | FloodNet cần 42 đặc trưng theo đúng bộ tạo đặc trưng, độ ngập và độ trễ mưa | Chuẩn hóa phép đo, lịch sử, độ trễ và hiệu chỉnh theo địa phương |
| Không có lịch sử tốc độ/đồ thị đầy đủ | SZ-Taxi cần tốc độ 15 phút và cấu trúc lân cận | Bổ sung quan trắc tốc độ, đơn vị đã xác minh và network_version |
| Đầu ra hiện cho phép `flood_risk`, `speed_km_h`, `risk`, `label` | Bellinge trả mực nước; NYC trả xác suất; tốc độ SZ chưa xác minh km/h | Phiên bản hợp đồng mới hoặc kiểu output mới, không ép đổi đơn vị |

Nhánh này dùng namespace `/api/ai/*` và schema `vietsafe.ai-replay.v1`. Chưa thêm giá trị AI vào `/api/snapshot`, lớp màu nguy cơ của bản đồ, cảnh báo công cộng hay thuật toán tìm tuyến. Bước nối đó chỉ thực hiện sau khi nhóm chốt hợp đồng và có dữ liệu thích hợp. Không mặc định sáu đặc trưng hiện có là đủ cho mô hình đã học.

## 5. Lộ trình tiếp theo đề xuất

1. **Review và duyệt nhánh hiện tại:** kiến trúc, thao tác web, ý nghĩa đầu ra, cách cấp artifact. Đầu ra: một PR tích hợp chạy được và có kiểm tra hồi quy.
   Tên “Thực nghiệm dự báo”, câu chữ của tab và nhãn “Kịch bản bản đồ — mô phỏng” đã được áp dụng. Phần so sánh metrics và xem quan trắc tương lai là phạm vi bổ sung, chưa nằm trong code runtime đã kiểm thử.
2. **Chốt hợp đồng với nhóm dữ liệu:** xác định sensor/road ID, network_version, đơn vị, tần suất, mốc thời gian, độ trễ, missing mask, nguồn và độ mới. Đầu ra: tài liệu schema + fixture hợp lệ/không hợp lệ + test liên nhóm.
3. **Tạo adapter đầu vào trực tuyến:** provider → kho chuỗi thời gian → tạo đặc trưng → suy luận; chỉ hỗ trợ địa điểm có đủ dữ liệu và mô hình phù hợp. Đầu ra: API trả dự báo hoặc lý do từ chối có thể kiểm chứng.
4. **Nối vào bản đồ sau kiểm định:** định vị đúng điểm; hiển thị đại lượng và độ mới; quyết định chuyển thành mức cảnh báo cần hiệu chỉnh và kiểm tra độc lập. Đầu ra: một kịch bản end-to-end trên địa bàn có dữ liệu.

Đề xuất người review theo phân công nhóm: **Sâm + Minh (VB2K5)** kiểm tra mô hình và sai số; **Quang (D12) + Minh (B2VB2K4)** kiểm tra hợp đồng dữ liệu; **Hoàng và nhóm Bản đồ** kiểm tra cấu trúc, điểm vào giao diện và API. Đây là đề xuất review, chưa gửi tin nhắn hoặc giao việc qua GitHub.

## 6. Quy trình Git đã được chủ dự án duyệt

“Push” là đưa commit từ máy lên GitHub. “Pull” là lấy thay đổi từ GitHub về máy. “Pull Request” là đề nghị nhóm review và gộp branch vào `main`.

Các lệnh dưới đây ghi lại quy trình xuất bản nhánh sau khi duyệt code và phạm vi. Trạng thái xuất bản thực tế xem ở branch/PR GitHub. Không thực hiện merge tự động.

```powershell
Set-Location 'F:\Data for Life\vietsafe-ai-integration'
git status --short
git branch --show-current
# Phải là feature/ai-forecast-integration
# Chọn đúng những file trong phạm vi AI, không add dữ liệu/checkpoint hoặc thay đổi của người khác.
git add .gitignore README.md requirements-ai.txt
git add backend/vietsafe/forecasting backend/vietsafe/web/controllers/ai_controller.py
git add backend/vietsafe/web/controllers/__init__.py backend/tests/test_ai.py backend/tests/test_ai_artifacts.py
git add frontend/index.html frontend/forecast-lab.html frontend/js/views/ai-forecast.js frontend/css/ai-forecast.css frontend/tests/ai-smoke.mjs
git add scripts/start-ai.ps1 docs/AI_INTEGRATION_PLAN.md docs/AI_FORECAST.md docs/AI_PULL_REQUEST_DRAFT.md docs/BACKEND.md docs/FRONTEND.md
git add docs/AI_TAB_POSITIONING.md
git diff --cached --stat
git diff --cached --check
git commit -m "feat(ai): integrate frozen research forecasts into VietSafe"
git fetch origin
# Nếu main thay đổi: rebase/giải quyết conflict và chạy lại test trước khi push.
git rebase origin/main
# Chạy các lệnh kiểm thử trong AI_FORECAST.md trước bước push.
git push -u origin feature/ai-forecast-integration
```

Sau đó mở GitHub → **Compare & pull request** → base `main`, compare `feature/ai-forecast-integration`. Dùng nội dung trong `AI_PULL_REQUEST_DRAFT.md`; có thể mở dạng Draft để review. Hoàng và các chủ module comment/approve, xử lý ý kiến và chạy lại các test liên quan rồi mới merge. Không push thẳng `main`, không force-push `main`.

Lưu ý: phải xem diff và commit đúng phạm vi đã duyệt trước khi rebase. Quy trình là commit → fetch/rebase nếu main đã thay đổi → test → push. Nếu có thay đổi ngoài phạm vi xuất hiện, giữ riêng chúng trước khi tiếp tục.

## 7. Phạm vi được duyệt để đưa lên branch

- Phạm vi PR đầu: ba mô hình HGB chạy lịch sử trong khu vực nghiên cứu, sau đó mới nối dữ liệu thực tế.
- Định vị tab là “Thực nghiệm dự báo”; ưu tiên nghiên cứu ngập Bellinge/FloodNet và tách giao thông SZ-Taxi theo bài toán, không chuyển kết quả nước ngoài thành dự báo trên bản đồ Hà Nội.
- Giữ cấu trúc theo PR #2 và tách hợp đồng khỏi PR #4 cho đến khi hai nhóm thống nhất.
- Cho phép tạo commit/push nhánh `feature/ai-forecast-integration` và mở PR để nhóm review.

Xem cách chạy và kiểm thử chi tiết ở [AI_FORECAST.md](AI_FORECAST.md).

## 8. Kết quả kiểm tra tại máy ngày 11/10/2026

Đã chạy lại các bộ kiểm tra ngày **12/10/2026** sau khi đổi nhãn giao diện và chuẩn hóa định dạng Python: kết quả giữ nguyên, tất cả đều đạt.

- Backend trước tích hợp: **51/51 test đạt**.
- Backend sau tích hợp, có artifact thực: **69/69 test đạt**, gồm 10 test API/hợp đồng mới và 8 test artifact.
- Giao diện hiện tại: **34/34 kiểm tra đạt**.
- Giao diện AI với mô hình thật: **21/21 kiểm tra đạt**, có kiểm tra phản hồi đến muộn khi đổi lựa chọn.
- Giao diện AI khi chưa cấu hình artifact: **5/5 kiểm tra đạt**.
- Bellinge: đối chiếu 12 mốc × 4 cảm biến × 2 chân trời với dự báo đã lưu; đạt `allclose(atol=1e-6, rtol=1e-6)`.
- SZ-Taxi: đối chiếu 12 mốc × 156 đoạn × 3 chân trời; đạt `allclose(atol=1e-5, rtol=1e-6)`.
- FloodNet: xác suất đã hiệu chỉnh khớp tập dự báo kiểm toán lưu cục bộ đến 9 chữ số thập phân trên các mốc lấy mẫu đủ điều kiện (ít nhất 10 mốc trong test).
- Đã mở trang trong trình duyệt và chạy dự báo Bellinge; các trạng thái lựa chọn, số liệu và biểu đồ hiển thị được.

Các kiểm tra này xác nhận việc chuyển mã giữ kết quả và luồng web hoạt động; chúng **không** chứng minh độ chính xác trên địa bàn mới hoặc đáp ứng tải production. Nhật ký chạy đầy đủ lưu dưới `data/` của checkout cục bộ, không đưa vào Git.
