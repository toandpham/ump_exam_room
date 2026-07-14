FROM node:22-alpine

WORKDIR /app

# Install deps first for better layer caching. node_modules is kept in an
# anonymous volume by compose so the host bind-mount does not shadow it.
COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173

HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=6 \
    CMD wget -q --spider http://127.0.0.1:5173/admin/ || exit 1

CMD ["npm", "run", "dev"]
