#!/usr/bin/env python3
"""Reads a provider's status from T3's local server, with the read-only token that setup issued.

T3 keeps the sign-in state of each provider, Antigravity's included, and tells it to a client over its own protocol.
The client trades the token for a ticket at `/api/auth/websocket-ticket/rpc`, opens `/ws?orchestrationProtocol=2&
wsTicket=<ticket>` and calls `server.getConfig`, whose reply lists the providers (ADR 0011). Python's standard
library has no websocket client and jidoka installs no packages, so this module carries a minimal one: the HTTP
upgrade, masked text frames out, text frames in, ping and close, and no extensions.

A caller with no --port, the beater, takes the port from $JIDOKA_T3_PORT, else 3773.

The protocol is T3's private one. Anything that does not match it, a refused ticket, a socket T3 closed, a reply
of another shape or no reply in time, is no status: `read_antigravity_status` raises NoStatus, and the command
exits 1. No reason ever holds the token or the ticket.

  provider_status.py antigravity [--jidoka-home <folder>] [--port <port>] [--timeout <seconds>]
      Prints `The Antigravity account is signed in.` or `The Antigravity account is signed out.` and exits 0.

Exit codes:
  0  the status was read.
  1  no status, with the reason on stderr.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

import routes
import settings_reader
import t3_token

T3_HOST = "127.0.0.1"
DEFAULT_PORT = 3773
PORT_VARIABLE = "JIDOKA_T3_PORT"
DEFAULT_TIMEOUT_SECONDS = 20
TICKET_PATH = "/api/auth/websocket-ticket/rpc"
SOCKET_PATH = "/ws"
ORCHESTRATION_PROTOCOL = "2"
CONFIG_CALL = "server.getConfig"
ANTIGRAVITY = routes.ANTIGRAVITY_DRIVER
SIGNED_IN = "authenticated"
SIGNED_OUT = "unauthenticated"
HANDSHAKE_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_HEADER_BYTES = 65536
MAX_PAYLOAD_BYTES = 8 * 1024 * 1024
CONTINUATION, TEXT, BINARY, CLOSE, PING, PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA
NORMAL_CLOSURE = 1000


def port_of_environment() -> int:
    """The port $JIDOKA_T3_PORT names, else T3's own, for a caller that has no --port to read."""
    held = os.environ.get(PORT_VARIABLE, "").strip()
    return int(held) if held.isdigit() and 0 < int(held) < 65536 else DEFAULT_PORT


class NoStatus(Exception):
    """T3 gave no status. The reason says what happened, worded for the person who reads stderr; it never holds the
    token or the ticket."""


class WebSocketError(Exception):
    """A websocket that cannot go on: T3 closed it, broke the protocol or ran out the time."""


@dataclass(frozen=True)
class ProviderStatus:
    """Whether the account of one provider is signed in at T3."""
    signed_in: bool


