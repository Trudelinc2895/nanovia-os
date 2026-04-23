# Nanovia OS — Makefile
# Usage: make <target>
# Run from project root on the VPS.

PROJECT_NAME ?= $(or $(COMPOSE_PROJECT),nanovia-os)
COMPOSE_FILES ?= -f infra/docker-compose.prod.yml
ENV_FILE ?= .env
COMPOSE = docker compose -p $(PROJECT_NAME) $(COMPOSE_FILES) --env-file $(ENV_FILE)
APP_DIR ?= $(or $(DEPLOY_PATH),/opt/nanovia-os)

.PHONY: help up down build logs restart migrate admin shell-api \
        backup update status clean pull test

# ── Default ────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Nanovia OS — Commands"
	@echo ""
	@echo "  make up          Start all containers"
	@echo "  make down        Stop all containers"
	@echo "  make build       Rebuild images"
	@echo "  make restart     Rebuild + restart"
	@echo "  make logs        Live logs (all services)"
	@echo "  make logs-api    Live logs (API only)"
	@echo "  make migrate     Run Alembic migrations"
	@echo "  make admin       Create first admin user"
	@echo "  make shell-api   Open bash in api container"
	@echo "  make status      Show container status"
	@echo "  make update      git pull + rebuild + migrate"
	@echo "  make backup      Run database backup"
	@echo "  make test        Run backend tests"
	@echo "  make clean       Remove stopped containers + old images"
	@echo ""
	@echo "  Overrides:"
	@echo "    ENV_FILE=.env.staging"
	@echo "    COMPOSE_FILES='-f infra/docker-compose.prod.yml -f infra/docker-compose.staging.yml'"
	@echo "    PROJECT_NAME=nanovia-staging"
	@echo ""

# ── Lifecycle ─────────────────────────────────────────────────────────────────
up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build --no-cache

restart: build
	$(COMPOSE) up -d

# ── Logs ──────────────────────────────────────────────────────────────────────
logs:
	$(COMPOSE) logs -f --tail=100

logs-api:
	$(COMPOSE) logs -f --tail=100 api

logs-caddy:
	$(COMPOSE) logs -f --tail=100 caddy

logs-db:
	$(COMPOSE) logs -f --tail=100 postgres

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	@echo "Running Alembic migrations..."
	$(COMPOSE) up -d postgres redis
	$(COMPOSE) run --rm api alembic upgrade head
	@echo "Done."

# ── Admin bootstrap ───────────────────────────────────────────────────────────
admin:
	$(COMPOSE) exec api python scripts/create_admin.py

shell-api:
	$(COMPOSE) exec api bash

shell-db:
	$(COMPOSE) exec postgres psql -U kt_user -d kt_monetization

# ── Monitoring ────────────────────────────────────────────────────────────────
status:
	@echo ""
	@docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
	@echo ""

# ── Deploy / Update ───────────────────────────────────────────────────────────
pull:
	git pull origin main

update: pull
	$(COMPOSE) build --no-cache api web
	$(COMPOSE) up -d postgres redis
	$(COMPOSE) run --rm api alembic upgrade head
	$(COMPOSE) up -d
	@echo "✅ Update complete"

# ── Backup ────────────────────────────────────────────────────────────────────
backup:
	bash infra/scripts/backup.sh

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	$(COMPOSE) exec -T api python -m pytest tests/ -q --tb=short

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	docker container prune -f
	docker image prune -f
