# from typing import Generator
# from program.media.item import MediaItem

from .listrr import Listrr
from .mdblist import Mdblist
from .overseerr import Overseerr
from .plex_watchlist import PlexWatchlist
from .trakt import TraktContent

__all__ = ["Listrr", "Mdblist", "Overseerr", "PlexWatchlist", "TraktContent"]

# class Requester:
#     def __init__(self):
#         self.key = "content"
#         self.initialized = False
#         self.services = {
#             Listrr: Listrr(),
#             Mdblist: Mdblist(),
#             Overseerr: Overseerr(),
#             PlexWatchlist: PlexWatchlist(),
#             TraktContent: TraktContent()
#         }
#         self.initialized = self.validate()
#         if not self.initialized:
#             return

#     def validate(self):
#         return any(service.initialized for service in self.services.values())

#     def run(self, item: MediaItem) -> Generator[MediaItem, None, None]:
#         """Index newly requested items."""
#         yield item
