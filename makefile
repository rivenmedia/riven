.PHONY: help install run build push push-dev push-branch tidy clean hard_reset format check sort test coverage pr-ready update

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
	@echo "make install     - Install dependencies"
	@echo "make run         - Run the application"
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


# Ensure the Buildx builder is set up and support multi-arch builds
setup-builder:
	@echo "Setting up Buildx builder..."
	@if ! docker buildx ls | grep -q "mybuilder"; then \
		echo "Creating Buildx builder..."; \
		docker buildx create --use --name mybuilder --driver docker-container; \
	else \
		echo "Using existing Buildx builder..."; \
	fi

build: setup-builder
	@echo "Building application image..."
	@docker buildx build --platform linux/amd64,linux/arm64 -t riven --load .

push-dev: setup-builder
	@echo "Building and pushing dev image to Docker Hub..."
	@docker buildx build --platform linux/amd64,linux/arm64 -t spoked/riven:dev --push .
	@echo "Image 'spoked/riven:dev' pushed to Docker Hub"

push-branch: setup-builder
	@echo "Building and pushing branch '${BRANCH_NAME}' image to Docker Hub..."
	@docker buildx build --platform linux/amd64,linux/arm64 -t spoked/riven:${BRANCH_NAME} --push .
	@echo "Image 'spoked/riven:${BRANCH_NAME}' pushed to Docker Hub"

tidy:
	@echo "Removing unused Docker images..."
	@docker rmi $(docker images | awk '$1 == "<none>" || $1 == "riven" {print $3}') -f


# Project environment & quality commands (uv-based)

clean:
	@echo "Cleaning up temporary files..."
	@find . -type f -name '*.pyc' -exec rm -f {} +
	@find . -type d -name '__pycache__' -exec rm -rf {} +
	@find . -type d -name '.pytest_cache' -exec rm -rf {} +
	@find . -type d -name '.ruff_cache' -exec rm -rf {} +
	@echo "Temporary files cleaned up"

hard_reset: clean
	@echo "Hard resetting the database..."
	@uv run python src/main.py --hard_reset_db
	@echo "Database hard reset complete"

install:
	@echo "Installing dependencies..."
	@uv sync --group dev
	@echo "Dependencies installed"

update:
	@echo "Updating dependencies..."
	@uv lock --upgrade
	@uv sync --group dev
	@echo "Dependencies updated"

diff:
	@echo "Diffing against previous commit..."
	@git diff HEAD~1 HEAD

# Run the application
run:
	@uv run python src/main.py

# Code quality commands
format:
	@uv run black .

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
