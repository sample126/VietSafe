> Archived original document. File paths, credentials policy and startup instructions may be obsolete. See README.md and docs/ARCHITECTURE.md.

# Đẩy đầy đủ dự án VietSafe lên GitHub

Bản bàn giao này theo đúng yêu cầu: Git được phép theo dõi `.env`, `.env.local`, các tệp `.env.*`, cơ sở dữ liệu `data/vietsafe.sqlite3` và toàn bộ tệp dự án cần thiết. Hai thông tin xác thực NASA Earthdata và TomTom có sẵn trong `.env`. Không có mật khẩu quản trị thực tế trong bản gốc, nên `.env.local` có giá trị `VIETSAFE_ADMIN_PASSWORD=` trống.

## Cách 1: Cập nhật repository VietSafe đã có trên máy

1. Sao chép toàn bộ nội dung thư mục `VietSafe` trong bản ZIP này vào thư mục Git VietSafe hiện tại (giữ lại thư mục ẩn `.git` của repository hiện tại).
2. Mở Terminal tại thư mục Git VietSafe và chạy:

```bash
git status
git add -A
git add -f .env .env.local
git status --short
git commit -m "Commit complete VietSafe project including configuration"
git push -u origin HEAD
```

Lưu ý: `git add` và `git commit` không phải là `git push`; chỉ sau khi đẩy thành công thì các thay đổi mới xuất hiện trên GitHub. Không chèn token vào dòng lệnh vì có thể bị ghi vào lịch sử shell.

## Cách 2: Tạo repository mới (nếu chưa có Git)

Tạo một repository trống trên GitHub. Trong thư mục `VietSafe` chạy:

```bash
git init
git branch -M main
git add -A
git add -f .env .env.local
git commit -m "Initial VietSafe project"
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

Thay `USERNAME/REPOSITORY` bằng đường dẫn thực; nếu repo đã có Git thì không chạy cách 2.

## Kiểm tra

```bash
git ls-files .env .env.local .env.example .env.local.example data/vietsafe.sqlite3
git status --short
git remote -v
```

Lệnh đầu tiên phải hiển thị các tệp cấu hình và SQLite khi đã thêm vào chỉ mục Git. Để kiểm tra Git bỏ qua những gì: `git status --ignored --short`.

## Giới hạn và rủi ro

- `.venv/`, `__pycache__/`, file log và tệp hệ điều hành tạo tự động vẫn bị bỏ qua, vì đó không phải mã nguồn hay cấu hình dự án.
- Nếu repository **Public**, token, mật khẩu điền trong `.env.local` và dữ liệu SQLite sẽ công khai. Người khác có thể đọc và dùng chúng. Xóa file khỏi GitHub về sau không chắc xóa khỏi lịch sử commit hoặc các bản sao. Nên chuyển sang repository **Private** hoặc dùng GitHub Secrets.
- GitHub có thể phát hiện và chặn push có chứa token. Nếu xảy ra, cách an toàn là không đưa token vào Git, chuyển sang Secrets và thay token đã lộ.
- `.dockerignore` không đưa secret vào Docker image. Nếu triển khai Render, vẫn cần cấu hình riêng Environment Variables; không thể giả định Render tự tải `.env` từ repository.
- Chưa có quyền truy cập repository GitHub của bạn nên bản ZIP này **chưa được push trực tiếp**.
