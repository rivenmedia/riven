import sys
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from program.program import Program
from utils.thread import ThreadRunner
from controllers.controller import PlexController, ContentController
from controllers.settings import settings_router
from controllers.items import items_router


sys.path.append(os.getcwd())

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
app.include_router(settings_router)
app.include_router(items_router)
app.include_router(PlexController(app).router)
app.include_router(ContentController(app).router)

runner = ThreadRunner(program.run, 5)

if __name__ == "__main__":

    try:
        runner.start()
        uvicorn.run(app, host="localhost", port=8080)
    except KeyboardInterrupt:
        print("Shutting down...")
        runner.stop()
        sys.exit(0)