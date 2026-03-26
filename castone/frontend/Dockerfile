FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

ARG VITE_API_TARGET
ARG VITE_INTERNAL_API_KEY
ENV VITE_API_TARGET=${VITE_API_TARGET}
ENV VITE_INTERNAL_API_KEY=${VITE_INTERNAL_API_KEY}

RUN npm run build

# --- Production stage ---
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
