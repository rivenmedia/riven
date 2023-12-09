"""Ui helpers"""
from types import SimpleNamespace
from flask.json import JSONEncoder
from program.media import MediaItem, MediaItemState


class CustomJSONEncoder(JSONEncoder):
    """Custom json encoder for flask to use"""

    def default(self, o):
        if isinstance(o, MediaItem):
            attributes = {k: v for k, v in o.__dict__.items() if k not in ["_lock", "parent"]}
            return attributes
        if isinstance(o, MediaItemState):
            return o.name
        if isinstance(o, SimpleNamespace):
            return o.__dict__
        return super().default(o)
