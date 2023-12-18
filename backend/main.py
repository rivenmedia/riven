import sys
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from program import Program
from controllers.settings import router as settings_router
from controllers.items import router as items_router
from controllers.default import router as default_router


sys.path.append(os.getcwd())


def lifespan(app: FastAPI):
    app.program.start()
    yield
    app.program.stop()


app = FastAPI(lifespan=lifespan)
app.program = Program()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(default_router)
app.include_router(settings_router)
app.include_router(items_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)
