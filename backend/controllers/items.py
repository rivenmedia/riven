from fastapi import APIRouter, HTTPException, Request
from program.media import MediaItemState
from utils.logger import logger


router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)

@router.get("/states")
async def get_states(request: Request):
    return {
        "success": True,
        "states": [state.name for state in MediaItemState],
    }


@router.get("/")
async def get_items(request: Request):
    items = request.app.program.media_items.items
    for item in items:
        item.set("current_state", item.state.name)

    return {
        "success": True,
        "items": [item.to_dict() for item in items],
    }


@router.get("/{state}")
async def get_item(request: Request, state: str):
    items = [item for item in request.app.program.media_items if item.state.name == state]
    for item in items:
        item.set("current_state", item.state.name)

    return {
        "success": True,
        "items": [item.to_dict() for item in items],
    }


@router.delete("/remove/{item}")
async def remove_item(request: Request, item: str):
    request.app.program.media_items.remove(item)
    return {
        "success": True,
        "message": f"Removed {item}",
    }
