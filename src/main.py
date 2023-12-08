"""
    Main module for the application.
"""
import sys
import os
import time
from flask import Flask
from program.program import Program
from utils.thread import ThreadRunner
from utils.ui_helpers import CustomJSONEncoder
from controllers.controller import ProgramController
from flask_cors import CORS

sys.path.append(os.getcwd())

if __name__ == "__main__":
    app = Flask(__name__)
    CORS(app)
    program = Program()
    app.register_blueprint(ProgramController(program))
    app.json_encoder = CustomJSONEncoder
    app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True
    runner = ThreadRunner(program.run, 5)
    runner.start()
    app.run(host="localhost", port=8080)  # TODO Disable flask logging

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        runner.stop()
