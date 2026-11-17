SHELL := /bin/bash
COMPOSE ?= docker compose
WEB := npm --workspace apps/web run
UI := npm --workspace packages/ui run

POSTGRES_PASSWORD ?= $(shell sed -n 's/^POSTGRES_PASSWORD=//p' .env 2>/dev/null)
POSTGRES_PORT ?= 55432
DATABASE_URL ?= postgresql+psycopg://mona:$(POSTGRES_PASSWORD)@localhost:$(POSTGRES_PORT)/mona_test
export DATABASE_URL

.PHONY: up down logs db check web-check py-check ci-py api-client e2e

up: node_modules apps/web/node_modules data
	$(COMPOSE) up -d --build

# compose mounts volumes over these paths; created first by docker they would be root-owned on the host
node_modules:
	npm ci --no-audit --no-fund

apps/web/node_modules:
	mkdir -p apps/web/node_modules

data:
	mkdir -p data

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

db:
	$(COMPOSE) up -d --wait postgres

check: db web-check py-check

web-check:
	$(UI) lint
	$(UI) typecheck
	$(UI) test
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
	cd apps/api && uv run --frozen python ../../scripts/no-practice-names.py
	cd apps/api && uv run --frozen ruff check .
	cd apps/api && uv run --frozen ruff format --check .
	cd apps/api && uv run --frozen pytest

ci-py:
	@name=mona-ci-py-$$$$; \
	docker run -d --rm --name $$name -e POSTGRES_USER=mona -e POSTGRES_PASSWORD=mona \
		-e POSTGRES_DB=mona_test -p 127.0.0.1::5432 postgres:17 >/dev/null || exit 1; \
	trap "docker rm -f $$name >/dev/null" EXIT; \
	for _ in $$(seq 60); do docker exec $$name pg_isready -q -h 127.0.0.1 -U mona && break; sleep 1; done; \
	port=$$(docker port $$name 5432/tcp | head -1 | sed 's/.*://'); \
	CI=true GITHUB_ACTIONS=true MONA_SEED_OVERLAY=/nonexistent $(MAKE) --no-print-directory py-check \
		DATABASE_URL=postgresql+psycopg://mona:mona@localhost:$$port/mona_test

e2e:
	$(WEB) e2e -- --workers=2
