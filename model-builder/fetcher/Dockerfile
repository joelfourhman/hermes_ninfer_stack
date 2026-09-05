FROM ghcr.io/astral-sh/uv:0.12.5-python3.13-trixie-slim@sha256:d1e005e6f5aac724b7554db95f1c128a77d8d35b59ebe70e188852b4bdad3a3d

LABEL org.opencontainers.image.source="https://github.com/joelfourhman/hermes_ninfer_stack"
LABEL org.opencontainers.image.description="uv-locked fetcher for the uncensored Qwen NInfer build inputs"

ENV UV_FROZEN=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/fetcher

WORKDIR /app
COPY fetcher/pyproject.toml fetcher/uv.lock ./
RUN uv sync --no-dev --no-install-project

COPY fetcher/fetch_sources.py /app/fetch_sources.py
COPY frontend.sha256 /app/frontend.sha256

ENTRYPOINT ["/opt/fetcher/bin/python", "/app/fetch_sources.py"]
