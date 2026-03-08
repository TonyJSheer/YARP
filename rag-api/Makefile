.PHONY: setup dev test lint typecheck migrate

setup:
	uv sync

dev:
	docker compose up

test:
	uv run pytest

lint:
	uv run ruff check . && uv run ruff format --check .

typecheck:
	uv run mypy app

migrate:
	PYTHONPATH=. uv run alembic upgrade head
