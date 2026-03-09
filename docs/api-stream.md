# Stream API

Base path: **`/api/v1/stream`**

Stream media files by item ID (direct or HLS). Also SSE event types for logging.

---

## GET `/api/v1/stream/event_types`

List available SSE event type names (for subscribing).

**Response:** `{ "event_types": ["logging", ...] }`

---

## GET `/api/v1/stream/{event_type}`

SSE stream for the given event type (e.g. `logging`). Streams events as they occur.

**Response:** `Content-Type: text/event-stream`. No API key on this route by default — check router deps.

---

## GET `/api/v1/stream/file/{item_id}`

Stream the media file for a media item directly from the debrid provider. Supports Range requests for seeking.

**Path:** `item_id` — MediaItem ID (must have an associated media file / filesystem entry with a URL).

**Response:** Streaming response with appropriate `Content-Type`, `Content-Length`/`Content-Range`, `Accept-Ranges`. Filename in `Content-Disposition`.

**Errors:** 404 if item not found, no media file, or no stream URL; 502 if upstream connection fails.

---

## GET `/api/v1/stream/hls/{item_id}/index.m3u8`

Get an HLS playlist (VOD) for the item. Segments are generated on the fly via FFmpeg.

**Query (optional):** `profile`, `pix_fmt`, `level`, `resolution` — passed to segment URLs for transcoding.

**Response:** `Content-Type: application/vnd.apple.mpegurl`. Playlist with segment references like `segment/0.ts`, `segment/1.ts`, ...

---

## GET `/api/v1/stream/hls/{item_id}/segment/{seq}.ts`

Get a single HLS segment (MPEG-TS). Segment duration is 12 seconds; `seq` is the segment index.

**Query (optional):** `profile`, `pix_fmt`, `level`, `resolution` — for FFmpeg (e.g. `resolution=720p` or `1280x720`).

**Response:** `Content-Type: video/mp2t`. Streamed segment.

**Note:** Requires FFmpeg; segments are transcoded from the item’s source URL (libx264, AAC audio).
