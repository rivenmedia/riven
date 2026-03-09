# Webhooks API

Base path: **`/api/v1/webhook`**

Incoming webhooks for external services (e.g. Overseerr).

---

## POST `/api/v1/webhook/overseerr`

Overseerr webhook. Used to add new requests (movies/TV) to Riven when requested in Overseerr.

**Body:** JSON payload from Overseerr. Expected shape includes:
- `notification_type`, `event`, `subject`, `message`, `image`
- `media`: `media_type` (`movie` | `tv`), `tmdbId`, `tvdbId`, `imdbId`, `status`
- `request`: optional — `request_id`, `requestedBy_email`, etc.
- For test: `subject` = `"Test Notification"` → returns success without creating an item.

**Response:**
```json
{
  "success": true,
  "message": null
}
```
Or on failure: `{ "success": false, "message": "..." }`.

**Behavior:** On valid request event, creates a `MediaItem` (movie by `tmdb_id`, tv by `tvdb_id`), sets `requested_by: "overseerr"` and optional `overseerr_id`, and enqueues it via the event manager. Test notifications are acknowledged without enqueueing.

**Errors:** Returns 200 with `success: false` and message if Overseerr not initialized or item creation fails (no 4xx/5xx).
