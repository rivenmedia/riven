<div align="center">
  <a href="https://github.com/rivenmedia/riven">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/rivenmedia/riven/main/assets/riven-light.png">
      <img alt="riven" src="https://raw.githubusercontent.com/rivenmedia/riven/main/assets/riven-dark.png">
    </picture>
  </a>
</div>

<div align="center">
  <a href="https://github.com/rivenmedia/riven/stargazers"><img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/rivenmedia/riven"></a>
  <a href="https://github.com/rivenmedia/riven/issues"><img alt="Issues" src="https://img.shields.io/github/issues/rivenmedia/riven" /></a>
  <a href="https://github.com/rivenmedia/riven/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/rivenmedia/riven"></a>
  <a href="https://github.com/rivenmedia/riven/graphs/contributors"><img alt="Contributors" src="https://img.shields.io/github/contributors/rivenmedia/riven" /></a>
  <a href="https://discord.gg/rivenmedia"><img alt="Discord" src="https://img.shields.io/badge/Join%20discord-8A2BE2" /></a>
</div>

<div align="center">
  <p>Plex torrent streaming through Debrid and 3rd party services like Overseerr, Mdblist, etc.</p>
</div>

Services currently supported:

| Type              | Supported                                                                         |
| ----------------- | --------------------------------------------------------------------------------- |
| Debrid services   | Real Debrid, All Debrid, TorBox                                                   |
| Content services  | Plex Watchlist, Overseerr, Mdblist, Listrr, Trakt                                 |
| Scraping services | Comet, Jackett, Torrentio, Orionoid, Mediafusion, Prowlarr, Zilean, Rarbg         |
| Media servers     | Plex, Jellyfin, Emby                                                              |

and more to come!

