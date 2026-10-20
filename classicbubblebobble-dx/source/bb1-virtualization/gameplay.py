"""Shared Gambatte state decoding and BB1 replay input policy."""
import hashlib


def chunks(state):
    if state[:5] != b"\x00\x01\x00\x00\x00":
        raise ValueError("unsupported Gambatte state format")
    result = {}
    offset = 5
    while offset < len(state) and state[offset]:
        end = state.index(0, offset)
        key = state[offset:end].decode("ascii")
        size = int.from_bytes(state[end + 1:end + 4], "big")
        offset = end + 4
        result[key] = state[offset:offset + size]
        offset += size
    return result


def record_digest(ram, groups):
    blocks = []
    for base, count, size in groups:
        for index in range(count):
            record = bytearray(ram[base + index * size:base + (index + 1) * size])
            for offset in (7, 10):
                pointer = int.from_bytes(record[offset:offset + 2], "little")
                if 0x25AA <= pointer < 0x2990:
                    record[offset:offset + 2] = (pointer + 0x4000).to_bytes(2, "little")
            blocks.append(record)
    return hashlib.sha256(b"".join(blocks)).hexdigest()


def buttons(frame, active):
    if not active or frame < 2400:
        return []
    phase = (frame - 2400) % 240
    held = ["RIGHT"] if phase < 80 else ["LEFT"] if phase < 160 else []
    if phase in (16, 17, 96, 97):
        held.append("A")
    if 40 <= phase < 220:
        held.append("B")
    return held
