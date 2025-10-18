.PHONY: help install run start stop restart logs shell build push push-dev push-branch tidy clean hard_reset format check sort test coverage pr-ready update

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

# Prevent inheriting an external virtualenv (e.g., old Poetry VIRTUAL_ENV)
unexport VIRTUAL_ENV

help:
	@echo "make install     - Install dependencies"
	@echo "make run         - Run the application"
	@echo "make start       - Start the application in a Docker container"
	@echo "make stop        - Stop the application container"
	@echo "make restart     - Restart the application container"
	@echo "make logs        - View the application logs"
	@echo "make shell       - Open a shell in the application container"
	@echo "make build       - Build the application image"
	@echo "make push        - Build and push the application image to Docker Hub"
	@echo "make push-dev    - Build and push the dev image to Docker Hub"
	@echo "make push-branch - Build and push the branch image to Docker Hub"
	@echo "make tidy        - Remove unused Docker images"
	@echo "make clean       - Clean up temporary files"
	@echo "make hard_reset  - Hard reset the database"
	@echo "make format      - Format the code"
	@echo "make check       - Check the code for errors"
	@echo "make sort        - Sort the imports"
	@echo "make test        - Run the tests"
	@echo "make coverage    - Run the tests with coverage"
	@echo "make pr-ready    - Run the linter and tests"
	@echo "make update      - Update dependencies"


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


# Project environment & quality commands (uv-based)

clean:
	@find . -type f -name '*.pyc' -exec rm -f {} +
	@find . -type d -name '__pycache__' -exec rm -rf {} +
	@find . -type d -name '.pytest_cache' -exec rm -rf {} +
	@find . -type d -name '.ruff_cache' -exec rm -rf {} +

hard_reset: clean
	@uv run python src/main.py --hard_reset_db

install:
	@uv sync --group dev

update:
	@uv lock --upgrade
	@uv sync --group dev

diff:
	@git diff HEAD~1 HEAD

# Run the application
run:
	@uv run python src/main.py

# Code quality commands
format:
	@uv run isort src

check:
	@uv run pyright

lint:
	@uv run ruff check src
	@uv run isort --check-only src

sort:
	@uv run isort src

test:
	@uv run pytest src

coverage: clean
	@uv run pytest src --cov=src --cov-report=xml --cov-report=term

# Run the linter and tests
pr-ready: clean lint test
