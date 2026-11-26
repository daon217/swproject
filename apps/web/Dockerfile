# 빌드 단계에서만 개발 패키지(TypeScript·Tailwind 등)를 쓰고, 실행 이미지에는 Next.js standalone 결과만 담는다.
# (예전 단일 단계 이미지는 node_modules 전체가 들어가 약 2GB였다.)
FROM node:22-bookworm-slim AS build
ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-bookworm-slim
ENV NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
