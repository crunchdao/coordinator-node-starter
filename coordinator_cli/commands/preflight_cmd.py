from __future__ import annotations

import socket
from typing import Iterable

_DEFAULT_PORTS = (3000, 5432, 8000, 9091)


def parse_ports(value: str | None) -> list[int]:
    if value is None or not value.strip():
        return list(_DEFAULT_PORTS)

    ports: list[int] = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        port = int(token)
        if port <= 0 or port > 65535:
            raise ValueError(f"invalid port '{token}'")
        ports.append(port)

    return ports or list(_DEFAULT_PORTS)


def busy_ports(ports: Iterable[int]) -> list[int]:
    busy: list[int] = []
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", int(port))) == 0:
                busy.append(int(port))
    return busy


def run_preflight(ports: list[int]) -> int:
    conflicts = busy_ports(ports)
    if conflicts:
        print("preflight failed: required local ports are busy")
        for port in conflicts:
            print(f"- {port} busy")
        print("Resolve and rerun. Helpful commands:")
        for port in conflicts:
            print(f"  lsof -nP -iTCP:{port} -sTCP:LISTEN")
        print("  # then stop the process or docker compose stack")
        return 1

    print("preflight passed: required ports are available")
    return 0
