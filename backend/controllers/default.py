from fastapi import APIRouter, Request
from utils.settings import settings_manager
import requests


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
    api_key = settings_manager.get("realdebrid")["api_key"]
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(
        "https://api.real-debrid.com/rest/1.0/user", headers=headers
    )
    return response.json()

    # fetch user from https://api.real-debrid.com/rest/1.0/user
