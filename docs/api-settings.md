# Settings API

Base path: **`/api/v1/settings`**

Read and write application settings. Settings are a nested structure (e.g. `api_key`, `scraping`, `ranking`, `downloaders`).

---

## GET `/api/v1/settings/schema`

Get the full JSON schema for the settings model.

**Response:** JSON schema object (Pydantic `model_json_schema()`).

---

## GET `/api/v1/settings/schema/keys`

Get JSON schema for a subset of top-level keys.

**Query:** `keys` — comma-separated list (e.g. `version,api_key,updaters`). `title` — optional schema title (default `"FilteredSettings"`).

**Response:** Filtered schema with only the requested keys.

**Errors:** 400 if no keys or invalid keys (response lists valid keys).

---

## GET `/api/v1/settings/load`

Reload settings from disk into memory.

**Response:** `{ "message": "Settings loaded!" }`

---

## POST `/api/v1/settings/save`

Persist current in-memory settings to disk.

**Response:** `{ "message": "Settings saved!" }`

---

## GET `/api/v1/settings/get/all`

Get the entire settings object.

**Response:** Full settings model (nested dict with `version`, `api_key`, `scraping`, `ranking`, `downloaders`, `content`, `filesystem`, etc.).

---

## GET `/api/v1/settings/get/{paths}`

Get one or more settings paths. Paths are dot-separated (e.g. `scraping.bucket_limit`, `downloaders.real_debrid.api_key`).

**Path:** `paths` — comma-separated list of paths.

**Response:** `{ "<path>": <value>, ... }` — only keys that exist are returned.

**Example:** `GET /api/v1/settings/get/scraping.bucket_limit,ranking.resolutions` → `{ "scraping.bucket_limit": 10, "ranking.resolutions": { ... } }`

---

## POST `/api/v1/settings/set/all`

Replace entire settings with a nested object. Validates and saves.

**Body:** Nested dict matching settings schema (partial or full).

**Response:** `{ "message": "All settings updated successfully!" }`

**Errors:** 400 if validation fails.

---

## POST `/api/v1/settings/set/{paths}`

Set one or more paths to new values.

**Path:** `paths` — comma-separated (e.g. `scraping.bucket_limit`).

**Body:** `{ "<path>": <value>, ... }` — must include a value for each path in `paths`.

**Example:** `POST /api/v1/settings/set/scraping.bucket_limit` with body `{ "scraping.bucket_limit": 15 }`.

**Response:** `{ "message": "Settings updated successfully." }`

**Errors:** 400 if path doesn't exist, value missing, or validation fails.
