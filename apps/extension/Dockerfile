FROM node:22-alpine AS build
WORKDIR /app
COPY apps/extension/package*.json ./
RUN npm ci --no-audit --no-fund
COPY apps/extension/ ./
ENV VITE_API_BASE_URL=/backend VITE_USE_MOCK_API=false
RUN npm run build:preview && cp preview-dist/preview.html preview-dist/index.html
FROM nginx:1.28-alpine
COPY infra/ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/preview-dist /usr/share/nginx/html
EXPOSE 8080