class WebSocket:
    """One client connection: the upgrade is done when it is built. It sends masked text frames and returns the text
    frames it receives, answers a ping with a pong, and takes no extension, so a frame with a reserved bit set breaks
    the connection."""

    def __init__(self, connection: socket.socket, deadline: float):
        self.connection = connection
        self.stream = connection.makefile("rb")
        self.deadline = deadline

    @classmethod
    def open(cls, host: str, port: int, target: str, deadline: float) -> "WebSocket":
        connection = socket.create_connection((host, port), timeout=remaining(deadline))
        client = cls(connection, deadline)
        try:
            client.upgrade(host, port, target)
        except Exception:
            client.drop()
            raise
        return client

    def upgrade(self, host: str, port: int, target: str) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        self.connection.sendall((f"GET {target} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                                 f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                                 "Sec-WebSocket-Version: 13\r\n\r\n").encode("ascii"))
        status = self.read_line()
        if status.split(" ")[1:2] != ["101"]:
            raise WebSocketError("T3 refused to open the socket")
        headers: dict[str, str] = {}
        received = len(status)
        while True:
            line = self.read_line()
            received += len(line)
            if received > MAX_HEADER_BYTES:
                raise WebSocketError("T3's upgrade reply is too long")
            if not line:
                break
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        accepted = base64.b64encode(hashlib.sha1((key + HANDSHAKE_GUID).encode("ascii")).digest()).decode("ascii")
        if headers.get("sec-websocket-accept") != accepted:
            raise WebSocketError("T3's upgrade reply does not answer the key")

    def read_line(self) -> str:
        self.connection.settimeout(remaining(self.deadline))
        line = self.stream.readline(MAX_HEADER_BYTES)
        if not line.endswith(b"\n"):
            raise WebSocketError("T3 closed the socket during the upgrade")
        return line.decode("latin-1").rstrip("\r\n")

    def read_exactly(self, count: int) -> bytes:
        self.connection.settimeout(remaining(self.deadline))
        held = self.stream.read(count)
        if len(held) < count:
            raise WebSocketError("T3 closed the socket")
        return held

    def send_frame(self, opcode: int, payload: bytes) -> None:
        length = len(payload)
        if length < 126:
            head = struct.pack("!BB", 0x80 | opcode, 0x80 | length)
        elif length < 65536:
            head = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, length)
        else:
            head = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, length)
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.connection.settimeout(remaining(self.deadline))
        self.connection.sendall(head + mask + masked)

    def send_text(self, text: str) -> None:
        self.send_frame(TEXT, text.encode("utf-8"))

    def read_frame(self) -> tuple[bool, int, bytes]:
        first, second = self.read_exactly(2)
        if first & 0x70:
            raise WebSocketError("T3 used a websocket extension")
        length = second & 0x7F
        if length == 126:
            length = struct.unpack("!H", self.read_exactly(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self.read_exactly(8))[0]
        if length > MAX_PAYLOAD_BYTES:
            raise WebSocketError("T3 sent a frame that is too large")
        mask = self.read_exactly(4) if second & 0x80 else b""
        payload = self.read_exactly(length)
        if mask:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        return bool(first & 0x80), first & 0x0F, payload

    def receive_text(self) -> str:
        """The next text message, whole. A ping is answered and a pong is skipped on the way; a close frame, a binary
        message or a broken fragment raises."""
        collected = b""
        collecting = False
        while True:
            final, opcode, payload = self.read_frame()
            if opcode == PING:
                self.send_frame(PONG, payload)
            elif opcode == PONG:
                continue
            elif opcode == CLOSE:
                self.answer_close(payload)
                raise WebSocketError("T3 closed the socket")
            elif opcode == TEXT and not collecting or opcode == CONTINUATION and collecting:
                collected += payload
                collecting = not final
                if final:
                    try:
                        return collected.decode("utf-8")
                    except UnicodeDecodeError as error:
                        raise WebSocketError("T3 sent text that is not UTF-8") from error
            else:
                raise WebSocketError("T3 sent a frame the client does not read")

    def answer_close(self, payload: bytes) -> None:
        try:
            self.send_frame(CLOSE, payload[:2])
        except OSError:
            pass

    def close(self) -> None:
        """Sends a close frame, as a polite client does, and drops the connection."""
        try:
            self.send_frame(CLOSE, struct.pack("!H", NORMAL_CLOSURE))
        except OSError:
            pass
        self.drop()

    def drop(self) -> None:
        self.stream.close()
        self.connection.close()


def remaining(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise WebSocketError("T3 did not answer in time")
    return left


def ticket_for(token: str, port: int, deadline: float) -> str:
    """The ticket T3 gives for the token. A refusal, an unreachable server and a reply without a ticket raise."""
    request = urllib.request.Request(f"http://{T3_HOST}:{port}{TICKET_PATH}", data=b"{}", method="POST",
                                     headers={"Authorization": f"Bearer {token}",
                                              "Content-Type": "application/json"})
    direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with direct.open(request, timeout=remaining(deadline)) as reply:
            held = json.loads(reply.read(MAX_HEADER_BYTES))
    except urllib.error.HTTPError as error:
        raise WebSocketError(f"T3 refused the token with {error.code}") from error
    except (OSError, ValueError, urllib.error.URLError) as error:
        raise WebSocketError(f"T3 gave no ticket ({type(error).__name__})") from error
    ticket = held.get("ticket") if isinstance(held, dict) else None
    if not isinstance(ticket, str) or not ticket:
        raise WebSocketError("T3's ticket reply holds no ticket")
    return ticket


def call(port: int, ticket: str, name: str, deadline: float) -> object:
    """The value that T3 answers to one call of its protocol, made over a socket that the ticket opens."""
    target = f"{SOCKET_PATH}?orchestrationProtocol={ORCHESTRATION_PROTOCOL}&wsTicket={ticket}"
    client = WebSocket.open(T3_HOST, port, target, deadline)
    try:
        identifier = "1"
        client.send_text(json.dumps({"_tag": "Request", "id": identifier, "tag": name, "payload": {},
                                     "headers": []}))
        while True:
            try:
                message = json.loads(client.receive_text())
            except ValueError as error:
                raise WebSocketError("T3 sent a reply that is not JSON") from error
            if not isinstance(message, dict) or "_tag" not in message:
                raise WebSocketError("T3 sent a reply of an unknown shape")
            if message["_tag"] != "Exit" or message.get("requestId") != identifier:
                continue
            outcome = message.get("exit")
            if not isinstance(outcome, dict) or outcome.get("_tag") != "Success" or "value" not in outcome:
                raise WebSocketError(f"T3 failed the {name} call")
            return outcome["value"]
    finally:
        client.close()


def driver_of(entry: dict) -> object:
    for key in ("driverKind", "driver", "provider"):
        if key in entry:
            return entry[key]
    return None


def antigravity_status(config: object) -> ProviderStatus:
    """The status of the Antigravity provider in what `server.getConfig` returned. A config with no such provider,
    and an auth state other than signed in or signed out, are no status."""
    providers = config.get("providers") if isinstance(config, dict) else None
    for entry in providers if isinstance(providers, list) else []:
        if isinstance(entry, dict) and driver_of(entry) == ANTIGRAVITY:
            auth = entry.get("auth")
            state = auth.get("status") if isinstance(auth, dict) else None
            if state in (SIGNED_IN, SIGNED_OUT):
                return ProviderStatus(state == SIGNED_IN)
            raise NoStatus("T3 reports no sign-in state for the Antigravity provider")
    raise NoStatus("T3 lists no Antigravity provider")


def read_antigravity_status(token: str, port: int, timeout_seconds: float) -> ProviderStatus:
    """The Antigravity provider's status at the T3 server on the port, within the timeout. It raises NoStatus when T3
    refuses the token, closes the socket, answers with anything other than a config, or runs out the time."""
    deadline = time.monotonic() + timeout_seconds
    try:
        ticket = ticket_for(token, port, deadline)
        return antigravity_status(call(port, ticket, CONFIG_CALL, deadline))
    except (WebSocketError, OSError) as error:
        raise NoStatus(str(error) or type(error).__name__) from error


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="provider_status.py", description="Read a provider's status from T3.")
    modes = parser.add_subparsers(dest="provider", required=True)
    reading = modes.add_parser(ANTIGRAVITY, help="say whether the Antigravity account is signed in")
    reading.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    reading.add_argument("--port", type=int, default=DEFAULT_PORT, help="the port of T3's local server")
    reading.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS,
                         help="seconds to wait for T3, in all")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout needs a number of seconds above zero")
    try:
        home = settings_reader.jidoka_home(args.jidoka_home)
        token = t3_token.read_token(home)
        if token is None:
            raise NoStatus("jidoka holds no T3 token; run /jidoka:setup and confirm the token")
        status = read_antigravity_status(token, args.port, args.timeout)
    except (NoStatus, settings_reader.SettingsError) as error:
        print(f"provider_status: no status: {error}", file=sys.stderr)
        return 1
    print(f"The Antigravity account is signed {'in' if status.signed_in else 'out'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
