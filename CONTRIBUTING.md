# Contributing

We want to make contributing to this project as easy and transparent as
possible.

### Submitting Changes

1. **Open an Issue**: For major changes, start by opening an issue to discuss your proposed modifications. This helps us understand your intentions and provide feedback early in the process.
2. **Pull Requests**: Once your changes are ready, submit a pull request. Ensure your code adheres to our coding standards and passes all tests. Commits should follow [conventional-commits](https://www.conventionalcommits.org/) specification.

### Code Formatting

-   **Backend**: We use [Black](https://black.readthedocs.io/en/stable/) for code formatting. Run `uv run black` on your code before submitting.
-   **Line Endings**: Use CRLF line endings unless the file is a shell script or another format that requires LF line endings.

## Development

Welcome! This section covers local development setup and workflows.

### Prerequisites
> [!IMPORTANT]
> Development is supported on Linux only. Windows is not supported.

- Python (3.13+)
- uv (for dependency management and virtual envs)

Install uv quickly:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```


### Initial Setup

1) Clone the repository

```sh
git clone https://github.com/rivenmedia/riven.git && cd riven
```

2) Install system dependencies (example for Debian/Ubuntu)

```sh
sudo apt-get update
sudo apt-get install -y \
  libssl-dev \
  libfuse3-dev \
  pkg-config \
  fuse3
```

3) Install Python dependencies with uv

```sh
uv sync
```

### Using make

A Makefile is provided for common tasks. Explore available commands:

```sh
make run
```

Additionally, you can view all the commands by running `make`.

Which outputs:

```sh
make install     - Install dependencies
make run         - Run the application
make build       - Build the application image
make push        - Build and push the application image to Docker Hub
make push-dev    - Build and push the dev image to Docker Hub
make push-branch - Build and push the branch image to Docker Hub
make tidy        - Remove unused Docker images
make clean       - Clean up temporary files
make hard_reset  - Hard reset the database
make format      - Format the code
make check       - Check the code for errors
make sort        - Sort the imports
make test        - Run the tests
make coverage    - Run the tests with coverage
make pr-ready    - Run the linter and tests
make update      - Update dependencies
```
### Development without make

Run the app directly with uv:

```sh
uv run python src/main.py
```

### Dependency Management (uv)

- Sync/install from lock: `uv sync`
- Add a dependency: `uv add <package>`
- Add a dev dependency: `uv add --dev <package>`
- Upgrade a dependency: `uv add --upgrade <package>`
- Remove a dependency: `uv remove <package>`

#### Update Dependencies

```sh
uv sync --group dev
```

### Running Tests and Linters

- Run tests: `uv run pytest`
- Ruff lint: `uv run ruff check src`
- isort check: `uv run isort --check-only src`
- Black format: `uv run black .`

### Pre-commit Hooks

Pre-commit is configured to run formatters and linters before commits.

```sh
uv run pre-commit install
uv run pre-commit run --all-files
```
## License

By contributing to examples, you agree that your contributions will be licensed
under the LICENSE file in the root directory of this source tree.
