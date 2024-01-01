from copy import copy
from fastapi import APIRouter
from utils.settings import settings_manager
from pydantic import BaseModel
from typing import Any


class SetSettings(BaseModel):
    key: str
    value: Any


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


@router.get("/get/all")
async def get_all_settings():
    return {
        "success": True,
        "data": copy(settings_manager.get_all()),
    }


@router.get("/get/{keys}")
async def get_settings(keys: str):
    keys = keys.split(",")
    data = {key: settings_manager.get(key) for key in keys}
    return {
        "success": True,
        "data": data,
    }


@router.post("/set")
async def set_settings(**settings: SetSettings):
    for key, value in settings.items():
        settings_manager.set(key, value)
    return {
        "success": True,
        "message": "Settings saved!",
    }
