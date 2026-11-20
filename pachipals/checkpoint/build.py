#!/usr/bin/env python3
"""Reproduce fixed October 27 checkpoint profiles from the pristine ROM."""

import argparse
import hashlib
import json
from pathlib import Path

PROFILES = json.loads(Path(__file__).with_name("profiles.json").read_text())


def identity(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "md5": hashlib.md5(data).hexdigest()}


def checksum(data):
    result = bytearray(data)
    total = (sum(result[:0x14E]) + sum(result[0x150:])) & 0xFFFF
    result[0x14E:0x150] = total.to_bytes(2, "big")
    return bytes(result)


def build(stock, name):
    if identity(stock) != PROFILES["input"]:
        raise ValueError("Unsupported pristine ROM")
    profile = PROFILES["profiles"][name]
    result = bytearray(stock)
    allowed = {0x14E, 0x14F}
    for edit in profile["edits"]:
        offset = edit["offset"]
        before, after = bytes.fromhex(edit["before"]), bytes.fromhex(edit["after"])
        if len(before) != len(after) or stock[offset:offset + len(before)] != before:
            raise ValueError(f"Original-byte assertion failed: {edit['name']}")
        addresses = set(range(offset, offset + len(before)))
        if addresses & allowed:
            raise ValueError("Overlapping patch sites")
        allowed.update(addresses)
        result[offset:offset + len(after)] = after
    result = checksum(result)
    if len(result) != len(stock) or any(
        a != b and i not in allowed for i, (a, b) in enumerate(zip(stock, result))
    ):
        raise ValueError("Changes outside asserted sites")
    if identity(result) != {k: profile[k] for k in ("sha256", "md5")}:
        raise ValueError("Output does not match archived checkpoint")
    return result


def build_control(stock, name):
    if identity(stock) != PROFILES["input"]:
        raise ValueError("Unsupported pristine ROM")
    if name == "pinball-pre-tipfit":
        result = bytearray(build(stock, "pinball-tipfit"))
        for offset in (0x1950A, 0x19647):
            if result[offset] != 0:
                raise ValueError("TipFit control-byte assertion failed")
            result[offset] = 1
    elif name == "capture-stock":
        result = bytearray(stock)
        boot = next(e for e in PROFILES["profiles"]["pinball-tipfit"]["edits"]
                    if e["name"] == "direct-start")
        offset = boot["offset"]
        before, after = bytes.fromhex(boot["before"]), bytes.fromhex(boot["after"])
        if result[offset:offset + len(before)] != before:
            raise ValueError("Boot control-byte assertion failed")
        result[offset:offset + len(after)] = after
    else:
        raise ValueError("Unknown control")
    result = checksum(result)
    if identity(result) != PROFILES["controls"][name]:
        raise ValueError("Control identity mismatch")
    return result


def restore(data, name):
    profile = PROFILES["profiles"][name]
    if identity(data) != {k: profile[k] for k in ("sha256", "md5")}:
        raise ValueError("Unsupported checkpoint output")
    result = bytearray(data)
    for edit in profile["edits"]:
        offset = edit["offset"]
        before, after = bytes.fromhex(edit["before"]), bytes.fromhex(edit["after"])
        if result[offset:offset + len(after)] != after:
            raise ValueError(f"Patched-byte assertion failed: {edit['name']}")
        result[offset:offset + len(before)] = before
    result = checksum(result)
    if identity(result) != PROFILES["input"]:
        raise ValueError("Restoration does not match pristine ROM")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=PROFILES["profiles"])
    parser.add_argument("stock", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = build(args.stock.read_bytes(), args.profile)
        with args.output.open("xb") as output:
            output.write(result)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(identity(result), indent=2))


if __name__ == "__main__":
    main()
