from __future__ import annotations

from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import threading
from typing import Any, Literal

import httpx


MultiplayerRole = Literal["host", "client"]


def normalize_base_url(base_url: str) -> str:
    value = base_url.strip()
    if not value:
        raise ValueError("base_url is empty")
    if "://" not in value:
        value = f"http://{value}"
    return value.rstrip("/")


def cells_payload_to_sets(payload: list[list[list[int]]]) -> list[set[tuple[int, int]]]:
    ships: list[set[tuple[int, int]]] = []
    for ship_payload in payload:
        ships.append({(row, col) for row, col in ship_payload})
    return ships


def sets_to_cells_payload(ships: list[set[tuple[int, int]]]) -> list[list[list[int]]]:
    payload: list[list[list[int]]] = []
    for ship in ships:
        payload.append([[row, col] for row, col in sorted(ship)])
    return payload


@dataclass
class MultiplayerSessionState:
    host_connected: bool = True
    client_connected: bool = False
    host_ready: bool = False
    client_ready: bool = False
    host_ships: list[set[tuple[int, int]]] = field(default_factory=list)
    client_ships: list[set[tuple[int, int]]] = field(default_factory=list)
    host_hits: set[tuple[int, int]] = field(default_factory=set)
    host_misses: set[tuple[int, int]] = field(default_factory=set)
    client_hits: set[tuple[int, int]] = field(default_factory=set)
    client_misses: set[tuple[int, int]] = field(default_factory=set)
    turn_role: MultiplayerRole = "host"
    winner_role: MultiplayerRole | None = None
    message: str = "Waiting for client to join"

    def phase(self) -> str:
        if self.winner_role is not None:
            return "finished"
        if not self.client_connected:
            return "waiting_for_join"
        if self.host_ready and self.client_ready:
            return "battle"
        return "setup"

    def battle_ready(self) -> bool:
        return self.client_connected and self.host_ready and self.client_ready and self.winner_role is None

    def snapshot(self) -> dict[str, Any]:
        return {
            "phase": self.phase(),
            "host_connected": self.host_connected,
            "client_connected": self.client_connected,
            "host_ready": self.host_ready,
            "client_ready": self.client_ready,
            "host_ships": sets_to_cells_payload(self.host_ships),
            "client_ships": sets_to_cells_payload(self.client_ships),
            "host_hits": [[row, col] for row, col in sorted(self.host_hits)],
            "host_misses": [[row, col] for row, col in sorted(self.host_misses)],
            "client_hits": [[row, col] for row, col in sorted(self.client_hits)],
            "client_misses": [[row, col] for row, col in sorted(self.client_misses)],
            "turn_role": self.turn_role,
            "winner_role": self.winner_role,
            "message": self.message,
        }


class MultiplayerGameServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], RequestHandlerClass: type[BaseHTTPRequestHandler]):
        super().__init__(server_address, RequestHandlerClass)
        self.state = MultiplayerSessionState()
        self.state_lock = threading.Lock()


