.PHONY: help start reset stop restart rebuild logs exec sc ec update

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
	@echo reset     : Build and run the Iceberg container without caching image
	@echo stop      : Stop and remove the Iceberg container and image
	@echo restart   : Restart the Iceberg container (without rebuilding image)
	@echo rebuild   : Rebuild the Iceberg container (with rebuilding image)
	@echo exec      : Open a shell inside the Iceberg container
	@echo logs      : Show the logs of the Iceberg container
	@echo sc        : Show the contents of the settings.json file inside the Iceberg container
	@echo ec        : Edit the settings.json file inside the Iceberg container
	@echo update    : Update this repository from GitHub and rebuild image
	@echo -------------------------------------------------------------------------

start: 
	@docker build -t iceberg:latest -f Dockerfile .
	@docker run -d --name iceberg --hostname iceberg -p 3000:3000 -p 8080:8080 -e PUID=1000 -e PGID=1000 -v $(DATA_PATH):/iceberg/data iceberg:latest
	@echo Iceberg Frontend is running on http://localhost:3000/status/
	@echo Iceberg Backend is running on http://localhost:8080/items/
	@docker logs iceberg -f

reset: 
	@docker build --no-cache -t iceberg:latest -f Dockerfile .
	@docker run -d --name iceberg --hostname iceberg -p 3000:3000 -p 8080:8080 -e PUID=1000 -e PGID=1000 -v $(DATA_PATH):/iceberg/data iceberg:latest
	@echo Iceberg Frontend is running on http://localhost:3000/status/
	@echo Iceberg Backend is running on http://localhost:8080/items/
	@docker logs iceberg -f

stop:
	@-docker stop iceberg
	@-docker rm iceberg
	@-docker rmi iceberg:latest

restart: 
	@-docker restart iceberg
	@echo Iceberg Frontend is running on http://localhost:3000/status/
	@echo Iceberg Backend is running on http://localhost:8080/items/
	@docker logs iceberg -f

rebuild: stop reset

logs:
	@docker logs iceberg -f

exec:
	@docker exec -it iceberg /bin/bash

sc:
	@docker exec -it iceberg /bin/bash -c "cat /iceberg/data/settings.json"

ec:
	@docker exec -it iceberg /bin/bash -c "vim /iceberg/data/settings.json"

update:
	@git pull
	@rebuild