FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
# Toolchain image only. No credentials, repository contents or Docker socket.
