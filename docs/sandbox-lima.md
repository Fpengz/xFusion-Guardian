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

## Fallback

If Lima setup fails, Multipass Ubuntu is acceptable. Docker is acceptable only for development smoke tests, not for the official demo, because container behavior differs from a real server OS for systemd, sudo, users, and process management.

