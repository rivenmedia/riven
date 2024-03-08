.PHONY: help install run start stop logs clean lint test pr-ready

# Detect operating system
ifeq ($(OS),Windows_NT)
    # For Windows
    DATA_PATH := $(shell echo %cd%)\data
else
    # For Linux
    DATA_PATH := $(PWD)/data
endif

help:
	@echo Iceberg Local Development Environment
	@echo -------------------------------------------------------------------------
	@echo install   : Install the required packages
	@echo run       : Run the Iceberg backend
	@echo start     : Build and run the Iceberg container
	@echo stop      : Stop and remove the Iceberg container and image
	@echo logs      : Show the logs of the Iceberg container
	@echo clean     : Remove all the cache files
	@echo lint      : Run the linter and type checker
	@echo test      : Run the tests
	@echo pr-ready  : Run the linter and tests
	@echo -------------------------------------------------------------------------

install:
	@poetry install

run:
	@poetry run python backend/main.py

start: stop
	@docker build -t iceberg:latest -f Dockerfile .
	@docker run -d --name iceberg --hostname iceberg --net host -e PUID=1000 -e PGID=1000 -v $(DATA_PATH):/iceberg/data -v /mnt:/mnt iceberg:latest
	@docker logs iceberg -f

stop:
	@-docker stop iceberg --time 0
	@-docker rm iceberg --force
	@-docker rmi iceberg:latest --force

logs:
	@docker logs iceberg -f

clean:
	@find . -type f -name '*.pyc' -exec rm -f {} +
	@find . -type d -name '__pycache__' -exec rm -rf {} +
	@find . -type d -name '.pytest_cache' -exec rm -rf {} +
	@find . -type d -name '.ruff_cache' -exec rm -rf {} +

format:
	@poetry run black backend

lint: format
	@poetry run ruff check backend
	@poetry run pyright backend

test:
	@cd backend/tests && poetry run pytest

pr-ready: clean lint test
