.PHONY: start restart stop logs exec help start-nocache restart-nocache

help:
	@echo Iceberg Local Development Environment
	@echo -------------------------------------------------------
	@echo start           : Build and run the Iceberg container
	@echo start-nocache   : Build and run the Iceberg container without using cache
	@echo stop            : Stop and remove the Iceberg container
	@echo restart         : Restart the Iceberg container
	@echo restart-nocache : Restart the Iceberg container without using cache
	@echo exec            : Open a shell inside the Iceberg container
	@echo logs            : Show the logs of the Iceberg container
	@echo -------------------------------------------------------

start: 
	docker build -t iceberg:latest -f Dockerfile .
	docker run -d --name iceberg -p 3000:3000 -p 8080:8080 -e PUID=1000 -e PGID=1000 -v ${PWD}/data:/iceberg/data iceberg:latest
	@echo Iceberg Frontend is running on http://localhost:3000/
	@echo Iceberg Backend is running on http://localhost:8080/items/
	@docker logs iceberg -f

start-nocache: 
	docker build --no-cache -t iceberg:latest -f Dockerfile .
	docker run -d --name iceberg -p 3000:3000 -p 8080:8080 -e PUID=1000 -e PGID=1000 -v ${PWD}/data:/iceberg/data iceberg:latest
	@echo Iceberg Frontend is running on http://localhost:3000/
	@echo Iceberg Backend is running on http://localhost:8080/items/
	@docker logs iceberg -f

stop:
	-docker stop iceberg
	-docker rm iceberg
	-docker rmi iceberg:latest

restart: stop start

restart-nocache: stop start-nocache

exec:
	@docker exec -it iceberg /bin/sh

logs:
	@docker logs iceberg -f
