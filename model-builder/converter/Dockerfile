FROM ghcr.io/astral-sh/uv:0.12.5-python3.13-trixie-slim@sha256:d1e005e6f5aac724b7554db95f1c128a77d8d35b59ebe70e188852b4bdad3a3d AS uv

FROM nvidia/cuda:13.1.2-runtime-ubuntu24.04

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

LABEL org.opencontainers.image.source="https://github.com/joelfourhman/hermes_ninfer_stack"
LABEL org.opencontainers.image.description="uv-locked offline converter for Qwen3.8-27B Uncensored"

ENV UV_FROZEN=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/converter \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

WORKDIR /app
COPY converter/pyproject.toml converter/uv.lock ./
RUN uv python install 3.12 \
    && uv sync --no-dev --no-install-project

COPY converter/convert_model.py /app/convert_model.py

ENTRYPOINT ["/opt/converter/bin/python", "/app/convert_model.py"]
