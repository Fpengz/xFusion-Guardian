> [!IMPORTANT]
> Historical, non-normative v0.1 material. For current behavior, use
> [docs/specs/xfusion-v0.2.md](../../specs/xfusion-v0.2.md).

# XFusion v0.1 Tool Definitions

Tools accept structured input and return structured output. They are scoped, non-interactive, and do not expose arbitrary shell passthrough.

## System

- `system.detect_os`: returns distro, version, current user, sudo availability, systemd availability, package manager, disk pressure, and active facts.
- `system.current_user`: returns the current user.
- `system.check_sudo`: reports whether `sudo` is available.
- `system.service_status`: reserved for service status inspection in the v0.1 tool surface.

## Disk

- `disk.check_usage`: reports root filesystem usage.
- `disk.find_large_directories`: runs a bounded one-level directory size scan.

## File

- `file.search`: searches for files/directories by name within a scoped path and limits result count.
- `file.preview_metadata`: returns path, size, and directory/file metadata.

## Process

- `process.list`: returns a bounded process list.
- `process.find_by_port`: returns processes listening on a requested port.
- `process.kill`: sends `SIGTERM` to a resolved PID after policy approval and typed confirmation.

## User

- `user.create`: runs explicit `sudo useradd -m <username>` after confirmation.
- `user.delete`: runs explicit `sudo userdel -r <username>` after confirmation.

## Cleanup

- `cleanup.safe_disk_cleanup`: previews bounded cleanup candidates in approved locations. v0.1 treats cleanup as a safety-first workflow and does not perform broad deletion.

## Planning

- `plan.explain_action`: explains supported actions and safe next steps.
