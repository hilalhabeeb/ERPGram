# ERPGRAM — developer tasks (macOS / Linux).
# Everything runs in Docker: `db` (Postgres 16) + `web` (Django + Tailwind CLI).
# Windows users: see tasks.ps1 for the same commands.

DC  := docker compose
RUN := docker compose run --rm web
EXEC := docker compose exec web

.DEFAULT_GOAL := help
.PHONY: help install up down migrate seed seed-manpower dev test lint fmt ci messages compilemessages tailwind shell logs

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'

install: ## Build the images and install dependencies
	$(DC) build

up: ## Start Postgres in the background
	$(DC) up -d db

down: ## Stop and remove containers
	$(DC) down

migrate: ## Apply database migrations
	$(RUN) uv run python manage.py migrate

seed-manpower: ## Load the demo GCC domestic-worker agency
	$(RUN) uv run python manage.py seed_manpower

seed: ## Load two demo tenants with owners and members
	$(RUN) uv run python manage.py seed

dev: ## Run the app: Django + Tailwind watch (http://localhost:8010)
	$(DC) up -d db
	$(DC) run --rm --service-ports web sh -c "\
		tailwindcss -i static/src/input.css -o static/css/app.css --watch & \
		uv run python manage.py runserver 0.0.0.0:8000"

test: ## Run the test suite
	$(RUN) uv run pytest

lint: ## Lint with ruff
	$(RUN) uv run ruff check .

fmt: ## Format with ruff
	$(RUN) uv run ruff format .

ci: ## Run the full CI gate locally (same checks as GitHub Actions)
	$(RUN) sh -c "uv run ruff check . \
		&& uv run ruff format --check . \
		&& uv run python manage.py makemigrations --check --dry-run \
		&& uv run python manage.py check \
		&& uv run pytest -q"

messages: ## Extract translatable strings for en + ar
	$(RUN) uv run python manage.py makemessages -l ar -l en --ignore=.venv

compilemessages: ## Compile .po files to .mo
	$(RUN) uv run python manage.py compilemessages

tailwind: ## Rebuild CSS once
	$(RUN) tailwindcss -i static/src/input.css -o static/css/app.css --minify

shell: ## Open a Django shell
	$(RUN) uv run python manage.py shell

logs: ## Tail container logs
	$(DC) logs -f
