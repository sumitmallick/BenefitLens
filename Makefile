# ─────────────────────────────────────────────────────────────────────────────
# ClaimsIQ — Makefile
# Common development, migration, and deployment commands.
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help dev down logs db-shell \
        migrate migrate-new migrate-rollback migrate-history \
        test test-backend test-frontend lint type-check \
        build push seed \
        obs obs-down obs-logs grafana prometheus

# ── Default ───────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  ClaimsIQ — available commands"
	@echo ""
	@echo "  Development"
	@echo "    make dev              Start all services (Docker Compose)"
	@echo "    make down             Stop and remove containers"
	@echo "    make logs             Follow all service logs"
	@echo "    make db-shell         Open psql shell in postgres container"
	@echo ""
	@echo "  Migrations"
	@echo "    make migrate          Apply all pending migrations"
	@echo "    make migrate-new msg='description'   Auto-generate migration"
	@echo "    make migrate-rollback                Rollback one step"
	@echo "    make migrate-history                 Show migration history"
	@echo ""
	@echo "  Quality"
	@echo "    make test             Run all tests (backend + frontend)"
	@echo "    make test-backend     pytest suite only"
	@echo "    make lint             ruff + mypy (backend) + tsc (frontend)"
	@echo ""
	@echo "  Build"
	@echo "    make build            Build Docker images"
	@echo "    make seed             Seed demo data (dev only)"
	@echo ""
	@echo "  Observability (Prometheus + Loki + Grafana)"
	@echo "    make obs              Start full stack + observability"
	@echo "    make obs-down         Stop observability stack"
	@echo "    make obs-logs         Tail observability container logs"
	@echo "    make grafana          Open Grafana  (http://localhost:3001)"
	@echo "    make prometheus       Open Prometheus (http://localhost:9090)"
	@echo ""

# ── Development ───────────────────────────────────────────────────────────────
dev:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f

db-shell:
	docker compose exec postgres psql -U claims -d claimsdb

# ── Database migrations ───────────────────────────────────────────────────────
# Run all pending migrations
migrate:
	docker compose exec backend sh -c "cd /app && alembic upgrade head"

# Auto-generate a new migration from model changes.
# Usage: make migrate-new msg="add claims_archive table"
migrate-new:
	@if [ -z "$(msg)" ]; then \
		echo "Usage: make migrate-new msg='your description'"; exit 1; \
	fi
	cd app/backend && alembic revision --autogenerate -m "$(msg)"

# Rollback one migration step
migrate-rollback:
	docker compose exec backend sh -c "cd /app && alembic downgrade -1"

# Show migration history
migrate-history:
	docker compose exec backend sh -c "cd /app && alembic history --verbose"

# Show current revision
migrate-current:
	docker compose exec backend sh -c "cd /app && alembic current"

# ── Local migration (without Docker) ─────────────────────────────────────────
migrate-local:
	cd app/backend && alembic upgrade head

migrate-new-local:
	@if [ -z "$(msg)" ]; then \
		echo "Usage: make migrate-new-local msg='your description'"; exit 1; \
	fi
	cd app/backend && alembic revision --autogenerate -m "$(msg)"

# ── Testing ───────────────────────────────────────────────────────────────────
test: test-backend test-frontend

test-backend:
	docker compose exec backend sh -c "cd /app && python -m pytest tests/ -v --tb=short --cov=claims --cov-report=term-missing"

test-frontend:
	docker compose exec frontend sh -c "npm run type-check 2>/dev/null || npx tsc --noEmit"

# ── Linting ───────────────────────────────────────────────────────────────────
lint:
	@echo "→ ruff (Python)"
	cd app/backend && python -m ruff check . --fix
	@echo "→ mypy (Python types)"
	cd app/backend && python -m mypy claims/ --ignore-missing-imports
	@echo "→ tsc (TypeScript)"
	cd app/frontend && npx tsc --noEmit

# ── Build ─────────────────────────────────────────────────────────────────────
build:
	docker compose build

# ── Observability stack ───────────────────────────────────────────────────────
# Start Prometheus + Loki + Grafana alongside the main app
obs:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build

# Stop the observability stack only
obs-down:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml down

# Tail observability container logs
obs-logs:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml logs -f prometheus loki grafana promtail

# Open Grafana in the browser
grafana:
	open http://localhost:3001

# Open Prometheus expression browser
prometheus:
	open http://localhost:9090

# ── Seed ──────────────────────────────────────────────────────────────────────
seed:
	@echo "→ Registering demo users…"
	curl -s -X POST http://localhost:8000/api/v1/auth/register \
	  -H "Content-Type: application/json" \
	  -d '{"email":"admin@claimsiq.com","password":"Admin1234!","full_name":"System Administrator","role":"ADMIN"}' | python3 -c "import sys,json;d=json.load(sys.stdin);print('admin:', d.get('user',{}).get('email','error'))"
	curl -s -X POST http://localhost:8000/api/v1/auth/register \
	  -H "Content-Type: application/json" \
	  -d '{"email":"processor@claimsiq.com","password":"Processor1!","full_name":"Sarah Mitchell","role":"CLAIM_PROCESSOR"}' | python3 -c "import sys,json;d=json.load(sys.stdin);print('processor:', d.get('user',{}).get('email','error'))"
	curl -s -X POST http://localhost:8000/api/v1/auth/register \
	  -H "Content-Type: application/json" \
	  -d '{"email":"provider@citymed.com","password":"Provider1!","full_name":"Dr. James Park","role":"PROVIDER","provider_npi":"1234567890","provider_name":"City Medical Center"}' | python3 -c "import sys,json;d=json.load(sys.stdin);print('provider:', d.get('user',{}).get('email','error'))"
	curl -s -X POST http://localhost:8000/api/v1/auth/register \
	  -H "Content-Type: application/json" \
	  -d '{"email":"patient@example.com","password":"Patient1!","full_name":"Alex Johnson","role":"PATIENT"}' | python3 -c "import sys,json;d=json.load(sys.stdin);print('patient:', d.get('user',{}).get('email','error'))"
	@echo "→ Seed complete."
