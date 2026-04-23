> [!IMPORTANT]
> Historical, non-normative v0.1 material. For current behavior, use
> [docs/specs/xfusion-v0.2.md](../../specs/xfusion-v0.2.md).

# Lima Ubuntu Demo Sandbox

The official v0.1 demo sandbox is a local Lima Ubuntu 24.04 VM on Apple Silicon macOS.

## Install Lima

```bash
brew install lima
```

## Create Demo VM

```bash
limactl start --name xfusion-demo template://ubuntu-24.04
```

## Enter VM

```bash
limactl shell xfusion-demo
```

## Prepare Project

Inside the VM, install `uv` and sync dependencies:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd /path/to/xfusion
uv sync --dev
```

## Run Agent

```bash
export XFUSION_AUDIT_LOG_PATH=audit.jsonl
uv run xfusion
```

## Run Opt-In Rehearsal Smoke

Inside the VM:

```bash
XFUSION_RUN_LIVE_VM=1 uv run pytest tests/test_live_vm_rehearsal.py -q
```

The live rehearsal is skipped by default outside this explicit opt-in.

## Fallback

If Lima setup fails, Multipass Ubuntu is acceptable. Docker is acceptable only for development smoke tests, not for the official demo, because container behavior differs from a real server OS for systemd, sudo, users, and process management.
