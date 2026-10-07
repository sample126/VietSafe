FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Chỉ sao chép phần cần chạy (xem .dockerignore). Backend không có thư viện ngoài để cài.
COPY backend ./backend
COPY frontend ./frontend

# Thư mục dữ liệu (SQLite). Gắn volume vào /app/data nếu muốn giữ dữ liệu giữa các lần chạy.
RUN mkdir -p /app/data \
    && useradd --create-home --shell /usr/sbin/nologin vietsafe \
    && chown -R vietsafe:vietsafe /app/data
USER vietsafe

EXPOSE 8765
WORKDIR /app/backend
CMD ["python", "-m", "vietsafe", "--host", "localhost", "--port", "8765"]
