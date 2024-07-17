.PHONY: help install run start start-dev stop restart logs logs-dev shell build push push-dev clean format check lint sort test coverage pr-ready

# Detect operating system
ifeq ($(OS),Windows_NT)
    # For Windows
    DATA_PATH := $(shell echo %cd%)\data
else
    # For Linux
    DATA_PATH := $(PWD)/data
endif

help:
	@echo "Riven Local Development Environment"
	@echo "-------------------------------------------------------------------------"
	@echo "install   : Install the required packages"
	@echo "run       : Run the Riven backend"
	@echo "start     : Build and run the Riven container (requires Docker)"
	@echo "start-dev : Build and run the Riven container in development mode (requires Docker)"
	@echo "stop      : Stop and remove the Riven container (requires Docker)"
	@echo "logs      : Show the logs of the Riven container (requires Docker)"
	@echo "logs-dev  : Show the logs of the Riven container in development mode (requires Docker)"
	@echo "clean     : Remove all the temporary files"
	@echo "format    : Format the code using isort"
	@echo "lint      : Lint the code using ruff and isort"
	@echo "test      : Run the tests using pytest"
	@echo "coverage  : Run the tests and generate coverage report"
	@echo "pr-ready  : Run the linter and tests"
	@echo "-------------------------------------------------------------------------"
# Docker related commands

start: stop
	@docker compose -f docker-compose.yml up --build -d --force-recreate --remove-orphans
	@docker compose -f docker-compose.yml logs -f

start-dev: stop-dev
	@docker compose -f docker-compose-dev.yml up --build -d --force-recreate --remove-orphans
	@docker compose -f docker-compose-dev.yml logs -f

stop:
	@docker compose -f docker-compose.yml down

stop-dev:
	@docker compose -f docker-compose-dev.yml down

restart:
	@docker restart riven
	@docker logs -f riven

logs:
	@docker logs -f riven

logs-dev:
	@docker compose -f docker-compose-dev.yml logs -f

shell:
	@docker exec -it riven fish

build:
	@docker build -t riven .

push: build
	@docker tag riven:latest spoked/riven:latest
	@docker push spoked/riven:latest

push-dev: build
	@docker tag riven:latest spoked/riven:dev
	@docker push spoked/riven:dev

tidy:
	@docker rmi $(docker images | awk '$1 == "<none>" || $1 == "riven" {print $3}') -f


# Poetry related commands

clean:
	@find . -type f -name '*.pyc' -exec rm -f {} +
	@find . -type d -name '__pycache__' -exec rm -rf {} +
	@find . -type d -name '.pytest_cache' -exec rm -rf {} +
	@find . -type d -name '.ruff_cache' -exec rm -rf {} +
	@rm -rf data/alembic/
	@rm -rf data/*.db

install:
	@poetry install --with dev

# Run the application
run:
	@poetry run python backend/main.py

# Code quality commands
format:
	@poetry run isort backend

check:
	@poetry run pyright

lint:
	@poetry run ruff check backend
	@poetry run isort --check-only backend

sort:
	@poetry run isort backend

test:
	@poetry run pytest backend

coverage: clean
	@poetry run pytest backend --cov=backend --cov-report=xml --cov-report=term

# Run the linter and tests
pr-ready: clean lint test
