"""
    Main module for the application.
"""
import uvicorn

from program.program import Program
from utils.thread import ThreadRunner
from controllers.settings import router as settings_router
from controllers.items import router as items_router
from program.media import MediaItemState
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

program = Program()
app.program = program


@app.get("/")
def read_root():
    return {"success": True, "message": "Iceburg is running!"}


@app.get("/states")
def get_states():
    """states endpoint"""
    return [state.name for state in MediaItemState]


runner = ThreadRunner(program.run, 5)

app.include_router(settings_router)
app.include_router(items_router)

try:
    if __name__ == "__main__":
        runner.start()
        uvicorn.run("main:app", host="localhost", port=8080, reload=True)
except KeyboardInterrupt:
    runner.stop()