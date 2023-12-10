from copy import copy
from fastapi import APIRouter, HTTPException, Request
from program.media import MediaItemState


items_router = APIRouter(
    tags=["items"],
    responses={404: {"description": "Not found"}},
)

@items_router.get("/items")
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

@items_router.get("/states")
async def get_states(request: Request):
    return [state.name for state in MediaItemState]

@items_router.post("/items/remove")
async def remove_item(request: Request, item: str = None):
    program = request.app.state.program
    if item is not None:
        program.media_items.remove(item)
    else:
        raise HTTPException(status_code=400, detail="Item not provided")