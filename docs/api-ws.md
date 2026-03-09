# WebSocket API

Base path: **`/api/v1/ws`**

WebSocket connections are authenticated via **`resolve_ws_api_key`** (separate from the standard API key dependency used for REST).

---

## WebSocket `/api/v1/ws/{topic}`

Connect to a topic channel. Server publishes messages to all clients subscribed to that topic.

**Path:** `topic` — any non-empty string (e.g. `logging`).

**Protocol:** After connection, client can send JSON text frames; server may send JSON or text frames for events. Invalid JSON from client is logged and ignored.

**Behavior:** On connect, client is subscribed to `topic`. On disconnect, client is removed. Logging handler can publish to `logging` topic (see stream router’s SSE for similar log events).

**Example:** Connect to `wss://host/api/v1/ws/logging` with API key (query or header per auth setup) to receive log events.
