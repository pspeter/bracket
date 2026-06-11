# Build static files
FROM node:25-alpine AS builder

WORKDIR /app

ENV NODE_ENV=production

RUN apk add pnpm

# Install dependencies before copying the source so this layer is only
# rebuilt when the lockfile changes
COPY package.json pnpm-lock.yaml ./
RUN CI=true pnpm install

COPY . .

RUN pnpm build

# Production image, copy all the static files and run next
FROM caddy:2-alpine AS runner

WORKDIR /app

COPY --from=builder /app/dist /app/dist
COPY --from=builder /app/Caddyfile /etc/caddy/Caddyfile

EXPOSE 3000

HEALTHCHECK --interval=3s --timeout=5s --retries=10 \
    CMD ["wget", "-O", "/dev/null", "http://localhost:3000"]
