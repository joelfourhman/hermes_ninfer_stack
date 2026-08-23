# Shared Hermes workspace

Files placed here are visible to Hermes at `/workspace` through the isolated
SSH sandbox. The sandbox is the only execution service with this directory as
its working tree; it has no Docker socket, GPU, privileged mode, or host port.
