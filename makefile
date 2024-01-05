.PHONY: help start stop restart logs exec sc ec update frontend backend

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
	@echo start     : Build and run the Iceberg container
	@echo stop      : Stop and remove the Iceberg container and image
	@echo restart   : Restart the Iceberg container (without rebuilding image)
	@echo exec      : Open a shell inside the Iceberg container
	@echo logs      : Show the logs of the Iceberg container
	@echo sc        : Show the contents of the settings.json file inside the Iceberg container
	@echo ec        : Edit the settings.json file inside the Iceberg container
	@echo update    : Update this repository from GitHub and rebuild image
	@echo frontend  : Start the frontend development server
	@echo backend   : Start the backend development server
	@echo -------------------------------------------------------------------------

start: stop
	@docker build -t iceberg:latest -f Dockerfile .
	@docker run -d --name iceberg --hostname iceberg --net host -e PUID=1000 -e PGID=1000 -v $(DATA_PATH):/iceberg/data -v /mnt:/mnt iceberg:latest
	@echo Iceberg Frontend is running on http://localhost:3000/status/
	@echo Iceberg Backend is running on http://localhost:8080/items/
	@docker logs iceberg -f

stop:
	@-docker stop iceberg --time 0
	@-docker rm iceberg --force
	@-docker rmi iceberg:latest --force

restart: 
	@-docker restart iceberg
	@echo Iceberg Frontend is running on http://localhost:3000/status/
	@echo Iceberg Backend is running on http://localhost:8080/items/
	@docker logs iceberg -f

logs:
	@docker logs iceberg -f

exec:
	@docker exec -it iceberg /bin/bash

sc:
	@docker exec -it iceberg /bin/bash -c "cat /iceberg/data/settings.json"

ec:
	@docker exec -it iceberg /bin/bash -c "vim /iceberg/data/settings.json"

update:
	@-git pull --rebase
	@make start

frontend:
	@echo Starting Frontend...
	@cd frontend && pnpm install && pnpm run build && pnpm run preview --host

backend:
	@echo Starting Backend...
	@cd backend && python main.py