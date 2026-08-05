# TorBox forward-port

This branch starts at upstream `v1.0.0-beta.1` and forward-ports the TorBox
provider introduced by `TorBox-App/riven` after common ancestor
`38fc68bc3bebd6d38cf56d713a94c7013d3d6929`.

## Included

- TorBox settings (`enabled` and `api_key`) and environment examples.
- Provider registration in Riven's multi-downloader pipeline.
- Premium-account validation through `GET /user/me`.
- Cached availability through `GET /torrents/checkcached`.
- Cached-only torrent creation through `POST /torrents/createtorrent`.
- Torrent metadata, file mapping, persistent download permalinks, and deletion.
- Riven/TorBox user-agent and current `SmartSession` retry, proxy, rate-limit,
  and circuit-breaker behavior.

## Configuration

```dotenv
RIVEN_DOWNLOADERS_TORBOX_ENABLED=true
RIVEN_DOWNLOADERS_TORBOX_API_KEY=your_api_key
```

The equivalent `settings.json` keys are `downloaders.torbox.enabled` and
`downloaders.torbox.api_key`.

## Design notes and limitations

- Riven only accepts cached TorBox torrents. `add_only_if_cached=true` prevents
  accidentally consuming an uncached download slot.
- TorBox has no file-selection endpoint, so `select_files` is intentionally a
  no-op.
- Download URLs use the TorBox-recommended permalink form. The API token is
  therefore embedded in Riven's stored media URL; protect the Riven database,
  settings, and logs accordingly. Resetting the token invalidates old links.
- No live TorBox account test is performed by the unit suite. A real account
  smoke test is still required before production use.
- This backend repository does not contain the separately maintained Riven
  frontend, so no provider-specific frontend form is included. The settings API
  and environment variables remain usable.

## Upstream comparison

The source fork added TorBox in seven focused commits plus test follow-ups:

- `fbc8f99` TorBox base
- `3134d8a` instant availability
- `9174057` authentication and cache handling
- `ba04dbd` settings
- `778998c` / `53f4e25` user-agent analytics
- `a6eeb15` / `c43448a` downloader tests

The old implementation used Riven's removed `BaseRequestHandler` stack and did
not implement the current `get_user_info` and `unrestrict_link` interface. This
port adapts those behaviors rather than cherry-picking the obsolete files.
