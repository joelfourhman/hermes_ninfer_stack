# Optional Hermes workspace

This directory is a convenient starting folder for native Hermes Desktop
sessions. It is not mounted into Docker; NInfer receives prompts through its
authenticated API and has no access to these files.

The setup helper configures this as Hermes's starting folder and includes it in
`HERMES_WRITE_SAFE_ROOT`, so direct `write_file` and `patch` actions outside
this folder (and Hermes's own profile) are blocked. This is still an
organizational guardrail, not a complete security boundary: native terminal
commands run with the signed-in operating-system user's permissions and can
reach anything that user can reach. Keep backups, leave YOLO mode off, review
risky tool approvals, and do not place irreplaceable or secret-only files here.
