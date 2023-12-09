"Api controller module"
from copy import copy
from fastapi import APIRouter, Request, HTTPException
from program.media import MediaItemState
from utils.settings import settings_manager

router = APIRouter()

@router.get("/items")
async def get_items(request: Request, state: str = None):
    program = request.app.state.program
    if state:
        items = [item for item in program.media_items if item.state.name == state]
    else:
        items = program.media_items.items

    new_items = copy(items)
    for item in new_items:
        item.set("current_state", item.state.name)
    return items

@router.get("/states")
async def get_states(request: Request):
    return [state.name for state in MediaItemState]

@router.post("/items/remove")
async def remove_item(request: Request, item: str = None):
    program = request.app.state.program
    if item is not None:
        program.media_items.remove(item)
    else:
        raise HTTPException(status_code=400, detail="Item not provided")

class PlexController:
    """Plex controller blueprint"""
    
    def __init__(self, app):
        self.plex = app.state.program.plex
        self.router = APIRouter()
        self.register_routes()

    def register_routes(self):
        # Add your Plex specific routes here
        pass

class ContentController:
    """Content controller blueprint"""

    def __init__(self, app):
        self.instances = app.state.program.content_services
        self.router = APIRouter()
        self.register_routes()

    def register_routes(self):
        # Add your Content specific routes here
        pass

class SettingsController:
    """Settings controller blueprint"""

    def __init__(self, app):
        self.router = APIRouter()
        self.register_routes()

    def register_routes(self):
        self.router.add_api_route("/load", self._load, methods=["GET"])
        self.router.add_api_route("/save", self._save, methods=["POST"])
        self.router.add_api_route("/get", self._get, methods=["GET"])
        self.router.add_api_route("/set", self._set, methods=["POST"])

    async def _load(self, request: Request):
        settings_manager.load()
        return {"message": "Settings loaded"}

    async def _save(self, request: Request):
        settings_manager.save()
        return {"message": "Settings saved"}

    async def _get(self, request: Request):
        key = request.query_params.get("key")
        return settings_manager.get(key)

    async def _set(self, request: Request):
        key = request.query_params.get("key")
        value = request.query_params.get("value")
        settings_manager.set(key, value)
        return {"message": "Setting updated"}
