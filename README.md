# DISCONTINUED

The idea behind this was to make a simple and functional rewrite of plex debrid that seemed to get a bit clustered.

Rewrite of plex_debrid project, limited functionality:
- Services include: plex, mdblist, torrentio and realdebrid

TODO:
- ~~Real-debrid should download only one file per stream, lets avoid collections~~
- ~~Modify scraping logic to try scaping once a day if not found?~~
- ~~Add overseerr support, mostly done~~; still need to mark items as available?
- ~~Store data with pickle~~
- ~~Improve logging...~~
- ~~Update plex libraries for changes, ongoing... ~~; (functional but we need to be more specific when to update)
- Add frontend, ongoing... (adding api endpoints as we go along)
- ~~Add support for shows, ongoing...~~ (Functionalish, needs work...)
- Implement uncached download in real-rebrid, dont know if we need this, movies seem to work ok...
- Implement updating quality of fetched items if below something
