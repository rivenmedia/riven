from fastapi import APIRouter, HTTPException, Request
from program.media.state import States

router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)


@router.get("/states")
async def get_states():
    return {
        "success": True,
        "states": [state for state in States],
    }


@router.get("/")
async def get_items(request: Request):
    return {
        "success": True,
        "items": [item.to_dict() for item in request.app.program.media_items],
    }


@router.get("/extended/{item_id}")
async def get_extended_item_info(request: Request, item_id: str):
    item = request.app.program.media_items.get_item_by_id(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return {
        "success": True,
        "item": item.to_extended_dict(),
    }


@router.delete("/remove/{item}")
async def remove_item(request: Request, item: str):
    request.app.program.media_items.remove(item)
    request.app.program.content.overseerr.delete_request(item)
    return {
        "success": True,
        "message": f"Removed {item}",
    }


@router.get("/imdb/{imdb_id}")
async def get_imdb_info(request: Request, imdb_id: str):
    item = request.app.program.media_items.get_item_by_imdb_id(imdb_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"success": True, "item": item.to_extended_dict()}
