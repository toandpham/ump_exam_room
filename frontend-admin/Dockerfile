FROM node:22-alpine

WORKDIR /app

# Install deps first for better layer caching.
# npm ci + package-lock.json: khoá cứng phiên bản dependency (xem frontend-exam).
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Bản PRODUCTION build — không dùng dev server ở vận hành thật (HMR WebSocket
# không qua được lớp webhost/proxy của nhà trường → trang tự reload liên tục,
# sự cố 27-07). Đổi code admin thì phải: docker compose build frontend-admin.
RUN npm run build

EXPOSE 5173

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD wget -q --spider http://127.0.0.1:5173/admin/ || exit 1

CMD ["npm", "run", "preview"]
