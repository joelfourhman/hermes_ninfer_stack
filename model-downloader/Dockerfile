FROM ghcr.io/astral-sh/uv:0.12.5-python3.13-trixie-slim@sha256:d1e005e6f5aac724b7554db95f1c128a77d8d35b59ebe70e188852b4bdad3a3d

LABEL org.opencontainers.image.source="https://github.com/joelfourhman/hermes_ninfer_stack"
LABEL org.opencontainers.image.description="uv-managed downloader for the pinned NInfer model artifact"

ENV UV_PYTHON_DOWNLOADS=0 \
    UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_TOOL_DIR=/opt/uv-tools

RUN uv tool install --python /usr/local/bin/python huggingface-hub==1.27.0

COPY download_model.py /usr/local/bin/download_model.py

ENTRYPOINT ["python", "/usr/local/bin/download_model.py"]
