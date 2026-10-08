FROM node:20-alpine AS base

# Install dependencies
FROM base AS deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

# Build
FROM base AS builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ .
RUN npm run build

# Production
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 --ingroup nodejs frontend

COPY --from=builder /app/dist ./dist
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json

USER frontend
EXPOSE 5173

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0"]
