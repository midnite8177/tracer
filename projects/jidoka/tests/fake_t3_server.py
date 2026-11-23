"""A fake of T3's local server, enough of it for the provider status client: the websocket ticket route and a /ws that
answers `server.getConfig` over a websocket. It speaks the protocol with plain sockets, so a test of the client
does not lean on the client's own framing code."""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

TICKET_PATH = "/api/auth/websocket-ticket/rpc"
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TICKET = "ticket-of-the-fake"

ANSWER = "answer"
PING_FIRST = "ping first"
CLOSE = "close"
GARBAGE = "garbage"
UNKNOWN_SHAPE = "unknown shape"
FAILURE = "failure"
SILENCE = "silence"


def provider(driver: str, auth_status: str) -> dict:
    return {"instanceId": driver, "driver": driver, "enabled": True, "installed": True, "status": "ready",
            "auth": {"status": auth_status}}


def usage_window(identifier: str, kind: str, used_percent: float, resets_at: str, duration_minutes: int) -> dict:
    return {"id": identifier, "kind": kind, "usedPercent": used_percent, "resetsAt": resets_at,
            "windowDurationMins": duration_minutes}


def antigravity_with_usage(checked_at: str, windows: list[dict]) -> dict:
    """A signed-in Antigravity provider whose `usageLimits` were checked at the ISO time and hold the windows."""
    return {**provider("antigravity", "authenticated"), "usageLimits": {"checkedAt": checked_at, "windows": windows}}


class FakeT3Server:
    """Serves on a free port of 127.0.0.1 from a thread of the test. `token` is the one bearer token the ticket route
    accepts, `providers` is what `server.getConfig` lists, and `on_request` says what /ws does with the request:
    ANSWER, PING_FIRST (a ping, and the answer once the pong came back), CLOSE, GARBAGE (text that is no JSON),
    UNKNOWN_SHAPE (JSON that is no reply), FAILURE (an Exit that failed) or SILENCE."""

    def __init__(self, token: str, providers: list[dict], on_request: str, refuse_ticket: bool):
        self.token = token
        self.providers = providers
        self.on_request = on_request
        self.refuse_ticket = refuse_ticket
        self.bearers: list[str] = []
        self.client_frames: list[tuple[int, bool, bytes]] = []
        self.paths: list[str] = []
        self.closed = threading.Event()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def do_POST(self):
                outer.ticket_route(self)

            def do_GET(self):
                outer.socket_route(self)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeT3Server":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()

    def ticket_route(self, handler: BaseHTTPRequestHandler) -> None:
        self.paths.append(handler.path)
        handler.rfile.read(int(handler.headers.get("Content-Length") or 0))
        bearer = handler.headers.get("Authorization", "")
        self.bearers.append(bearer)
        if handler.path != TICKET_PATH or self.refuse_ticket or bearer != f"Bearer {self.token}":
            self.reply(handler, 401, {"error": "unauthorized"})
        else:
            self.reply(handler, 200, {"ticket": TICKET})

    @staticmethod
    def reply(handler: BaseHTTPRequestHandler, status: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    def socket_route(self, handler: BaseHTTPRequestHandler) -> None:
        self.paths.append(handler.path)
        parsed = urlparse(handler.path)
        query = parse_qs(parsed.query)
        key = handler.headers.get("Sec-WebSocket-Key")
        if (parsed.path != "/ws" or query.get("orchestrationProtocol") != ["2"] or query.get("wsTicket") != [TICKET]
                or key is None or handler.headers.get("Upgrade", "").lower() != "websocket"):
            self.reply(handler, 401, {"error": "unauthorized"})
            return
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")
        handler.wfile.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                             f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode("ascii"))
        handler.wfile.flush()
        handler.close_connection = True
        self.converse(handler)

    def converse(self, handler: BaseHTTPRequestHandler) -> None:
        if self.on_request == CLOSE:
            self.send(handler, 0x8, struct.pack("!H", 1001))
            return
        request = self.next_text(handler, until_pong=False)
        if request is None:
            return
        if self.on_request == SILENCE:
            self.next_text(handler, until_pong=False)
            return
        identifier = json.loads(request).get("id")
        if self.on_request == PING_FIRST:
            self.send(handler, 0x9, b"are you there")
            if self.next_text(handler, until_pong=True) is None:
                return
        body = (b"this is not json" if self.on_request == GARBAGE
                else json.dumps(self.answer(identifier)).encode("utf-8"))
        self.send(handler, 0x1, body)
        self.next_text(handler, until_pong=False)

    def answer(self, identifier: object) -> dict:
        if self.on_request == UNKNOWN_SHAPE:
            return {"hello": "world"}
        if self.on_request == FAILURE:
            return {"_tag": "Exit", "requestId": identifier, "exit": {"_tag": "Failure", "cause": "nope"}}
        return {"_tag": "Exit", "requestId": identifier,
                "exit": {"_tag": "Success", "value": {"providers": self.providers}}}

    def next_text(self, handler: BaseHTTPRequestHandler, until_pong: bool) -> str | None:
        """Reads client frames until a text frame (or, with until_pong, a pong) arrives, and returns the text. It
        returns None when the client closed or went away."""
        while True:
            head = handler.rfile.read(2)
            if len(head) < 2:
                return None
            opcode, masked, length = head[0] & 0x0F, bool(head[1] & 0x80), head[1] & 0x7F
            if length == 126:
                length = struct.unpack("!H", handler.rfile.read(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", handler.rfile.read(8))[0]
            mask = handler.rfile.read(4) if masked else b""
            payload = handler.rfile.read(length)
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            self.client_frames.append((opcode, masked, payload))
            if opcode == 0x8:
                self.closed.set()
                self.send(handler, 0x8, payload[:2])
                return None
            if opcode == 0x1:
                return payload.decode("utf-8")
            if opcode == 0xA and until_pong:
                return ""

    @staticmethod
    def send(handler: BaseHTTPRequestHandler, opcode: int, payload: bytes) -> None:
        length = len(payload)
        head = bytes([0x80 | opcode])
        head += (bytes([length]) if length < 126 else bytes([126]) + struct.pack("!H", length)
                 if length < 65536 else bytes([127]) + struct.pack("!Q", length))
        handler.wfile.write(head + payload)
        handler.wfile.flush()
