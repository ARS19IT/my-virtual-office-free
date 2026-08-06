# My Virtual Office — Free Fork

A separately maintained personal fork of the AGPL-3.0 source, kept next to the upstream working copy.

## What is different

- Separate runtime data directory: `/tmp/virtual-office-free-status`
- Separate ports: HTTP `8092`, WebSocket `8093`
- Branded as `My Virtual Office — Free Fork`
- Full OpenClaw roster is surfaced by the fork's own roster mode, including the seven configured local agents.

The upstream working copy at `../my-virtual-office` is not modified by this fork. Keep the upstream AGPL notices and source-availability obligations when sharing or serving this modified version.

## Run locally

```sh
VO_FREE_FORK=1 \
VO_CONFIG=/tmp/virtual-office-free-status/vo-config.json \
VO_STATUS_DIR=/tmp/virtual-office-free-status \
VO_OPENCLAW_PATH=$HOME/.openclaw \
VO_PORT=8092 VO_WS_PORT=8093 \
.venv/bin/python app/server.py
```

Open <http://127.0.0.1:8092>.