class MultiplayerRequestHandler(BaseHTTPRequestHandler):
    server: MultiplayerGameServer

    def do_GET(self) -> None:
        if self.path == "/state":
            self._write_json(self.server.state.snapshot())
            return
        if self.path == "/health":
            self._write_json({"ok": True})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "invalid json")
            return

        if self.path == "/join":
            with self.server.state_lock:
                self.server.state.client_connected = True
                if not self.server.state.host_ready and not self.server.state.client_ready:
                    self.server.state.message = "Both players connected. Place your ships"
                elif self.server.state.host_ready and not self.server.state.client_ready:
                    self.server.state.message = "Client connected. Place your ships"
                else:
                    self.server.state.message = "Client connected"
                snapshot = self.server.state.snapshot()
            self._write_json(snapshot)
            return

        if self.path == "/setup":
            role = self._normalize_role(payload.get("role"))
            ships_payload = payload.get("ships")
            if not isinstance(ships_payload, list):
                self.send_error(HTTPStatus.BAD_REQUEST, "ships must be a list")
                return

            ships = cells_payload_to_sets(ships_payload)
            with self.server.state_lock:
                self._apply_setup(role, ships)
                snapshot = self.server.state.snapshot()
            self._write_json(snapshot)
            return

        if self.path == "/shot":
            role = self._normalize_role(payload.get("role"))
            row = payload.get("row")
            col = payload.get("col")
            if not isinstance(row, int) or not isinstance(col, int):
                self.send_error(HTTPStatus.BAD_REQUEST, "row and col must be integers")
                return

            with self.server.state_lock:
                result = self._apply_shot(role, row, col)
                if result is None:
                    self.send_error(HTTPStatus.CONFLICT, "shot rejected")
                    return
                self._write_json(result)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        if not raw:
            return {}
        decoded = raw.decode("utf-8")
        return json.loads(decoded)

    def _write_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _normalize_role(self, value: Any) -> MultiplayerRole:
        if value not in {"host", "client"}:
            raise ValueError("invalid role")
        return value

    def _apply_setup(self, role: MultiplayerRole, ships: list[set[tuple[int, int]]]) -> None:
        state = self.server.state
        if state.phase() in {"battle", "finished"}:
            return

        if role == "host":
            state.host_ready = True
            state.host_ships = ships
        else:
            state.client_connected = True
            state.client_ready = True
            state.client_ships = ships

        if state.client_connected and state.host_ready and state.client_ready and state.winner_role is None:
            state.turn_role = "host"
            state.message = "Battle started. Host turn"
        elif state.client_connected:
            if role == "host":
                state.message = "Host ready. Waiting for client"
            else:
                state.message = "Client ready. Waiting for host"
        else:
            state.message = "Waiting for client to join"

    def _apply_shot(self, role: MultiplayerRole, row: int, col: int) -> dict[str, Any] | None:
        state = self.server.state
        if not state.battle_ready() or state.turn_role != role or state.winner_role is not None:
            return None

        shooter_hits, shooter_misses, target_ships, target_role = self._shot_state(role)
        cell = (row, col)
        if cell in shooter_hits or cell in shooter_misses:
            return None

        if cell in self._all_ship_cells(target_ships):
            shooter_hits.add(cell)
            sunk = self._ship_sunk(target_ships, cell, shooter_hits)
            if self._all_ships_sunk(target_ships, shooter_hits):
                state.winner_role = role
                state.message = f"{role.title()} wins"
            else:
                state.message = f"{role.title()} hit. Extra turn"
                if sunk:
                    state.message = f"{role.title()} sunk a ship. Extra turn"
            if state.winner_role is None:
                state.turn_role = role
            return state.snapshot()

        shooter_misses.add(cell)
        state.turn_role = target_role
        state.message = f"{role.title()} missed. {target_role.title()} turn"
        return state.snapshot()

    def _shot_state(
        self,
        role: MultiplayerRole,
    ) -> tuple[set[tuple[int, int]], set[tuple[int, int]], list[set[tuple[int, int]]], MultiplayerRole]:
        state = self.server.state
        if role == "host":
            return state.host_hits, state.host_misses, state.client_ships, "client"
        return state.client_hits, state.client_misses, state.host_ships, "host"

    def _all_ship_cells(self, ships: list[set[tuple[int, int]]]) -> set[tuple[int, int]]:
        cells: set[tuple[int, int]] = set()
        for ship in ships:
            cells.update(ship)
        return cells

    def _ship_sunk(
        self,
        ships: list[set[tuple[int, int]]],
        hit_cell: tuple[int, int],
        hits: set[tuple[int, int]],
    ) -> bool:
        for ship in ships:
            if hit_cell in ship:
                return ship.issubset(hits)
        return False

    def _all_ships_sunk(self, ships: list[set[tuple[int, int]]], hits: set[tuple[int, int]]) -> bool:
        return all(ship.issubset(hits) for ship in ships)


@dataclass
class MultiplayerServerHandle:
    server: MultiplayerGameServer
    thread: threading.Thread
    base_url: str
    advertised_url: str

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1.0)


def start_multiplayer_server(host: str = "127.0.0.1", port: int = 8765) -> MultiplayerServerHandle:
    server = MultiplayerGameServer(("0.0.0.0", port), MultiplayerRequestHandler)
    thread = threading.Thread(target=server.serve_forever, name="multiplayer-server", daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    advertised_url = f"http://{_detect_local_ip_address()}:{port}"
    return MultiplayerServerHandle(server=server, thread=thread, base_url=base_url, advertised_url=advertised_url)


@dataclass
class MultiplayerClient:
    base_url: str
    timeout_seconds: float = 1.0

    def __post_init__(self) -> None:
        self.base_url = normalize_base_url(self.base_url)
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def join(self) -> dict[str, Any]:
        return self._request_json("POST", "/join", {"role": "client"})

    def state(self) -> dict[str, Any]:
        response = self._client.get("/state")
        response.raise_for_status()
        return response.json()

    def submit_setup(self, role: MultiplayerRole, ships: list[set[tuple[int, int]]]) -> dict[str, Any]:
        return self._request_json("POST", "/setup", {"role": role, "ships": sets_to_cells_payload(ships)})

    def submit_shot(self, role: MultiplayerRole, row: int, col: int) -> dict[str, Any]:
        return self._request_json("POST", "/shot", {"role": role, "row": row, "col": col})

    def _request_json(self, method: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.request(method, path, json=payload)
        response.raise_for_status()
        return response.json()


def payload_to_ship_sets(payload: list[list[list[int]]]) -> list[set[tuple[int, int]]]:
    return cells_payload_to_sets(payload)


def _detect_local_ip_address() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
