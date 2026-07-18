FROM node:20-alpine AS builder

WORKDIR /app

COPY frontend/client/package*.json ./
RUN npm ci --prefer-offline

COPY frontend/client/ .
COPY shared/catalog/ /shared/catalog/

ARG NEXT_PUBLIC_API_URL=
ARG BACKEND_INTERNAL_URL=http://api:8010
ARG API_BASE_URL=http://api:8010
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV BACKEND_INTERNAL_URL=$BACKEND_INTERNAL_URL
ENV API_BASE_URL=$API_BASE_URL

RUN npm run build

FROM node:20-alpine

RUN addgroup --system appuser && adduser --system --ingroup appuser appuser

WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 3000

CMD ["node_modules/.bin/next", "start", "-p", "3000"]
