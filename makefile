.PHONY: help install run start start-dev stop restart logs logs-dev shell build push push-dev clean format check lint sort test coverage pr-ready

# Detect operating system
ifeq ($(OS),Windows_NT)
    # For Windows
    DATA_PATH := $(shell echo %cd%)\data
else
    # For Linux
    DATA_PATH := $(PWD)/data
endif

BRANCH_NAME := $(shell git rev-parse --abbrev-ref HEAD | sed 's/[^a-zA-Z0-9]/-/g' | tr '[:upper:]' '[:lower:]')
COMMIT_HASH := $(shell git rev-parse --short HEAD)

help:
	@echo "Riven Local Development Environment"
	@echo "-------------------------------------------------------------------------"
	@echo "install   : Install the required packages"
	@echo "run       : Run the Riven src"
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

# Ensure the Buildx builder is set up
setup-builder:
	@if ! docker buildx ls | grep -q "mybuilder"; then \
		echo "Creating Buildx builder..."; \
		docker buildx create --use --name mybuilder --driver docker-container; \
	else \
		echo "Using existing Buildx builder..."; \
	fi

# Build multi-architecture image (local only, no push)
build: setup-builder
	@docker buildx build --platform linux/amd64,linux/arm64 -t riven --load .

# Build and push multi-architecture release image
push: setup-builder
	@echo "Building and pushing release image to Docker Hub..."
	@docker buildx build --platform linux/amd64,linux/arm64 -t spoked/riven:latest --push .
	@echo "Image 'spoked/riven:latest' pushed to Docker Hub"

# Build and push multi-architecture dev image
push-dev: setup-builder
	@echo "Building and pushing dev image to Docker Hub..."
	@docker buildx build --platform linux/amd64,linux/arm64 -t spoked/riven:dev --push .
	@echo "Image 'spoked/riven:dev' pushed to Docker Hub"

push-branch: setup-builder
	@echo "Building and pushing branch '${BRANCH_NAME}' image to Docker Hub..."
	@docker buildx build --platform linux/amd64,linux/arm64 -t spoked/riven:${BRANCH_NAME} --push .
	@echo "Image 'spoked/riven:${BRANCH_NAME}' pushed to Docker Hub"

tidy:
	@docker rmi $(docker images | awk '$1 == "<none>" || $1 == "riven" {print $3}') -f


# Poetry related commands

clean:
	@find . -type f -name '*.pyc' -exec rm -f {} +
	@find . -type d -name '__pycache__' -exec rm -rf {} +
	@find . -type d -name '.pytest_cache' -exec rm -rf {} +
	@find . -type d -name '.ruff_cache' -exec rm -rf {} +

hard_reset: clean
	@poetry run python src/main.py --hard_reset_db

install:
	@poetry install --with dev

update:
	@poetry cache clear PyPI --all
	@poetry update

# Run the application
run:
	@poetry run python src/main.py

# Code quality commands
format:
	@poetry run isort src

check:
	@poetry run pyright

lint:
	@poetry run ruff check src
	@poetry run isort --check-only src

sort:
	@poetry run isort src

test:
	@poetry run pytest src

coverage: clean
	@poetry run pytest src --cov=src --cov-report=xml --cov-report=term

# Run the linter and tests
pr-ready: clean lint test
