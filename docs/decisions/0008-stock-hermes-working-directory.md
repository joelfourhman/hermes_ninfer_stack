# ADR 0008: Preserve stock Hermes working-directory behavior

- Status: accepted
- Date: 2026-09-05

## Context

ADR 0005 made the NInfer helper set Hermes's terminal directory to this
repository's `workspace/` and applied `HERMES_WRITE_SAFE_ROOT` to that folder
and the Hermes profile. This made a native stock Hermes installation feel tied
to the NInfer repository and could surprise users when skills, projects, or
scheduled work lived elsewhere. The safe-root applied only to direct file
tools; local terminal commands still had the user's full authority.

## Decision

The helper configures only the local NInfer provider, the tested context and
compression values, the local terminal backend, and manual approvals. It
explicitly unsets the former `terminal.cwd` override and removes the former
`HERMES_WRITE_SAFE_ROOT` entry from Hermes's private environment.

Hermes therefore follows upstream defaults: Desktop and gateway work begin in
the user's home directory when no working directory is configured, and CLI
sessions use their launch directory. Hermes's built-in credential and
protected-path denylist remains active. Manual approvals remain a deliberate
safety override because local terminal tools run as the signed-in user.

Existing content under the repository's legacy `workspace/` is not moved or
deleted. Users may open it as an ordinary project or move it themselves.

## Consequences

- Hermes behaves like a normal native installation and can work naturally in
  any user-selected project.
- The NInfer repository is no longer presented as a universal workspace.
- Direct file tools are no longer confined to two project-defined roots.
- Safety depends on manual approvals, the upstream protected-path denylist,
  backups, and—when real containment is needed—an isolated execution backend.
