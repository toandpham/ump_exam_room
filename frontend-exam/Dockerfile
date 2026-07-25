FROM node:22-alpine

WORKDIR /app

# Install deps first for better layer caching.
# npm ci + package-lock.json: KHOÁ CỨNG phiên bản dependency. Trước đây chỉ COPY
# package.json + npm install → mỗi lần layer này bị dựng lại là giải lại range "^"
# từ registry (React/vite/plugin-legacy có thể nhảy phiên bản chưa ai test, thẳng
# vào bundle thí sinh). Lock đã có sẵn trong repo — dùng nó.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Build a PRODUCTION bundle. The candidate app runs inside Safe Exam Browser
# 2.4.1 on Windows 7, whose engine is Gecko/Firefox 41 (2015) — it cannot run
# the Vite dev server's native-ESM output. The build (plugin-legacy + postcss
# down-levelling) emits an ES5 `nomodule` bundle + flat CSS the old engine reads.
RUN npm run build

EXPOSE 5173

# Serve the built dist/ over HTTP for Caddy to proxy at /thisinh/.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD wget -q --spider http://127.0.0.1:5173/thisinh/ || exit 1

CMD ["npm", "run", "preview"]
