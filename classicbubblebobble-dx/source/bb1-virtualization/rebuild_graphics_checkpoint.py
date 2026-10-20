#!/usr/bin/env python3
"""Rebuild the death-sprite fix from the exact saved graphics checkpoint.

This path preserves the saved Classic and BB2 bytes when their input ROMs are
unavailable. Full builds use build.py with all three original patched inputs.
"""
import argparse
import hashlib
from pathlib import Path

import graphics_experiment as builder

CHECKPOINT_MD5 = "617beb54814b87dff60e7b95d0068c09"
CHECKPOINT_HOST_END = 0x2322


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("bb1", type=Path)
    parser.add_argument("--rgbds", type=Path, required=True)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    original = args.checkpoint.read_bytes()
    bb1 = args.bb1.read_bytes()
    if hashlib.md5(original).hexdigest() != CHECKPOINT_MD5:
        parser.error("checkpoint has the wrong MD5")
    if hashlib.md5(bb1).hexdigest() != builder.EXPECTED["bb1"]:
        parser.error("BB1 input has the wrong MD5")
    if args.output.resolve() in (args.checkpoint.resolve(), args.bb1.resolve()):
        parser.error("output must preserve the inputs")
    builder.RGBASM = args.rgbds / "rgbasm"
    builder.RGBLINK = args.rgbds / "rgblink"
    if not builder.RGBASM.is_file() or not builder.RGBLINK.is_file():
        parser.error("--rgbds must contain rgbasm and rgblink")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    builder.BUILD = args.output.parent / (args.output.stem + "-build")
    _, _, back, _ = builder.banked_edges(bb1)
    low_targets = {target for *_, target in back}
    _, _, _, upper, _, _ = builder.discover_bank0(bb1, low_targets)
    host, symbols = builder.assemble_host(
        builder.make_asm({target for _, _, target in upper}, low_targets))
    # Existing entry points and service bytes must retain their exact addresses.
    assert host[builder.HOST_ORG:CHECKPOINT_HOST_END] == original[
        builder.HOST_ORG:CHECKPOINT_HOST_END]
    assert host[:0x61] == original[:0x61]
    assert host[0x100:0x104] == original[0x100:0x104]
    entry = symbols["host_bb1_death_sprite_pointers"]
    assert entry == CHECKPOINT_HOST_END
    assert symbols["host_end"] < builder.HOST_LIMIT
    result = bytearray(original)
    result[builder.HOST_ORG:symbols["host_end"]] = host[
        builder.HOST_ORG:symbols["host_end"]]
    site = builder.BASE * builder.BANK + 0x1B49
    assert result[site:site + 3] == bytes.fromhex("2ac600")
    result[site:site + 3] = bytes((0xC3, entry & 255, entry >> 8))
    result[0x14D] = builder.hsum(result)
    result[0x14E:0x150] = builder.gsum(result).to_bytes(2, "big")
    args.output.write_bytes(result)
    print(f"md5={hashlib.md5(result).hexdigest()}")
    print(f"sha256={hashlib.sha256(result).hexdigest()}")
    print(f"host_end=${symbols['host_end']:04X}")


if __name__ == "__main__":
    main()