Check out out [Project Board](https://github.com/users/dreulavelle/projects/2) to stay informed!

Please add feature requests and issues over on our [Issue Tracker](https://github.com/rivenmedia/riven/issues) or join our [Discord](https://discord.gg/rivenmedia) to chat with us!

We are constantly adding features and improvements as we go along and squashing bugs as they arise.

---

## Table of Contents

- [Self Hosted](#self-hosted)
  - [Installation](#installation)
  - [Plex](#plex)
- [RivenVFS and Caching](#rivenvfs-and-caching)
- [Contributing](#contributing)
- [License](#license)

---

## Self Hosted

### Installation

1) Find a good place on your hard drive we can call mount from now on. For the sake of things I will call it /path/to/riven/mount.

2) Copy over the contents of [docker-compose.yml](docker-compose.yml) to your `docker-compose.yml` file.

- Modify the PATHS in the `docker-compose.yml` file volumes to match your environment. When adding /mount to any container, make sure to add `:rshared,z` to the end of the volume mount. Like this:

```yaml
volumes:
  - /path/to/riven/data:/riven/data
  - /path/to/riven/mount:/mount:rshared,z
```

3) Make your mount directory a bind mount and mark it shared (run once per boot):

```bash
sudo mkdir -p /path/to/riven/mount
sudo mount --bind /path/to/riven/mount /path/to/riven/mount
sudo mount --make-rshared /path/to/riven/mount
```

- Verify propagation:

```bash
findmnt -T /path/to/riven/mount -o TARGET,PROPAGATION  # expect: shared or rshared
```

> [!TIP]
> **Make it automatic on boot**
>
>- Option A – systemd one-shot unit:
>
>```ini
>[Unit]
>Description=Make Riven data bind mount shared
>After=local-fs.target
>Before=docker.service
>
>[Service]
>Type=oneshot
>ExecStart=/usr/bin/mount --bind /path/to/riven/mount /path/to/riven/mount
>ExecStart=/usr/bin/mount --make-rshared /path/to/riven/mount
>RemainAfterExit=yes
>
>[Install]
>WantedBy=multi-user.target
>```
>
>Enable it:
>
>```bash
>sudo systemctl enable --now riven-bind-shared.service
>```
>
>- Option B – fstab entry:
>
>```fstab
>/path/to/riven/mount  /path/to/riven/mount  none  bind,rshared  0  0
>```
>
>Notes:
>- Keep your FUSE mount configured with allow_other (Dockerfile sets user_allow_other in /etc/fuse.conf so you dont have to).
>- On SELinux systems, add :z to the bind mount if needed.


## Plex

Plex libraries that are currently required to have sections:

| Type   | Categories               |
| ------ | ------------------------ |
| Movies | `movies`, `anime_movies` |
| Shows  | `shows`, `anime_shows`   |

> [!NOTE]
> Currently, these Plex library requirements are mandatory. However, we plan to make them customizable in the future to support additional libraries as per user preferences.


### Troubleshooting: Plex shows empty /mount after Riven restart

If Plex’s library path appears empty inside the Plex container after restarting Riven/RivenVFS, it’s almost always mount propagation and/or timing. Use the steps below to diagnose and fix without restarting Plex.

1) Verify the host path is shared (required)

- Mark your host mount directory as a shared bind mount (one-time per boot):

```bash
sudo mkdir -p /path/to/riven/mount
sudo mount --bind /path/to/riven/mount /path/to/riven/mount
sudo mount --make-rshared /path/to/riven/mount
findmnt -T /path/to/riven/mount -o TARGET,PROPAGATION  # expect: shared or rshared
```

2) Verify propagation inside the Plex container

- The container must also receive mount events recursively (rslave or rshared):

```bash
docker exec -it plex sh -c 'findmnt -T /mount -o TARGET,PROPAGATION,OPTIONS,FSTYPE'
# PROPAGATION should be rslave or rshared, FSTYPE should show fuse when RivenVFS is mounted
```

- In docker-compose for Plex, ensure the bind includes mount propagation (and SELinux label if needed):

```yaml
  - /path/to/riven/mount:/mount:rslave,z
```

3) Ensure the path Riven mounts to is the container path

- In Riven settings, set the Filesystem mount path to the container path (typically `/mount`), not the host path. Both Riven (if containerized) and Plex should refer to the same in-container path for their libraries (e.g., `/mount/movies`, `/mount/shows`).

4) Clear a stale FUSE mount (after crashes)

- If a previous FUSE instance didn’t unmount cleanly on the host, a stale mount can block remounts.

```bash
sudo fusermount -uz /path/to/riven/mount || sudo umount -l /path/to/riven/mount
# then start Riven again
```

6) Expected behavior during restart window

- When Riven stops, the FUSE mount unmounts and `/mount` may briefly appear empty inside the container; it will become FUSE again when Riven remounts. With proper propagation (host rshared + container rslave/rshared) and startup order, Plex should see the content return automatically without a restart. Enabling Plex’s “Automatically scan my library” can also help it pick up changes.

## RivenVFS and Caching

### What the settings do
- `cache_dir`: Directory to store on‑disk cache files (use a user‑writable path).
- `cache_max_size_mb`: Max cache size (MB) for the VFS cache directory.
- `chunk_size_mb`: Size of individual CDN requests (MB). Default 32MB provides good balance between efficiency and connection reliability.
- `fetch_ahead_chunks`: Number of chunks to prefetch ahead of current read position. Default 4 chunks prefetches 128MB ahead (4 × 32MB) for smooth streaming with fair multi-user scheduling.
- `ttl_seconds`: Optional expiry horizon when using `eviction = "TTL"` (default eviction is `LRU`).

- Eviction behavior:
  - LRU (default): Strictly enforces the configured size caps by evicting least‑recently‑used blocks when space is needed.
  - TTL: First removes entries that have been idle longer than `ttl_seconds` (sliding expiration). If the cache still exceeds the configured size cap after TTL pruning, it additionally trims oldest entries (LRU) until usage is within the limit.

