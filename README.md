# Iceberg

The idea behind this was to make a simple and functional rewrite of plex debrid that seemed to get a bit clustered.

Rewrite of [plex_debrid](https://github.com/itsToggle/plex_debrid) project.

Currently:
- Services include: Plex, Mdblist, Torrentio and Real Debrid

TODO:
- Implement uncached download in real-rebrid, dont know if we need this, movies seem to work ok...
- Implement updating quality of fetched items if below something
- Add frontend, ongoing... (adding api endpoints as we go along)

Check out out [Project Board](https://github.com/users/dreulavelle/projects/2) to stay informed!

COMPLETED:
- ~~Update plex libraries for changes, ongoing... ~~; (functional but we need to be more specific when to update)
- ~~Real-debrid should download only one file per stream, lets avoid collections~~
- ~~Add overseerr support, mostly done~~; still need to mark items as available?
- ~~Add support for shows, ongoing...~~ (Functionalish, needs work...)
- ~~Modify scraping logic to try scaping once a day if not found?~~
- ~~Store data with pickle~~
- ~~Improve logging...~~
- And more..

Please add features and mention issues over on our [Issue Tracker](https://github.com/dreulavelle/iceberg/issues)!

We are constantly adding features and improvements as we go along and squashing bugs as they arise.

Enjoy!

## Docker Compose

```yml
version: '3.8'

services:
  iceberg:
    image: iceberg:latest
    container_name: Iceberg
    ports:
      - "4173:4173"
    volumes:
      - ./logs:/iceberg/logs
      - ./settings.json:/iceberg/settings.json
```

> [!WARNING]  
> You must have a standard settings.json file already in place before bind mounting it!
> An empty settings.json file, or no file at all, will cause issues!

You can get a copy of the default settings [here](https://raw.githubusercontent.com/dreulavelle/iceberg/main/backend/utils/default_settings.json)

After copying over the settings file (on a fresh install) you can bind mount it like the compose above.

## Running outside of Docker

```sh
pip install -r requirements.txt
```

```sh
python3 backend/main.py
```

```sh
cd frontend

npm install
npm run dev

# OR

pnpm install
pnpm run dev
```