from fastapi import APIRouter, Request

router = APIRouter(
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def root(request: Request):
    return {
        "success": True,
        "message": "Iceburg is running!",
    }
