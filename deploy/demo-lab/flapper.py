"""SurfaceX demo lab: a target whose ports and services change on a schedule.

Cycles through phases so consecutive scans show NEW / CHANGED / GONE / FLAKY
findings. Standard library only. Intended for an isolated Docker network.

  PHASE_SECONDS  seconds per phase (default 90; 0 = manual, advance via /next)
  Control (port 80): GET /state  -> current phase and expected open ports
                     GET /next   -> switch to the next phase now
"""

from __future__ import annotations

import asyncio
import json
import os
import time

PHASE_SECONDS = int(os.environ.get("PHASE_SECONDS", "90"))
# Where the changing services listen, and where the control page (/state, /next) listens.
# Running natively on a laptop: SERVICE_HOST=0.0.0.0 CONTROL_HOST=127.0.0.1 CONTROL_PORT=18766
SERVICE_HOST = os.environ.get("SERVICE_HOST", "0.0.0.0")
CONTROL_HOST = os.environ.get("CONTROL_HOST", "0.0.0.0")
CONTROL_PORT = int(os.environ.get("CONTROL_PORT", "80"))
# Move a lab port when the host already uses it, e.g. PORT_REMAP="8080=8088,21=2121".
REMAP = {
    int(src): int(dst)
    for src, dst in (item.split("=", 1) for item in os.environ.get("PORT_REMAP", "").split(",") if "=" in item)
}


def real(port: int) -> int:
    return REMAP.get(port, port)

# Each phase: port -> service definition. Ports missing from a phase are closed.
WEB_V1 = {"kind": "http", "server": "nginx/1.24.0", "title": "Shop v1", "headers": {
    "X-Powered-By": "PHP/8.1.2", "X-Debug-Token": "a1b2c3d4", "X-Request-Id": "req-1001",
    "Set-Cookie": "PHPSESSID=abc123; path=/", "X-Backend-Server": "app-01.internal"}}
WEB_V2 = {"kind": "http", "server": "Apache/2.4.58 (Ubuntu)", "title": "Shop v2", "headers": {
    "X-Powered-By": "PHP/8.3.0", "Via": "1.1 varnish", "Access-Control-Allow-Origin": "*",
    "X-Backend-Server": "app-02.internal", "Server-Timing": "db;dur=53"}}
LEGACY = {"kind": "http", "server": "Apache/2.2.15 (CentOS)", "title": "Legacy intranet", "headers": {
    "X-AspNet-Version": "2.0.50727", "X-Powered-By": "ASP.NET", "X-Pad": "avoid browser bug"}}
ADMIN = {"kind": "http", "server": "nginx/1.25.3", "title": "Staging Admin Login",
         "headers": {"Set-Cookie": "PHPSESSID=demo; path=/; HttpOnly",
                     "X-Generator": "StagingCMS 0.9", "WWW-Authenticate": "Basic realm=\"admin\"",
                     "X-Runtime": "0.123", "X-Robots-Tag": "noindex"}, "path_hint": "/admin"}
SSH_OLD = {"kind": "banner", "banner": "SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.1\r\n"}
SSH_NEW = {"kind": "banner", "banner": "SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13\r\n"}
FTP_OLD = {"kind": "banner", "banner": "220 (vsFTPd 2.3.4)\r\n"}

PHASES = [
    {"name": "A baseline", "ports": {8080: WEB_V1, 2222: SSH_OLD, 8787: LEGACY, 9000: WEB_V1}},
    {"name": "B changes", "note": "8787 and 9000 gone, 8080 changed server/title, NEW staging admin on 5000",
     "ports": {8080: WEB_V2, 2222: SSH_OLD, 5000: ADMIN}},
    {"name": "C returns", "note": "8787 back (flaky), SSH version changed, 9000 back",
     "ports": {8080: WEB_V2, 2222: SSH_NEW, 8787: LEGACY, 5000: ADMIN, 9000: WEB_V1}},
    {"name": "D exposure", "note": "old FTP appears on 21, 9000 gone again, admin panel removed",
     "ports": {8080: WEB_V1, 2222: SSH_NEW, 8787: LEGACY, 21: FTP_OLD}},
]

state = {"index": 0, "since": time.time()}
servers: dict[int, asyncio.base_events.Server] = {}


def http_response(service: dict, path: str) -> bytes:
    title = service["title"]
    body = (
        f"<!doctype html><html><head><title>{title}</title></head>"
        f"<body><h1>{title}</h1><footer>Powered by {service['server']}</footer></body></html>"
    ).encode()
    lines = [
        "HTTP/1.1 200 OK",
        f"Server: {service['server']}",
        "Content-Type: text/html; charset=utf-8",
        f"Content-Length: {len(body)}",
        "Connection: close",
    ] + [f"{key}: {value}" for key, value in service.get("headers", {}).items()]
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


async def handle(port: int, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    service = PHASES[state["index"]]["ports"].get(port)
    try:
        if service and service["kind"] == "banner":
            writer.write(service["banner"].encode())
        elif service:
            request = await asyncio.wait_for(reader.read(2048), timeout=5)
            path = request.split(b" ")[1].decode(errors="replace") if b" " in request else "/"
            writer.write(http_response(service, path))
        await writer.drain()
    except Exception:  # noqa: BLE001 - scanners send all kinds of probes
        pass
    finally:
        writer.close()


async def apply_phase() -> None:
    wanted = set(PHASES[state["index"]]["ports"])
    for port in list(servers):
        if port not in wanted:
            servers.pop(port).close()
    for port in wanted - set(servers):
        servers[port] = await asyncio.start_server(lambda r, w, p=port: handle(p, r, w), SERVICE_HOST, real(port))
    phase = PHASES[state["index"]]
    print(f"[{time.strftime('%H:%M:%S')}] phase {phase['name']}: open {sorted(real(p) for p in wanted)}", flush=True)


def describe() -> dict:
    phase = PHASES[state["index"]]
    remaining = None
    if PHASE_SECONDS > 0:
        remaining = max(0, int(PHASE_SECONDS - (time.time() - state["since"])))
    return {
        "phase": phase["name"],
        "note": phase.get("note", ""),
        "open_ports": sorted(real(p) for p in phase["ports"]),
        "next_phase_in_seconds": remaining,
        "phases": [{"name": p["name"], "open_ports": sorted(real(x) for x in p["ports"])} for p in PHASES],
    }


async def next_phase() -> None:
    state["index"] = (state["index"] + 1) % len(PHASES)
    state["since"] = time.time()
    await apply_phase()


async def control(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        request = await asyncio.wait_for(reader.read(2048), timeout=5)
        path = request.split(b" ")[1].decode(errors="replace") if b" " in request else "/"
        if path == "/next":
            await next_phase()
        body = json.dumps(describe(), indent=2).encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\nServer: surfacex-demo-lab\r\nContent-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
            + body
        )
        await writer.drain()
    except Exception:  # noqa: BLE001
        pass
    finally:
        writer.close()


async def main() -> None:
    await asyncio.start_server(control, CONTROL_HOST, CONTROL_PORT)
    await apply_phase()
    while True:
        await asyncio.sleep(1)
        if PHASE_SECONDS > 0 and time.time() - state["since"] >= PHASE_SECONDS:
            await next_phase()


if __name__ == "__main__":
    asyncio.run(main())
