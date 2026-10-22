# web (apps/web): the owner's panel, Next.js standalone on port 3000.
# Build context: apps/web only (design assets are generated and committed; `npm run gen:check` proves it).
# Runs as uid 10001 on a read-only root filesystem (compose adds tmpfs for /tmp and the Next cache).
FROM node:22.22.0-trixie-slim AS build
WORKDIR /src
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# public/demo holds the mock-mode media fixtures (§22 demo studio); development fixtures never ship.
RUN npm run typecheck && npm run build && rm -rf public/demo

FROM node:22.22.0-trixie-slim
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin web
COPY --from=build --chown=10001:10001 /src/.next/standalone ./
COPY --from=build --chown=10001:10001 /src/.next/static ./.next/static
COPY --from=build --chown=10001:10001 /src/public ./public
USER 10001
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/healthz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["node", "server.js"]
