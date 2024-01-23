import json
from models import AppModel

print(AppModel().model_dump_json(indent=2))