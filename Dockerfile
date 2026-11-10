FROM node:24-alpine AS frontend

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
ARG VITE_API_URL=/
RUN VITE_API_URL="$VITE_API_URL" npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/incidents.db

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend

RUN python -m pip install --no-cache-dir . \
    && mkdir -p /data

COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
