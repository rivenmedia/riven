import sys
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from program.media import MediaItemState
from program.program import Program
from utils.thread import ThreadRunner
from controllers.settings import router as settings_router
from controllers.items import router as items_router


sys.path.append(os.getcwd())
program = Program()
runner = ThreadRunner(program.run, 5)

def lifespan(app: FastAPI):
    runner.start()
    yield
    runner.stop()

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.program = program
app.MediaItemState = MediaItemState
app.include_router(settings_router)
app.include_router(items_router)

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8080)