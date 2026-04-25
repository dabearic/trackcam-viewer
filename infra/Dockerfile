# ── Stage 1: build Vue frontend ───────────────────────────────────────────────
# node:20-slim (glibc/Debian) instead of alpine to sidestep the npm optional-deps
# bug (npm/cli#4828): when package-lock.json is generated on Windows, the
# linux-musl rollup binary isn't listed, so `npm ci` on alpine fails to find
# @rollup/rollup-linux-x64-musl at build time. Using `npm install` (not `npm ci`)
# also tolerates the same mismatch by resolving platform-specific optional deps
# at install time. This stage is discarded; only dist/ is copied forward.
FROM node:20-slim AS frontend-build

WORKDIR /build
COPY webapp/frontend/package*.json ./
RUN npm install --no-audit --no-fund
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
