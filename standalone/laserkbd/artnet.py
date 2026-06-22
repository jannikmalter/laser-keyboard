"""Minimal Art-Net implementation: ArtDMX output plus ArtPoll discovery.

We hand-roll the packets (they're small and well-specified) rather than take a
dependency, which also gives us ArtPollReply parsing for the web-UI device picker.
Reference: Art-Net 4 spec, opcodes ArtDMX=0x5000, ArtPoll=0x2000, ArtPollReply=0x2100.
"""

from __future__ import annotations

import logging
import socket
import struct

log = logging.getLogger(__name__)

ARTNET_ID = b"Art-Net\x00"
OP_DMX = 0x5000
OP_POLL = 0x2000
OP_POLL_REPLY = 0x2100
PROTOCOL_VERSION = 14
DEFAULT_PORT = 6454


def build_artdmx(universe: int, data: bytes, sequence: int = 0) -> bytes:
    """Build an ArtDMX packet. `data` length should be even, 2..512 bytes."""
    length = len(data)
    sub_uni = universe & 0xFF
    net = (universe >> 8) & 0x7F
    header = ARTNET_ID + struct.pack(
        "<HBBBBBB",
        OP_DMX,            # OpCode (little-endian)
        0, PROTOCOL_VERSION,  # ProtVerHi, ProtVerLo
        sequence & 0xFF,   # Sequence (0 = disabled)
        0,                 # Physical
        sub_uni,           # SubUni (low byte of universe)
        net,               # Net (high byte)
    ) + struct.pack(">H", length)  # Length is big-endian
    return header + data


def build_artpoll() -> bytes:
    return ARTNET_ID + struct.pack(
        "<HBBBB",
        OP_POLL,
        0, PROTOCOL_VERSION,
        0,   # TalkToMe
        0,   # Priority
    )


class ArtNetSender:
    """Sends ArtDMX frames to a broadcast address or a specific unicast IP."""

    def __init__(self, port: int = DEFAULT_PORT):
        self._port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sequence = 1

    def send(self, target_ip: str, universe: int, data: bytes) -> None:
        packet = build_artdmx(universe, data, self._sequence)
        self._sequence = 1 if self._sequence >= 255 else self._sequence + 1
        try:
            self._sock.sendto(packet, (target_ip, self._port))
        except OSError as exc:
            log.warning("ArtNet send to %s failed: %s", target_ip, exc)

    def close(self) -> None:
        self._sock.close()


def discover_nodes(timeout: float = 2.0, port: int = DEFAULT_PORT) -> list[dict]:
    """Broadcast an ArtPoll and collect ArtPollReply packets for `timeout` seconds.

    Returns a list of {ip, short_name, long_name} dicts for the web-UI picker.
    Note: reliable only when the Pi shares a subnet/interface with the nodes.
    """
    found: dict[str, dict] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.bind(("", port))
        sock.settimeout(timeout)
        sock.sendto(build_artpoll(), ("255.255.255.255", port))
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                sock.settimeout(max(0.0, deadline - time.monotonic()))
                packet, addr = sock.recvfrom(1024)
            except socket.timeout:
                break
            reply = _parse_poll_reply(packet, addr[0])
            if reply:
                found[reply["ip"]] = reply
    except OSError as exc:
        log.warning("ArtPoll discovery failed: %s", exc)
    finally:
        sock.close()
    return sorted(found.values(), key=lambda r: r["ip"])


def _parse_poll_reply(packet: bytes, src_ip: str) -> dict | None:
    if len(packet) < 26 or packet[:8] != ARTNET_ID:
        return None
    opcode = struct.unpack_from("<H", packet, 8)[0]
    if opcode != OP_POLL_REPLY:
        return None
    # IP address is at offset 10 (4 bytes); fall back to packet source if zeroed.
    ip_bytes = packet[10:14]
    ip = ".".join(str(b) for b in ip_bytes) if any(ip_bytes) else src_ip
    short_name = _read_cstr(packet, 26, 18)
    long_name = _read_cstr(packet, 44, 64)
    return {"ip": ip, "short_name": short_name, "long_name": long_name}


def _read_cstr(packet: bytes, offset: int, length: int) -> str:
    if offset >= len(packet):
        return ""
    chunk = packet[offset:offset + length]
    return chunk.split(b"\x00", 1)[0].decode("latin-1", "replace").strip()
