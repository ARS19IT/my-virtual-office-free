"""Provider-neutral, brokered browser actions for Virtual Office."""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import threading
import time
import urllib.request
import urllib.parse

_LOCK = threading.Lock()


def _token(config):
    browser = (config.get("browser") or {}) if isinstance(config, dict) else {}
    return str(os.environ.get("VO_BROWSER_TOKEN") or browser.get("actionToken") or "").strip()


def authorize(headers, config):
    expected = _token(config)
    supplied = str(headers.get("X-Virtual-Office-Browser-Token") or "").strip()
    auth = str(headers.get("Authorization") or "")
    if auth.lower().startswith("bearer "):
        supplied = auth.split(" ", 1)[1].strip()
    return bool(expected) and hmac.compare_digest(supplied, expected)


def _cdp_url(config):
    return str((config.get("browser") or {}).get("cdpUrl") or "").rstrip("/")


def _json_tabs(config):
    url = _cdp_url(config)
    if not url:
        raise RuntimeError("CDP backend is not configured")
    with urllib.request.urlopen(url + "/json", timeout=4) as response:
        return json.loads(response.read().decode("utf-8"))


def _tab(tabs, target_id=None):
    pages = [t for t in tabs if isinstance(t, dict) and t.get("type") == "page"]
    if target_id:
        pages = [t for t in pages if t.get("id") == target_id]
    if not pages:
        raise RuntimeError("No matching browser page")
    return pages[0]

async def _call(ws_url, method, params=None):
    from websockets.asyncio.client import connect as ws_connect
    async with ws_connect(ws_url, open_timeout=4, close_timeout=4, max_size=16 * 1024 * 1024) as ws:
        msg_id = 1
        await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            item = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if item.get("id") != msg_id:
                continue
            if item.get("error"):
                raise RuntimeError(item["error"].get("message", "CDP error"))
            return item.get("result") or {}


def action(config, request):
    """Execute one allowlisted action while holding the global browser lock."""
    if not ((config.get("features") or {}).get("browserPanel") and _feature_allowed()):
        return {"ok": False, "status": 403, "error": "Browser feature is disabled by the free/demo gate"}
    op = str(request.get("action") or "status").lower()
    allowed = {"status", "tabs", "navigate", "click", "type", "input", "screenshot"}
    if op not in allowed:
        return {"ok": False, "status": 400, "error": "Unsupported browser action"}
    with _LOCK:
        try:
            tabs = _json_tabs(config)
            if op == "status":
                return {"ok": True, "enabled": True, "cdpAvailable": True, "tabCount": len([t for t in tabs if t.get("type") == "page"])}
            if op == "tabs":
                return {"ok": True, "tabs": tabs}
            page = _tab(tabs, request.get("targetId"))
            if op == "navigate":
                url = str(request.get("url") or "").strip()
                parsed = urllib.parse.urlparse(url)
                if parsed.scheme not in {"http", "https"}:
                    return {"ok": False, "status": 400, "error": "Only http(s) navigation is allowed"}
                result = asyncio.run(_call(page["webSocketDebuggerUrl"], "Page.navigate", {"url": url}))
                return {"ok": True, "action": op, "targetId": page.get("id"), "result": result}
            if op in {"click", "type", "input"}:
                selector = str(request.get("selector") or "").strip()
                if not selector or len(selector) > 500:
                    return {"ok": False, "status": 400, "error": "selector is required"}
                if op == "click":
                    expr = "(() => { const e=document.querySelector(%s); if(!e) throw new Error('selector not found'); e.click(); return true; })()" % json.dumps(selector)
                    result = asyncio.run(_call(page["webSocketDebuggerUrl"], "Runtime.evaluate", {"expression": expr, "returnByValue": True}))
                else:
                    value = str(request.get("text") if request.get("text") is not None else request.get("value") or "")
                    expr = "(() => { const e=document.querySelector(%s); if(!e) throw new Error('selector not found'); e.focus(); return true; })()" % json.dumps(selector)
                    asyncio.run(_call(page["webSocketDebuggerUrl"], "Runtime.evaluate", {"expression": expr, "returnByValue": True}))
                    result = asyncio.run(_call(page["webSocketDebuggerUrl"], "Input.insertText", {"text": value}))
                return {"ok": True, "action": op, "targetId": page.get("id"), "result": result}
            result = asyncio.run(_call(page["webSocketDebuggerUrl"], "Page.captureScreenshot", {"format": "png"}))
            return {"ok": True, "action": op, "targetId": page.get("id"), "data": result.get("data"), "encoding": "base64"}
        except Exception as exc:
            return {"ok": False, "status": 502, "error": str(exc)}


def _feature_allowed():
    # Imported lazily so this module remains independently testable.
    try:
        from license import check_feature
        return bool(check_feature("browserPanel"))
    except Exception:
        return True
