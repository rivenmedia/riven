from fastapi import APIRouter


class PlexController:
    """Plex controller blueprint"""
    
    def __init__(self, app):
        self.plex = app.program.plex
        self.router = APIRouter()
        self.register_routes()

    def register_routes(self):
        # Add your Plex specific routes here
        pass

class ContentController:
    """Content controller blueprint"""

    def __init__(self, app):
        self.instances = app.program.content_services
        self.router = APIRouter()
        self.register_routes()

    def register_routes(self):
        # Add your Content specific routes here
        pass