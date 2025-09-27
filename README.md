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

- [Table of Contents](#table-of-contents)
- [ElfHosted](#elfhosted)
- [Self Hosted](#self-hosted)
  - [Installation](#installation)
  - [Plex](#plex)
- [RivenVFS and Caching](#rivenvfs-and-caching)
- [Development](#development)
  - [Prerequisites](#prerequisites)
  - [Initial Setup](#initial-setup)
  - [Using `make` for Development](#using-make-for-development)
  - [Development without `make`](#development-without-make)
  - [Additional Tips](#additional-tips)
- [Contributing](#contributing)
  - [Submitting Changes](#submitting-changes)
  - [Code Formatting](#code-formatting)
  - [Dependency Management](#dependency-management)
    - [Adding or Updating Dependencies](#adding-or-updating-dependencies)
  - [Running Tests and Linters](#running-tests-and-linters)
- [License](#license)

---

## ElfHosted

[ElfHosted](https://elfhosted.com) is a geeky [open-source](https://elfhosted.com/open/) PaaS which provides all the "plumbing" (_hosting, security, updates, etc_) for your self-hosted apps.

> [!IMPORTANT]
> **ElfHosted ❤️ Riven 100%**
> [Riven](https://elfhosted.com/app/riven/) is an "Elf-icial" app in the [ElfHosted app catalogue](https://elfhosted.com/apps/) - A whopping :heart_eyes_cat::heart_eyes_cat: 100% :heart_eyes_cat::heart_eyes_cat: of your subscription goes directly to Riven developers, who can usually be found in the [#elf-riven](https://discord.com/channels/396055506072109067/1253110932062601276) channel in the [ElfHosted Discord Server](https://discord.elfhosted.com).

Curious how it works? Here's an [explainer video](https://www.youtube.com/watch?v=ZHZAEhLuJqk)!

> [!TIP]
> **ElfHosted "Infinite Streaming" bundles**
> Riven is pre-packaged with Plex, Zurg, and symlinks, and ready-to-go, in these convenient bundles:
>
> -   [Starter Kit](https://store.elfhosted.com/product/plex-riven-infinite-streaming-starter-kit) (_quick and easy setup_)
> -   [Hobbit Bundle](https://store.elfhosted.com/product/hobbit-riven-real-debrid-infinite-streaming-bundle) (_12.5% dedicated node, with extras_)
> -   [Ranger Bundle](https://store.elfhosted.com/product/plex-riven-infinite-streaming-plus-bundle) (_25% dedicated node, with extras_)

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

### What the settings do (MB units)
- `vfs_cache_dir`: Directory to store on‑disk cache files (use a user‑writable path).
- `vfs_cache_max_size_mb`: Max cache size (MB) for the VFS cache directory.
- `vfs_chunk_mb`: Size of individual CDN requests (MB). Default 32MB provides good balance between efficiency and connection reliability.
- `fetch_ahead_size_mb`: Total amount of data (MB) to prefetch ahead of current read position. Default 128MB prefetches ~4 chunks ahead for smooth streaming.
- `ttl_seconds`: Optional expiry horizon when using `eviction = "TTL"` (default eviction is `LRU`).

- Eviction behavior:
  - LRU (default): Strictly enforces the configured size caps by evicting least‑recently‑used blocks when space is needed.
  - TTL: First removes entries that have been idle longer than `ttl_seconds` (sliding expiration). If the cache still exceeds the configured size cap after TTL pruning, it additionally trims oldest entries (LRU) until usage is within the limit.

## Development

Welcome to the development section! Here, you'll find all the necessary steps to set up your development environment and start contributing to the project.

### Prerequisites

Ensure you have the following installed on your system:

-   **Python** (3.10+)

### Initial Setup

1. **Clone the Repository:**

    ```sh
    git clone https://github.com/rivenmedia/riven.git && cd riven
    ```

2. **Install Dependencies:**

    ```sh
    apk add --no-cache \
    openssl-dev \
    fuse3-dev \
    pkgconf \
    fuse3
    ```

3. **Install Python Dependencies:**

    ```sh
    pip install poetry
    poetry install
    ```

### Using `make` for Development

We provide a `Makefile` to simplify common development tasks. Here are some useful commands:

-   **Initialize the Project:**

    ```sh
    make
    ```

-   **Start the Development Environment:**
    This command stops any previous containers, removes old images, and rebuilds the image using cached layers. Any changes in the code will trigger a rebuild.

    ```sh
    make start
    ```

-   **Restart the Container:**

    ```sh
    make restart
    ```

-   **View Logs:**
    ```sh
    make logs
    ```

### Development without `make`

If you prefer not to use `make` and Docker, you can manually set up the development environment with the following steps:

1. **Start Riven:**

    ```sh
    poetry run python src/main.py
    ```

### Additional Tips

-   **Environment Variables:**
    Ensure you set the `ORIGIN` environment variable to the URL where the frontend will be accessible. For example:

    ```sh
    export ORIGIN=http://localhost:3000
    ```

By following these guidelines, you'll be able to set up your development environment smoothly and start contributing to the project. Happy coding!

---

## Contributing

We welcome contributions from the community! To ensure a smooth collaboration, please follow these guidelines:

### Submitting Changes

1. **Open an Issue**: For major changes, start by opening an issue to discuss your proposed modifications. This helps us understand your intentions and provide feedback early in the process.
2. **Pull Requests**: Once your changes are ready, submit a pull request. Ensure your code adheres to our coding standards and passes all tests. Commits should follow [conventional-commits](https://www.conventionalcommits.org/) specification.

### Code Formatting

-   We use [Black](https://black.readthedocs.io/en/stable/) for code formatting. Run `black` on your code before submitting.
-   Use CRLF line endings unless the file is a shell script or another format that requires LF line endings.

### Dependency Management

We use [Poetry](https://python-poetry.org/) for managing dependencies. Poetry simplifies dependency management by automatically handling package versions and resolving conflicts, ensuring consistency across all environments.

#### Adding or Updating Dependencies

-   **Add a Dependency**: Use `poetry add <package-name>` to add a new dependency.
-   **Update a Dependency**: Use `poetry update <package-name>` to update an existing dependency.

### Running Tests and Linters

Before submitting a pull request, ensure your changes are compatible with the project's dependencies and coding standards. Use the following commands to run tests and linters:

-   **Run Tests**: `poetry run pytest`
-   **Run Linters**: `poetry run ruff check backend` and `poetry run isort --check-only backend`

By following these guidelines, you help us maintain a high-quality codebase and streamline the review process. Thank you for contributing!

---

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
