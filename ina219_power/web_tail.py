from __future__ import annotations

import asyncio
import os
import contextlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import AsyncIterator, Optional

from aiohttp import web


INDEX_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>INA219 Logs</title>
    <style>
      :root { color-scheme: dark; }
      body { margin: 0; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: #0b0e14; color: #d6deeb; }
      header { padding: 12px 14px; border-bottom: 1px solid #1b2333; position: sticky; top: 0; background: rgba(11,14,20,0.9); backdrop-filter: blur(8px); }
      .muted { color: #7f8ea3; font-size: 12px; }
      main { padding: 12px 14px; }
      pre { white-space: pre-wrap; word-break: break-word; margin: 0; }
      .line { padding: 2px 0; border-bottom: 1px dashed rgba(127,142,163,0.15); }
      .err { color: #ff757f; }
      a { color: #82aaff; }
    </style>
  </head>
  <body>
    <header>
      <div><strong>INA219 Power Monitor</strong></div>
      <div class="muted">Live tail of today’s CSV. Endpoint: <code>/tail</code></div>
      <div class="muted" id="status">Connecting…</div>
    </header>
    <main>
      <pre id="out"></pre>
    </main>
    <script>
      const out = document.getElementById('out');
      const statusEl = document.getElementById('status');
      const maxLines = 400;
      const lines = [];

      function render() {
        out.innerHTML = lines.map(l => `<div class="line">${l}</div>`).join("");
        window.scrollTo(0, document.body.scrollHeight);
      }

      function addLine(s) {
        lines.push(s.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;"));
        while (lines.length > maxLines) lines.shift();
        render();
      }

      const es = new EventSource("/tail");
      es.onopen = () => { statusEl.textContent = "Connected"; };
      es.onerror = () => { statusEl.textContent = "Disconnected (will retry)…"; };
      es.onmessage = (ev) => { addLine(ev.data); };
    </script>
  </body>
</html>
"""


@dataclass(frozen=True)
class TailConfig:
    log_dir: Path
    tail_lines: int = 50
    poll_interval_s: float = 0.25
    debug: bool = False


def _today_prefix() -> str:
    return date.today().isoformat()


def _pick_latest_csv_for_today(log_dir: Path) -> Optional[Path]:
    prefix = _today_prefix()
    candidates = sorted(log_dir.glob(f"{prefix}*.csv"))
    if not candidates:
        return None
    # Prefer newest by mtime
    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return candidates[0]


def _read_last_lines(path: Path, n: int) -> list[str]:
    if n <= 0:
        return []
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = data.splitlines()
    return lines[-n:]


async def _follow_lines(cfg: TailConfig) -> AsyncIterator[str]:
    last_path: Optional[Path] = None
    last_size: int = 0

    while True:
        cfg.log_dir.mkdir(parents=True, exist_ok=True)
        path = _pick_latest_csv_for_today(cfg.log_dir)

        if path is None:
            yield "waiting for today's log file to be created…"
            await asyncio.sleep(1.0)
            continue

        if last_path != path:
            last_path = path
            last_size = 0
            yield f"--- now tailing: {path.name} ---"
            for line in _read_last_lines(path, cfg.tail_lines):
                yield line
            try:
                last_size = path.stat().st_size
            except OSError:
                last_size = 0

        try:
            size = last_path.stat().st_size
        except OSError:
            yield "log file temporarily unavailable; retrying…"
            await asyncio.sleep(1.0)
            continue

        if size < last_size:
            # truncated/rotated in-place
            last_size = 0

        if size > last_size:
            try:
                with last_path.open("r", encoding="utf-8", errors="replace") as f:
                    f.seek(last_size)
                    chunk = f.read()
            except OSError:
                chunk = ""
            if chunk:
                for line in chunk.splitlines():
                    yield line
            last_size = size

        await asyncio.sleep(cfg.poll_interval_s)


async def index(_request: web.Request) -> web.Response:
    return web.Response(text=INDEX_HTML, content_type="text/html")


async def healthz(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def tail(request: web.Request) -> web.StreamResponse:
    cfg: TailConfig = request.app["tail_cfg"]

    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await resp.prepare(request)

    async def _send(line: str) -> None:
        payload = f"data: {line}\n\n"
        await resp.write(payload.encode("utf-8", errors="replace"))

    try:
        async for line in _follow_lines(cfg):
            await _send(line)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        await _send(f"error: {e!r}")
    finally:
        with contextlib.suppress(Exception):
            await resp.write_eof()

    return resp


def create_app(*, log_dir: str, tail_lines: int, debug: bool) -> web.Application:
    app = web.Application()
    app["tail_cfg"] = TailConfig(log_dir=Path(log_dir), tail_lines=tail_lines, debug=debug)
    app.router.add_get("/", index)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/tail", tail)
    return app


def run_server(*, host: str, port: int, log_dir: str, tail_lines: int, debug: bool) -> None:
    app = create_app(log_dir=log_dir, tail_lines=tail_lines, debug=debug)
    # When embedded in another process (we run this in a background thread),
    # aiohttp must not install signal handlers.
    web.run_app(
        app,
        host=host,
        port=port,
        access_log=None if not debug else "aiohttp.access",
        handle_signals=False,
    )

