from copy import copy
from fastapi import APIRouter
from utils.settings import settings_manager
from pydantic import BaseModel


class SetSettings(BaseModel):
    key: str
    value: str


router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    responses={404: {"description": "Not found"}},
)


@router.get("/load")
async def load_settings():
    settings_manager.load()
    return {
        "success": True,
        "message": "Settings loaded!",
    }


@router.post("/save")
async def save_settings():
    settings_manager.save()
    return {
        "success": True,
        "message": "Settings saved!",
    }


@router.get('/get/all')
async def get_all_settings():
    return {
        "success": True,
        "data": copy(settings_manager.get_all()),
    }


@router.get("/get/{key}")
async def get_settings(key: str):
    return {
        "success": True,
        "data": settings_manager.get(key),
    }


@router.post("/set")
async def set_settings(settings: SetSettings):
    settings_manager.set(
        settings.key,
        settings.value,
    )
    return {
        "success": True,
        "message": "Settings saved!",
    }
