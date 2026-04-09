# ── Backend Development Dockerfile ──
# 용��: docker-compose.yml (개발 환���)
# 특���: volume mount + hot reload (--reload)
FROM python:3.12-slim

# torch (OpenMP) 런타임 라이브러리
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# uv 바이너리만 복사 (추가 설치 불필요)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# 의존성만 먼저 복사 -> 레이어 캐시 최적화
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

RUN useradd -m appuser

COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

# App code (volume mount in dev, COPY in prod)
COPY . /app/

EXPOSE 8000

CMD ["/entrypoint.sh"]
