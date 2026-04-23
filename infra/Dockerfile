# ── Stage 1: build Vue frontend ───────────────────────────────────────────────
FROM node:20-alpine AS frontend-build

WORKDIR /build
COPY webapp/frontend/package*.json ./
RUN npm ci
COPY webapp/frontend/ ./
RUN npm run build          # outputs to /build/dist


# ── Stage 2: FastAPI runtime ──────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY webapp/backend/requirements_cloud.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy cloud backend as main.py
COPY webapp/backend/main_cloud.py ./main.py

# Copy built Vue app — served as static files by FastAPI
COPY --from=frontend-build /build/dist ./static

ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
