import sys
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from program.program import Program
from utils.thread import ThreadRunner
from controllers.controller import router as program_router, PlexController, ContentController, SettingsController

sys.path.append(os.getcwd())

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include the main router
app.include_router(program_router)

# Create an instance of your Program class
program = Program()

# Attach the program instance to the FastAPI app
app.state.program = program

# Include the routers for PlexController, ContentController, and SettingsController
app.include_router(PlexController(app).router)
app.include_router(ContentController(app).router)
app.include_router(SettingsController(app).router)

# Thread runner setup (if still needed)
runner = ThreadRunner(program.run, 5)
runner.start()

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8080)
