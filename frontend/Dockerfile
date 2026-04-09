# ── Frontend Multi-Stage Dockerfile ──
# 개발: docker-compose.yml에서 target=dev 지정, npm run dev
# 배포: docker-compose.prod.yml에서 전체 빌드, nginx 서빙

# ── Stage 1: 의존성 설치 (공용) ──
FROM node:22-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

# ── Stage 2: 개발 서버 ──
FROM deps AS dev
WORKDIR /app
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host", "--port", "3000"]

# ── Stage 3: 프로덕션 빌드 ──
FROM deps AS build
WORKDIR /app
COPY . .
ARG VITE_API_TARGET
ARG VITE_GOOGLE_CLIENT_ID
ARG VITE_INTERNAL_API_KEY
ENV VITE_API_TARGET=${VITE_API_TARGET}
ENV VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID}
ENV VITE_INTERNAL_API_KEY=${VITE_INTERNAL_API_KEY}
RUN npm run build

# ── Stage 4: 프로덕션 서빙 (nginx) ──
FROM nginx:alpine AS prod

RUN addgroup -g 1001 -S appgroup && adduser -S appuser -u 1001 -G appgroup

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
