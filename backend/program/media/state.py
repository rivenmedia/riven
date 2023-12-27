from enum import Enum
from program.scrapers import scraper as scrape
from program.debrid.realdebrid import debrid
from program.symlink import symlink


class MediaItemState:
    def __eq__(self, other) -> bool:
        if type(other) == type:
            return type(self) == other
        return type(self) == type(other)

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
        if self.context.type in ["movie", "season", "episode"]:
            scrape.run(self.context)
        if self.context.type == "show":
            for season in self.context.seasons:
                season.state.perform_action()


class Scrape(MediaItemState):
    def __init__(self) -> None:
        self.name = "Scrape"

    def perform_action(self):
        if self.context.type in ["movie", "season", "episode"]:
            debrid.run(self.context)
        if self.context.type == "show":
            for season in self.context.seasons:
                season.state.perform_action()
        if self.context.type == "season":
            self.context.state.perform_action()


class Download(MediaItemState):
    def __init__(self) -> None:
        self.name = "Download"

    def perform_action(self):
        if self.context.type in ["movie", "episode"]:
            symlink.run(self.context)
        if self.context.type == "show":
            for season in self.context.seasons:
                for episode in season.episodes:
                    episode.state.perform_action()
        if self.context.type == "season":
            for episode in self.context.episodes:
                episode.state.perform_action()


class Symlink(MediaItemState):
    def __init__(self) -> None:
        self.name = "Symlink"

    def perform_action(self):
        pass


class Library(MediaItemState):
    def __init__(self) -> None:
        self.name = "Library"

    def perform_action(self):
        pass


class LibraryPartial(MediaItemState):
    def __init__(self) -> None:
        self.name = "Library Partial"

    def perform_action(self):
        if self.context.type == "show":
            for season in self.context.seasons:
                season.state.perform_action()
        if self.context.type == "season":
            for episode in self.context.episodes:
                episode.state.perform_action()


# This for api to get states, not for program
class MediaItemStates(Enum):
    Unknown = Unknown()
    Content = Content()
    Scrape = Scrape()
    Download = Download()
    Symlink = Symlink()
    Library = Library()
    LibraryPartial = LibraryPartial()
