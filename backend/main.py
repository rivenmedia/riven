import contextlib
import sys
import os
import threading
import time
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from program import Program
from controllers.settings import router as settings_router
from controllers.items import router as items_router
from controllers.default import router as default_router


class Server(uvicorn.Server):
    def install_signal_handlers(self):
        pass

    @contextlib.contextmanager
    def run_in_thread(self):
        thread = threading.Thread(target=self.run, name="Iceberg")
        thread.start()
        try:
            while not self.started:
                time.sleep(1e-3)
            yield
        finally:
            self.should_exit = True

app = FastAPI()
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

config = uvicorn.Config(app, host="0.0.0.0", port=8080)
server = Server(config=config)

with server.run_in_thread():
    app.program.start()
    try:
        app.program.run()
    except KeyboardInterrupt:
        app.program.stop()
        sys.exit(0)
