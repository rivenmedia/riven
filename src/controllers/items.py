from copy import copy
from fastapi import APIRouter, Request
from program.media import MediaItemState
from utils.settings import settings_manager
from pydantic import BaseModel
from typing import Optional

router = APIRouter(
    prefix="/items",
    tags=["items"],
    responses={404: {"description": "Not found"}},
)

@router.get("/")
async def get_all_items(request: Request, ):
    """items endpoint"""
    items = request.app.program.media_items.items

    new_items = copy(items)
    for item in new_items:
        item.set("current_state", item.state.name)

    return items


@router.get("/{state}")
async def get_item(request: Request, state: str):
    """items endpoint"""
    items = [
        item for item in request.app.program.media_items if item.state.name == state
    ]

    new_items = copy(items)
    for item in new_items:
        item.set("current_state", item.state.name)

    return items

@router.delete("/{item}")
async def remove_item(request: Request, item: Optional[str] = None):
    """Remove item from program"""
    request.app.program.media_items.remove(item)