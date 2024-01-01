from enum import Enum


class MediaItemState:
    def __eq__(self, other) -> bool:
        if type(other) == type:
            return type(self) == other
        return type(self) == type(other)

    def set_context(self, context):
        self.context = context

    def perform_action(self, _):
        pass


class Unknown(MediaItemState):
    def perform_action(self, _):
        pass


class Content(MediaItemState):
    def perform_action(self, modules):
        scraper = next(module for module in modules if module.key == "scrape")
        if self.context.type in ["movie", "season", "episode"]:
            scraper.run(self.context)
        if self.context.type == "show":
            for season in self.context.seasons:
                if season.aired_at:
                    season.state.perform_action()
                else:
                    for episode in season.episodes:
                        episode.state.perform_action()


class Scrape(MediaItemState):
    def perform_action(self, modules):
        debrid = next(module for module in modules if module.key == "realdebrid")
        if self.context.type in ["movie", "season", "episode"]:
            debrid.run(self.context)
        if self.context.type == "show":
            for season in self.context.seasons:
                if season.aired_at:
                    season.state.perform_action()
                else:
                    for episode in season.episodes:
                        episode.state.perform_action()
        if self.context.type == "season":
            self.context.state.perform_action()


class Download(MediaItemState):
    def perform_action(self, modules):
        symlink = next(module for module in modules if module.key == "symlink")
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
    def perform_action(self, _):
        pass


class Library(MediaItemState):
    def perform_action(self, _):
        pass


class LibraryPartial(MediaItemState):
    def perform_action(self, modules):
        if self.context.type == "show":
            for season in self.context.seasons:
                season.state.perform_action(modules)
        if self.context.type == "season":
            for episode in self.context.episodes:
                episode.state.perform_action(modules)


# This for api to get states, not for program
class MediaItemStates(Enum):
    Unknown = Unknown.__name__
    Content = Content.__name__
    Scrape = Scrape.__name__
    Download = Download.__name__
    Symlink = Symlink.__name__
    Library = Library.__name__
    LibraryPartial = LibraryPartial.__name__
