# Discover / TMDB / TVDB API

Routes are mounted at **`/api/v1`** (no sub-prefix). They proxy to TMDB/TVDB and normalize responses; many include `in_library`, `library_item_id`, `library_state`, etc. when the item exists in the Riven library.

---

## Discover

### GET `/api/v1/discover/tmdb/movie`

Proxy to TMDB discover movie. Query params are passed through (e.g. `sort_by`, `with_genres`, `primary_release_year`).

**Query:** `page` (default 1).

**Response:** `{ "results": [...], "page": 1, "total_pages": N, "total_results": M }` — each result has normalized fields (`id`, `title`, `poster_path`, `year`, `media_type`, `tmdb_id`, `tvdb_id`, `overview`, `vote_average`) plus library status.

### GET `/api/v1/discover/tmdb/tv`

Same for TV discover. Query params passed through; `page` default 1.

---

## Search

### GET `/api/v1/search/tmdb/movie`

**Query:** `query` (required), `page` (default 1).

**Response:** TMDB search response with normalized results and library status.

### GET `/api/v1/search/tmdb/tv`

**Query:** `query`, `page`.

### GET `/api/v1/search/tmdb/multi`

Search movies, TV, and people.

**Query:** `query` (required), `page`, `include_people` (default true).

**Response:** Normalized results; people have `media_type: "person"`, `known_for`, etc.

### GET `/api/v1/search/tvdb`

**Query:** `query`, `remote_id`, `type` (default `"series"`), `limit` (default 20, max 100).

**Response:** TVDB search results.

---

## Trending

### GET `/api/v1/trending/tmdb/{media_type}/{window}`

**Path:** `media_type` = `movie` | `tv` | `all`; `window` = `day` | `week`.

**Response:** `{ "results": [...], "page", "total_pages", "total_results" }` with normalized results and library status.

---

## TMDB details

### GET `/api/v1/tmdb/movie/{movie_id}`

Movie details with `append_to_response` (e.g. credits, images).

### GET `/api/v1/tmdb/tv/{tv_id}`

TV show details.

### GET `/api/v1/tmdb/movie/{movie_id}/credits`

### GET `/api/v1/tmdb/tv/{tv_id}/credits`

### GET `/api/v1/tmdb/movie/{movie_id}/recommendations`

### GET `/api/v1/tmdb/movie/{movie_id}/similar`

### GET `/api/v1/tmdb/tv/{tv_id}/recommendations`

### GET `/api/v1/tmdb/tv/{tv_id}/similar`

### GET `/api/v1/tmdb/tv/{tv_id}/season/{season_number}/episode/{episode_number}`

Episode details.

### GET `/api/v1/tmdb/person/{person_id}`

Person details with credits, images.

### GET `/api/v1/tmdb/person/{person_id}/combined_credits`

### GET `/api/v1/tmdb/person/{person_id}/movie_credits`

### GET `/api/v1/tmdb/person/{person_id}/tv_credits`

---

## TVDB

### GET `/api/v1/tvdb/series/{series_id}`

Series details.

### GET `/api/v1/tvdb/series/{series_id}/season/{season_number}/episode/{episode_number}`

Episode details.

---

## Normalized item shape (TMDB)

Returned in discover/search/trending and attached to library status:

- `id`, `title`, `poster_path`, `year`, `media_type` (`movie` | `tv` | `person`), `indexer` (`tmdb` | `tvdb`)
- `overview`, `vote_average`, `tmdb_id`, `tvdb_id`
- `in_library`, `library_item_id`, `library_state`, `library_type`, `library_title` (when applicable)
