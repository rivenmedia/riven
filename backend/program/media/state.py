from enum import IntEnum
from program.scrapers import scraper as scrape
from program.debrid.realdebrid import debrid
from program.symlink import symlink
# from program.libraries.plex import plex

class States(IntEnum):
    Unknown = 0,
    Content = 1,
    Scrape = 2,
    Download = 3,
    Symlink = 4,
    Library = 5,
    LibraryPartial = 6,

class MediaItemState():

    def __eq__(self, obj: object) -> bool:
        return type(self) is type(obj)

    def set_context(self, context):
        self.context = context

    def perform_action(self):
        pass


class Unknown(MediaItemState):
    def __init__(self):
        self.name = "Unknown"

    def perform_action(self):
        pass


class Content(MediaItemState):
    def __init__(self) -> None:
        self.name = "Content"

    def perform_action(self):
        if self.context.type == "movie":
            scrape.run(self.context)
        if self.context.type == "show":
            for season in self.context.seasons:
                if season.state == Content:
                    scrape.run(season)
                else:
                    for episode in season.episodes:
                        if episode.state == Content:
                            scrape.run(episode)


class Scrape(MediaItemState):
    def __init__(self) -> None:
        self.name = "Scrape"

    def perform_action(self):
        if self.context.type == "movie":
            debrid.run(self.context)
        if self.context.type == "show":
            for season in self.context.seasons:
                if season.state == Scrape:
                    debrid.run(season)
                else:
                    for episode in season.episodes:
                        if episode.state == Scrape:
                            debrid.run(episode)


class Download(MediaItemState):
    def __init__(self) -> None:
        self.name = "Download"

    def perform_action(self):
        if self.context.type == "movie":
            symlink.run(self.context)
        if self.context.type == "show":
            for season in self.context.seasons:
                for episode in season.episodes:
                    if episode.state == Download:
                        symlink.run(episode)


class Symlink(MediaItemState):
    def __init__(self) -> None:
        self.name = "Symlink"

    def perform_action(self):
        pass
        # plex.update(self.context)


class Library(MediaItemState):
    def __init__(self) -> None:
        self.name = "Library"

    def perform_action(self):
        pass


class LibraryPartial(MediaItemState):
    def __init__(self) -> None:
        self.name = "Library Partial"

    def perform_action(self):
        for season in self.context.seasons:
            if season.state == Content:
                scrape.run(season)
            if season.state == Scrape:
                debrid.run(season)
            elif season.state == LibraryPartial:
                for episode in season.episodes:
                    if episode.state == Content:
                        scrape.run(episode)
                    if episode.state == Scrape:
                        debrid.run(episode)
                    if episode.state == Download:
                        symlink.run(episode)

states = [state for state in States]
