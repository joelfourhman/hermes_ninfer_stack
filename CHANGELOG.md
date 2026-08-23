# Changelog

All notable changes to this project will be documented in this file. The format
is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Reproducible Docker Compose topology for Hermes Agent, NInfer, and a separate
  SSH execution sandbox.
- Pinned Qwen3.8-27B NVFP4 model acquisition with revision and checksum
  verification.
- Local secret generation, Hermes configuration, layered verification, and
  benchmark helpers.
- GPU ownership, internal network, persistent-state, healthcheck, and startup
  ordering configuration.
- Architecture, installation, configuration, model, security, compatibility,
  performance, troubleshooting, and design documentation.
- Non-GPU continuous integration for static validation, Compose rendering,
  shell analysis, and the sandbox image build.
- Public issue templates, contribution guidance, a security policy, and an
  Apache-2.0 license for stack-authored files.

### Security

- Kept the NInfer host API on loopback and authenticated it with a generated
  bearer key.
- Isolated model-generated commands in a resource-limited, no-egress sandbox
  without Docker-socket, privileged, GPU, or broad host-filesystem access.
- Excluded secrets, model weights, Hermes runtime state, logs, SSH material,
  and workspace output from Git.
