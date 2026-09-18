FROM python:3.11-slim

WORKDIR /app

# Copy application files
COPY . /app

# Expose port
EXPOSE 8765

# Run VietSafe server bound to all interfaces for container deployment
CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8765"]
