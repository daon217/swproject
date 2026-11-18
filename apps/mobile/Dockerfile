FROM node:22-alpine AS build
WORKDIR /app
COPY apps/mobile/package*.json ./
RUN npm ci --no-audit --no-fund
COPY apps/mobile/ ./
ENV EXPO_PUBLIC_API_BASE_URL=/backend EXPO_PUBLIC_USE_MOCK_API=false EXPO_NO_TELEMETRY=1 CI=1
RUN npm run build:preview
FROM nginx:1.28-alpine
COPY infra/ui/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
