FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt && useradd --uid 10001 --create-home app
COPY backend/ /app/backend/
COPY ops/service.py /app/ops/service.py
COPY --from=frontend /build/dist /app/frontend/dist
RUN mkdir -p /data/media /app/backend/staticfiles && chown -R app:app /data /app
USER app
EXPOSE 8000
CMD ["python", "/app/ops/service.py"]
