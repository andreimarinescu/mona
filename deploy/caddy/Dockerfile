FROM node:24 AS web
WORKDIR /repo
COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/
COPY packages/ui/package.json packages/ui/
RUN npm ci --no-audit --no-fund
COPY apps/web apps/web
COPY packages/ui packages/ui
COPY design design
RUN npm run build -w apps/web

FROM caddy:2-alpine
COPY deploy/caddy/Caddyfile /etc/caddy/Caddyfile
COPY --from=web /repo/apps/web/dist /srv
