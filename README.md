# Iceberg

Plex torrent streaming through Real Debrid and 3rd party services like Overseerr, Mdblist, etc.

Rewrite of [plex_debrid](https://github.com/itsToggle/plex_debrid) project.

Services currently supported:
- [x] Real Debrid
- [x] Plex
- [x] Overseerr
- [x] Mdblist
- [x] Plex Watchlist RSS
- [x] Torrentio
- [x] Orionoid
- [x] Jackett
- [ ] and more to come!

Check out out [Project Board](https://github.com/users/dreulavelle/projects/2) to stay informed!

Please add feature requests and issues over on our [Issue Tracker](https://github.com/dreulavelle/iceberg/issues) or join our [Discord](https://discord.gg/wDgVdH8vNM) to chat with us!

We are constantly adding features and improvements as we go along and squashing bugs as they arise.

---

## Table of Contents
- [Docker Compose](#docker-compose)
  - [What is ORIGIN ?](#what-is-origin-)
- [Running outside of Docker](#running-outside-of-docker)
- [Symlinking settings](#symlinking-settings)
- [Development](#development)
  - [Development without `make`](#development-without-make)

---

## Docker Compose

Create a `docker-compose.yml` file with the following contents:

```yml
version: '3.8'

services:
  iceberg:
    image: spoked/iceberg:latest
    container_name: Iceberg
    restart: unless-stopped
    environment:
      PUID: "1000"
      PGID: "1000"
      ORIGIN: "http://localhost:3000" # read below for more info
    ports:
      - "3000:3000"
    volumes:
      - ./data:/iceberg/data
```

Then run `docker compose up -d` to start the container in the background. You can then access the web interface at `http://localhost:3000` or whatever port and origin you set in the `docker-compose.yml` file.

#### What is ORIGIN ?
`ORIGIN` is the URL of the frontend on which you will access it from anywhere. If you are hosting Iceberg on a vps with IP address `134.32.24.44` then you will need to set the `ORIGIN` to `http://134.32.24.44:3000` (no trailing slash). Similarly, if using a domain name, you will need to set the `ORIGIN` to `http://iceberg.mydomain.com:3000` (no trailing slash). If you change the port in the `docker-compose.yml` file, you will need to change it in the `ORIGIN` as well.

## Running outside of Docker

To run outside of docker you will need to have node (v18.13+) and python (3.10+) installed. Then clone the repository

```sh
git clone https://github.com/dreulavelle/iceberg.git
```

and open two terminals in the root of the project and run the following commands in each.

#### First terminal:

```sh
cd frontend
npm install
npm run build
ORIGIN=http://localhost:3000 node build
```
Read above for more info on `ORIGIN`.

#### Second terminal:

```sh
pip install -r requirements.txt
python backend/main.py
```

---

## Symlinking settings
"host_mount" should point to your rclone mount that has your torrents on your host, if you are using native webdav set webdav-url to "https://dav.real-debrid.com/torrents"

"container_mount" should point to the location of the mount in plex container

### Example:
Rclone is mounted to /iceberg/vfs on your host machine -> settings should have: "host_mount": "/iceberg/vfs"

Plex container volume configuration for rclone mount is "/iceberg/vfs:/media/vfs" -> settings should have: "container_mount": "/media/vfs"

Plex libraries you want to add to sections: movies -> /media/library/movies, shows -> /media/library/shows

---

## Development
You can view the readme in `make` to get started!

```sh
make
```

To get started you can simply do this. This will stop any previous Iceberg containers and remove previous image.
As well as rebuild the image using cached layers. If your a developer, then any files changed in the code will not get cached, 
and thus rebuilt in the image.

```sh
make start
```

You can also restart the container with `make restart`, or view the logs with `make logs`. 

### Development without `make`
If you don't want to use `make` and docker, you can use the following commands to run development environment.

```sh
pip install -r requirements.txt
python backend/main.py
```

```sh
cd frontend
npm install
npm run dev
```

---

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

We use Black for backend and Prettier for frontend. Please make sure to run the formatters before submitting a pull request. Also use CRLF line endings unless it is a shell script or something that requires LF line endings.

---

## License
This project is licensed under the GNU GPLv3 License - see the [LICENSE](LICENSE) file for details