### Library Profiles

Library profiles allow you to organize media into different virtual libraries based on metadata filters. Media matching a profile appears at both the base path (e.g., `/movies/Title/`) and the profile path (e.g., `/kids/movies/Title/`).

**Configuration**: Edit `library_profiles` in `settings.json` under the `filesystem` section. Multiple example profiles are provided (disabled by default) - enable them or create your own.

**Available Filters**:

| Filter | Type | Description | Example |
|--------|------|-------------|---------|
| `content_types` | List[str] | Media types to include (`movie`, `show`) | `["movie", "show"]` |
| `genres` | List[str] | Include if ANY genre matches (OR logic). Use `!` to exclude values. | `["animation", "family", "!horror"]` |
| `min_year` | int | Minimum release year | `2020` |
| `min_year` | int | Minimum release year | `2020` |
| `max_year` | int | Maximum release year | `1999` |
| `min_rating` | float | Minimum rating (0-10 scale) | `7.5` |
| `max_rating` | float | Maximum rating (0-10 scale) | `9.0` |
| `is_anime` | bool | Filter by anime flag (true/false) | `true` |
| `networks` | List[str] | TV networks (OR logic) | `["HBO", "HBO Max"]` |
| `countries` | List[str] | Countries of origin (ISO codes, OR logic) | `["GB", "UK"]` |
| `languages` | List[str] | Original languages (ISO 639-1 codes, OR logic) | `["en", "ja"]` |
| `content_ratings` | List[str] | Allowed content ratings | `["G", "PG", "TV-Y"]` |

> Exclusion syntax: For any list-based filter (genres, networks, countries, languages, content_ratings), prefix a value with `!` to exclude it.

**Content Ratings Reference**:
- **US Movies**: `G`, `PG`, `PG-13`, `R`, `NC-17`, `NR` (Not Rated), `Unrated`
- **US TV**: `TV-Y`, `TV-Y7`, `TV-G`, `TV-PG`, `TV-14`, `TV-MA`

**Example Profile**:
```json
{
  "filesystem": {
    "library_profiles": {
      "kids": {
        "name": "Kids & Family Content",
        "library_path": "/kids",
        "enabled": true,
        "filter_rules": {
          "content_types": ["movie", "show"],
          "genres": ["animation", "family", "!horror"],
          "content_ratings": ["G", "PG", "TV-Y", "TV-G", "!TV-MA"],
          "max_rating": 7.5
        }
      }
    }
  }
}
```

**How It Works**:
1. Media is downloaded and metadata is evaluated against all enabled profiles
2. Matching media appears at base path + all matching profile paths
3. Media servers (Plex/Jellyfin/Emby) see the content in all applicable libraries
4. Filters use AND logic between different filter types, OR logic within list filters

**Notes**:
- Remove any filter you don't want to use
- All filters must match for a profile to apply (AND logic)
- List filters (genres, networks, etc.) match if ANY value matches (OR logic)
- Shows/Seasons inherit metadata from parent for filtering purposes


## Contributing

We welcome contributions from the community! For development setup, dependency management, coding standards, and how to run tests, please see the Contributing Guide.

- Contributing Guide: [CONTRIBUTING.md](./CONTRIBUTING.md)
- Issues: https://github.com/rivenmedia/riven/issues
- Discord: https://discord.gg/rivenmedia

Commits should follow the [conventional-commits](https://www.conventionalcommits.org/) specification.
<a href="https://github.com/rivenmedia/riven/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=rivenmedia/riven" />
</a>

---

<div align="center">
  <h1>Riven Analytics</h1>
  <img alt="Alt" src="https://repobeats.axiom.co/api/embed/9a780bcd591b50aa26de6b8226b1de938bde5adb.svg" title="Repobeats analytics image">
</div>

## License

This project is licensed under the GNU GPLv3 License - see the [LICENSE](LICENSE) file for details
