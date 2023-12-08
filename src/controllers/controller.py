""" Program controller """
from copy import copy
from flask import Blueprint, request
from program.media import MediaItemState
from utils.settings import settings_manager


class ProgramController(Blueprint):
    """Program controller blueprint"""

    def __init__(self, program):
        super().__init__("program", __name__)
        self.program = program
        self.register_blueprint(self.PlexController(self.program.plex))
        self.register_blueprint(self.ContentController(self.program.content_services))
        # self.register_blueprint(self.ScrapingController(self.program.scraping_instances))
        # self.register_blueprint(self.DebridController(self.program.debrid_instances))
        self.add_url_rule("/items", methods=["GET"], view_func=self.get_items)
        self.add_url_rule("/states", methods=["GET"], view_func=self.get_states)
        self.add_url_rule(
            "/items/remove",
            methods=["POST"],
            view_func=self.remove_item,
            defaults={"item": None},
        )

    def get_items(self):
        """items endpoint"""
        state = request.args.get("state")

        if state:
            items = [
                item for item in self.program.media_items if item.state.name == state
            ]
        else:
            items = self.program.media_items.items

        new_items = copy(items)
        for item in new_items:
            item.set("current_state", item.state.name)
        return items

    def get_states(self):
        """states endpoint"""
        return [state.name for state in MediaItemState]

    def remove_item(self, item):
        """Remove item from program"""
        self.program.media_items.remove(item)

    class PlexController(Blueprint):
        """Plex controller blueprint"""

        def __init__(self, plex):
            super().__init__("library", __name__)
            self.plex = plex

    class ContentController(Blueprint):
        """Content controller blueprint"""

        def __init__(self, instances: list):
            super().__init__("content", __name__)
            self.instances = instances

    class SettingsController(Blueprint):
        """Settings controller blueprint"""

        def __init__(self):
            super().__init__("settings", __name__)
            self.add_url_rule("/settings/load", methods=["GET"], view_func=self._load)
            self.add_url_rule("/settings/save", methods=["POST"], view_func=self._save)
            self.add_url_rule("/settings/get", methods=["GET"], view_func=self._get)
            self.add_url_rule("/settings/set", methods=["POST"], view_func=self._set)

        def _load(self):
            settings_manager.load()

        def _save(self):
            settings_manager.save()

        def _get(self):
            key = request.args.get("key")
            return settings_manager.get(key)

        def _set(self):
            key = request.args.get("key")
            value = request.args.get("value")
            settings_manager.set(key, value)
