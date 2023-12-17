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
    return {
        "success": True,
        "items": [item.to_dict() for item in request.app.program.media_items.items],
    }


@router.get("/{state}")
async def get_item(request: Request, state: str):
    state = MediaItemState[state]
    items = request.app.program.media_items.get_items_with_state(state).items

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
