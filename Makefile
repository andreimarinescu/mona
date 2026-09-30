SHELL := /bin/bash
COMPOSE ?= docker compose
WEB := npm --workspace apps/web run

POSTGRES_PASSWORD ?= $(shell sed -n 's/^POSTGRES_PASSWORD=//p' .env 2>/dev/null)
POSTGRES_PORT ?= 55432
DATABASE_URL ?= postgresql+psycopg://mona:$(POSTGRES_PASSWORD)@localhost:$(POSTGRES_PORT)/mona_test
export DATABASE_URL

.PHONY: up down logs db check web-check py-check api-client e2e

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

db:
	$(COMPOSE) up -d --wait postgres

check: db web-check py-check

web-check:
	$(WEB) lint
	$(WEB) typecheck
	$(WEB) test
	node scripts/i18n-check.mjs
	npm run test:scripts
	$(MAKE) api-client
	$(WEB) build

api-client:
	cd apps/web && npx openapi-typescript ../api/openapi.json -o ../../node_modules/.cache/schema.gen.ts >/dev/null \
		&& diff -u src/api/schema.gen.ts ../../node_modules/.cache/schema.gen.ts \
		|| { echo "apps/web/src/api/schema.gen.ts is stale: run npm run gen:api -w apps/web"; exit 1; }

py-check:
	cd apps/api && uv run --frozen ruff check .
	cd apps/api && uv run --frozen ruff format --check .
	cd apps/api && uv run --frozen pytest

e2e:
	$(WEB) e2e
