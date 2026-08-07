# Shared browser broker

All Virtual Office agents (OpenClaw, Hermes, Codex, and Claude Code) use the same provider-neutral endpoint:

`POST /api/browser/action`

The office server holds `VO_CDP_URL`; agents receive only a broker token (`VO_BROWSER_TOKEN`). Actions are serialized with one process-wide lock.

## Configure

```sh
export VO_BROWSER_TOKEN="$(openssl rand -hex 32)"
export VO_CDP_URL="http://127.0.0.1:9222"
export VO_VIEWER_URL="http://127.0.0.1:6901" # optional
```

The CDP service must expose `/json` and page entries with `webSocketDebuggerUrl`. For Chromium, start a dedicated profile with remote debugging, for example:

```sh
chromium --headless=new --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=9222 --user-data-dir=/tmp/vo-browser-profile
```

Do not expose port 9222 publicly. In Docker, bind it to the office container network or use a private sidecar. The office process must be able to reach it.

## Actions

```json
{"action":"status"}
{"action":"tabs"}
{"action":"navigate","url":"https://example.com"}
{"action":"click","targetId":"...","selector":"button.submit"}
{"action":"type","targetId":"...","selector":"input[name=q]","text":"hello"}
{"action":"screenshot","targetId":"..."}
```

Send `Authorization: Bearer $VO_BROWSER_TOKEN`. The endpoint rejects missing/invalid tokens, non-http(s) navigation, unsupported actions, and requests when the browser feature is disabled.

## Free/demo gate

The normal `browserPanel` license gate is unchanged. In demo/free mode the broker returns HTTP 403; this is intentional and must not be bypassed. A valid activation and `features.browserPanel=true` are required.

## Operational rules

Agents should announce browser work through office presence/communications, inspect `tabs` before acting, and retry/wait rather than racing another user or agent. Never place CDP URLs, VNC passwords, or broker tokens in a shared skill file, prompt, public log, or git repository.
