import sys
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from program.program import Program
from utils.thread import ThreadRunner
from controllers.settings import router as settings_router
from controllers.items import router as items_router
from controllers.default import router as default_router


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

app.include_router(default_router)
app.include_router(settings_router)
app.include_router(items_router)

if __name__ == "__main__":
    try:
        uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
    except KeyboardInterrupt:
        print("Exiting...")
        sys.exit(0)
