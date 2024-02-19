from starlette.testclient import TestClient
from fastapi import FastAPI
from program.media.state import States
import controllers.items as items
from program.media.container import MediaItemContainer
from unittest.mock import MagicMock

app = FastAPI()
app.include_router(items.router)
app.program = MagicMock()
app.program.media_items = MediaItemContainer()

client = TestClient(app)


def test_get_states():
    response = client.get("/items/states")
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "states": [state.value for state in States],
    }


def test_get_items():
    response = client.get("/items/")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
    assert response.json()["success"] is True
    assert isinstance(response.json()["items"], list)
