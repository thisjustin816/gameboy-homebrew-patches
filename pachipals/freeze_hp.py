#!/usr/bin/env python3
"""Disable damage in two known experimental ROMs without changing native physics."""

import argparse
import hashlib
import json
from pathlib import Path


PROFILES_PATH = Path(__file__).with_name("profiles.json")


def file_offset(bank, address):
    if not 1 <= bank <= 0x1FF or not 0x4000 <= address < 0x8000:
        raise ValueError("Expected a switchable ROM bank and address")
    return bank * 0x4000 + address - 0x4000


def identity(data):
    return {"sha256": hashlib.sha256(data).hexdigest(),
            "md5": hashlib.md5(data).hexdigest()}


def fix_global_checksum(data):
    checksum = (sum(data[:0x14E]) + sum(data[0x150:])) & 0xFFFF
    data[0x14E:0x150] = checksum.to_bytes(2, "big")


def apply_edits(data, sites):
    """Validate every context before changing a copy; allocate no ROM space."""
    if len(data) < 0x150:
        raise ValueError("Truncated cartridge header")
    edits = []
    occupied = set()
    for site in sites:
        start = file_offset(int(site["bank"], 16), int(site["context_address"], 16))
        context = bytes.fromhex(site["context_before"])
        if data[start:start + len(context)] != context:
            raise ValueError(f"Original-byte assertion failed: {site['name']}")
        offset = file_offset(int(site["bank"], 16), int(site["address"], 16))
        before = bytes.fromhex(site["before"])
        after = bytes.fromhex(site["after"])
        if not before or len(before) != len(after):
            raise ValueError("Edits must preserve length")
        if not start <= offset or offset + len(before) > start + len(context):
            raise ValueError("Edit must lie inside its asserted context")
        if data[offset:offset + len(before)] != before:
            raise ValueError(f"Original operand assertion failed: {site['name']}")
        addresses = set(range(offset, offset + len(before)))
        if addresses & occupied or addresses & {0x14E, 0x14F}:
            raise ValueError("Overlapping edit")
        occupied.update(addresses)
        edits.append((offset, after))
    result = bytearray(data)
    for offset, after in edits:
        result[offset:offset + len(after)] = after
    fix_global_checksum(result)
    allowed = occupied | {0x14E, 0x14F}
    if len(result) != len(data) or any(
        a != b and i not in allowed for i, (a, b) in enumerate(zip(data, result))
    ):
        raise ValueError("Unexpected change outside patch sites")
    return bytes(result)


def freeze_hp(data):
    profiles = json.loads(PROFILES_PATH.read_text())
    actual = identity(data)
    matches = [p for p in profiles["inputs"]
               if all(actual[k] == p[k] for k in ("sha256", "md5"))]
    if len(matches) != 1:
        raise ValueError(f"Unsupported ROM: {actual}")
    result = apply_edits(data, profiles["sites"])
    expected = matches[0].get("expected_output_sha256")
    if expected and identity(result)["sha256"] != expected:
        raise ValueError("Output SHA-256 does not match recorded build")
    return result, matches[0]["name"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Use a separate output file")
    try:
        patched, profile = freeze_hp(args.input.read_bytes())
        # Exclusive creation protects an existing ROM or other artifact.
        with args.output.open("xb") as output:
            output.write(patched)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps({"input_profile": profile, "output": identity(patched)}, indent=2))


if __name__ == "__main__":
    main()
