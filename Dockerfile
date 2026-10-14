FROM python:3.11-slim
WORKDIR /app
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY data/.gitkeep ./data/.gitkeep
COPY requirements.txt requirements-optional.txt ./
# Opt in to NASA HDF5 support: docker build --build-arg ENABLE_NASA=1 ...
ARG ENABLE_NASA=0
RUN if [ "$ENABLE_NASA" = "1" ]; then pip install --no-cache-dir -r requirements-optional.txt; fi
EXPOSE 8765
CMD ["python", "backend/run.py", "--host", "0.0.0.0", "--port", "8765"]
