from fastapi import APIRouter, HTTPException, Request
from program.media.state import states


router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)


@router.get("/states")
async def get_states(request: Request):
    return {
        "success": True,
        "states": [state.name for state in states],
    }


@router.get("/")
async def get_items(request: Request):
    return {
        "success": True,
        "items": [item.to_dict() for item in request.app.program.media_items.items],
    }


@router.get("/extended/{item_id}")
async def get_extended_item_info(request: Request, item_id: str):
    item = request.app.program.media_items.get_item_by_id(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return {
        "success": True,
        "item": item.to_extended_dict(),  # Assuming this method exists
    }


@router.delete("/remove/{item}")
async def remove_item(request: Request, item: str):
    request.app.program.media_items.remove(item)
    return {
        "success": True,
        "message": f"Removed {item}",
    }
