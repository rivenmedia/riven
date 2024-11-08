FROM python:3.11-slim

# Install system dependencies including rclone and fuse
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    rclone \
    fuse3 \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && apt-get update \
    && apt-get install -y sudo \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Install poetry
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VERSION=1.7.1
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    cd /usr/local/bin && \
    ln -s /opt/poetry/bin/poetry

# Set up working directory
WORKDIR /workspace

# Configure poetry
RUN poetry config virtualenvs.create false

ENV PYTHONPATH=/workspace
ENV PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user and ensure they own the workspace
RUN chown -R $USERNAME:$USERNAME /workspace

# Switch to non-root user
USER $USERNAME