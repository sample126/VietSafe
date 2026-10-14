# Chạy cùng một phiên bản trên local và Render

Ứng dụng chính giữ cấu trúc của nhóm: `backend/vietsafe/` xử lý API,
`frontend/` chứa giao diện, `scripts/` chứa lệnh chạy. Module dự báo thêm
logic trong `backend/vietsafe/forecasting/`, controller trong
`backend/vietsafe/web/controllers/` và HTML/JS/CSS trong `frontend/`.

## Vì sao giao diện online có thể vẫn cũ?

Code đẩy lên nhánh riêng chưa có trên `main` cho tới khi được hợp nhất.
Ngoài ra, bản `server.py` cũ ở thư mục gốc phục vụ `public/`, trong khi
backend mới phục vụ `frontend/`. Render dùng lệnh chạy cũ có thể tiếp tục
hiển thị giao diện cũ dù repo đã có thư mục mới.

Hiện `python server.py` chuyển tiếp sang `vietsafe.__main__.main()` của
backend mới, giữ tham số `--host`, `--port` và biến môi trường `HOST`, `PORT`.
Vì vậy nút `START-VIETSAFE.cmd` cũ cũng mở đúng ứng dụng mới. Không phát triển
tính năng mới trong `public/` hoặc các hàm lịch sử ở `server.py`.

## Render

Với Python web service hiện có, kiểm tra trong Render Dashboard:

- Repository: `sample126/VietSafe`; Branch: `main`.
- Root Directory: để trống (thư mục gốc repo).
- Start Command: `cd backend && python -m vietsafe --host 0.0.0.0 --port $PORT`.
- Health Check Path: `/api/health`.
- Auto-Deploy: bật theo commit của nhánh `main` nếu muốn tự cập nhật.

`render.yaml` có lệnh chạy mới, nhưng sửa tệp này không bảo đảm một service
được tạo thủ công sẽ tự đổi các thiết lập trên Dashboard. Sau khi merge,
đối chiếu commit đang Live trong Events/Deploys; nếu chưa cập nhật, chọn
Manual Deploy → Deploy latest commit. Không cần xóa dữ liệu để cập nhật code.

Dấu hiệu đã phục vụ bản mới:

- HTML trang chủ nạp `/js/main.js` và CSS trong `/css/`.
- `/forecast-lab.html` và `/flood-simulator.html` trả HTTP 200.
- `/api/ai/catalog` và `/api/flood-simulation/catalog` trả JSON.

Phần mô phỏng ngập chạy bằng thư viện chuẩn Python. AI nghiên cứu chỉ chạy
suy luận khi máy chủ có thư viện trong `requirements-ai.txt`, artifact đúng
manifest và biến `VIETSAFE_AI_RESEARCH_ROOT` trỏ tới thư mục dữ liệu tại
chính máy chủ. Đường dẫn trên máy cá nhân không dùng được trên Render.
Repo không chứa checkpoint hoặc dữ liệu nghiên cứu. Khi chưa cấu hình,
giao diện AI hiển thị trạng thái chưa sẵn sàng, không tạo dự báo giả.
Xem [AI_FORECAST.md](AI_FORECAST.md) trước khi triển khai runtime AI.

## Local có AI và mô phỏng

Chạy từ thư mục gốc repo bằng môi trường đã cài thư viện AI:

```powershell
.\scripts\start-ai.ps1 -ResearchRoot 'F:\Data for Life' -Python 'C:\Users\DELL\anaconda3\python.exe' -Port 8790
```

Mở trang chủ `http://127.0.0.1:8790/`, vào **Dự báo** để chọn AI nghiên cứu
hoặc mô phỏng. Cả hai trang dùng cùng backend; mô phỏng không cần checkpoint.
Đổi đường dẫn Python và ResearchRoot theo máy đang sử dụng.
