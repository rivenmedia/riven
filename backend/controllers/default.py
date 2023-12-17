from fastapi import APIRouter, Request
from utils.settings import settings_manager
import requests
from program.debrid.realdebrid import get_user


router = APIRouter(
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def root(request: Request):
    return {
        "success": True,
        "message": "Iceburg is running!",
    }


@router.get("/user")
async def get_rd_user():
    return get_user()
