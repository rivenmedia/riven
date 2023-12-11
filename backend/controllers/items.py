from fastapi import APIRouter, HTTPException, Request
from program.media import MediaItemState
from utils.logger import logger


router = APIRouter(
    tags=["items"],
    responses={404: {"description": "Not found"}},
)

@router.get("/items")
async def get_items(request: Request):
    """items endpoint"""
    logger.info("Updating states...")
    state = request.app.MediaItemState if state else None
    media_items = request.app.program.media_items
    if state:
        items = [item for item in media_items if item.state.name == state]
    else:
        items = media_items.items
    for item in items:
        item.set("current_state", item.state.name)
        logger.debug(f'Set \'{item.title}\' to {item.current_state}')
    logger.info("Done!")
    return [item.to_dict() for item in items]

@router.get("/states")
async def get_states(request: Request):
    return [state.name for state in request.app.MediaItemState]

@router.post("/items/remove")
async def remove_item(request: Request, item: str = None):
    program = request.app.state.program
    if item is not None:
        program.media_items.remove(item)
    else:
        raise HTTPException(status_code=400, detail="Item not provided")