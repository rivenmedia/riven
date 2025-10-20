import asyncio

from fastapi import APIRouter, Request

from program.program import Program
from ..models.shared import MessageResponse

router = APIRouter(
    prefix="/program",
    tags=["program"],
    responses={404: {"description": "Not found"}},
)


@router.post("/start", operation_id="start_program")
async def start_program(request: Request) -> MessageResponse:
    """Start the program."""
    if not request.app.program.is_alive():
        request.app.program = Program()
        request.app.program.start()
    return {"message": "Program started"}


@router.post("/stop", operation_id="stop_program")
async def stop_program(request: Request) -> MessageResponse:
    """Stop the program."""
    request.app.program.stop()  # no-op if not running
    return {"message": "Program stopped"}


@router.post("/restart", operation_id="restart_program")
async def restart_program(request: Request) -> MessageResponse:
    """Restart the program."""
    if request.app.program.is_alive():
        request.app.program.stop()
        await asyncio.sleep(0.5)
        request.app.program = Program()
        request.app.program.start()
    return {"message": "Program restarted"}
