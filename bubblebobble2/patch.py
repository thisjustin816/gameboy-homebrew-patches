#!/usr/bin/env python3
"""Fix the screen tearing in Bubble Bobble Part 2 (Game Boy).

The game runs its logic right after each VBlank and writes the scroll
registers wherever the logic gets to them, partway down the visible frame.
The top of the screen is drawn with the old scroll and the rest with the new
one. This makes those writes wait for VBlank:

  1. Assemble bb2scroll.asm into unused space at the start of bank 0.
  2. Point the RST $08 and RST $10 vectors at it. Each stores a scroll value
     in HRAM and marks it pending.
  3. Replace the game's "SCX, SCY <- shadow" routine and the direct scroll
     writes of its two scrolling transitions with those RSTs.
  4. Have the VBlank handler copy the pending values just before its OAM DMA.
  5. Clear the pending bits at boot, since HRAM starts out random on hardware.
  6. Repair the global checksum. The header is untouched.

It refuses any ROM it has no profile for, and checks every byte it replaces
before replacing it.
"""
import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asm

HERE = os.path.dirname(os.path.abspath(__file__))

OFF_HDR_SUM = 0x14D
OFF_GLOBAL_SUM = 0x14E
MAX_IPS_RECORD = 0xFFFF
IPS_MERGE_GAP = 8
IPS_EOF_OFFSET = 0x454F4F

OP_RST_08 = 0xCF
OP_RST_10 = 0xD7
OP_LDH_A = 0xE0
OP_CALL = 0xCD
OP_JP = 0xC3
# Opcodes whose 16-bit operand is a jump or call target.
BRANCHES = (0xC3, 0xC2, 0xCA, 0xD2, 0xDA, 0xCD, 0xC4, 0xCC, 0xD4, 0xDC)

ROM_PROFILES = {
    "8bbb9ba0d72548706e4e5eba1b3a9fe1": {
        "name": "Bubble Bobble Part 2 (USA, Europe)",
        "consts": {
            "LCDC": 0x40, "SCY": 0x42, "SCX": 0x43,
            "OAM_DMA": 0xFF80,          # the DMA routine the game copies into HRAM
            "WRAM_CLEAR": 0x027F,       # the boot's clear of WRAM, which boot_init runs
            "SHADOW_X": 0xC167,         # the camera's scroll, as the game keeps it
            "SHADOW_Y": 0xC168,
            # HRAM the game never reads or writes
            "PEND_Y": 0xA2, "PEND_X": 0xA3, "FLAGS": 0xA4,
        },
        "org_body": 0x0068,
        "rst_y": 0x0008,                # the RST $08 and $10 vectors; the game
        "rst_x": 0x0010,                # never executes either
        # Junk the game never executes or reads, which the code goes over: the
        # two RST vectors and the area between the joypad vector and the
        # header. (start, end, md5 of the stock bytes)
        "filler": [
            (0x0008, 0x0010, "9fb716a1f86860d9795e5fb290969776"),
            (0x0010, 0x0018, "e35d950295f789236f264e9e98c13a06"),
            (0x0068, 0x0100, "a8df4500dd358c31b921fe5b775d9799"),
        ],
        # The game's scroll copy (bank 1 $4129): SCX <- $C167, SCY <- $C168, ret
        "scroll_copy": (0x4129, bytes.fromhex("fa67c1e043fa68c1e042c9")),
        # The VBlank handler's OAM DMA call, at the top of its full update
        "vblank_dma_call": (0x023F, bytes.fromhex("cd80ff")),
        # The boot's call to the WRAM clear
        "boot_call": (0x0156, bytes.fromhex("cd7f02")),
        # Direct scroll writes on per-frame paths: (offset, axis, bytes before, bytes after)
        "direct_writes": [
            (0x0B62, "y", "c602", "c9"),        # scroll down 2 a frame until SCY = $80
            (0x0BC8, "y", "f042c602", "f043"),  # scroll down 2 and left 2 a frame
            (0x0BD4, "x", "af", "fae9c1"),
            (0x1639, "y", "c602", "ea68c1"),    # scroll back to the start of the room
            (0x1648, "x", "d602", "ea67c1"),
        ],
    },
}


def header_checksum(rom):
    x = 0
    for i in range(0x134, 0x14D):
        x = (x - rom[i] - 1) & 0xFF
    return x


def global_checksum(rom):
    return (sum(rom) - rom[OFF_GLOBAL_SUM] - rom[OFF_GLOBAL_SUM + 1]) & 0xFFFF


def make_ips(original, patched):
    if len(patched) != len(original):
        raise SystemExit("IPS generation expects same-sized images")
    runs = []
    for i in range(len(patched)):
        if patched[i] == original[i]:
            continue
        if runs and i - runs[-1][1] <= IPS_MERGE_GAP:
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1])
    out = bytearray(b"PATCH")
    for start, end in runs:
        if start == IPS_EOF_OFFSET:
            start -= 1
        while start < end:
            size = min(end - start, MAX_IPS_RECORD)
            out += bytes([(start >> 16) & 0xFF, (start >> 8) & 0xFF, start & 0xFF])
            out += bytes([(size >> 8) & 0xFF, size & 0xFF])
            out += patched[start:start + size]
            start += size
    out += b"EOF"
    return bytes(out)


def build_preamble(profile):
    lines = [f"; ==== generated from the ROM profile: {profile['name']} ===="]
    for name, value in profile["consts"].items():
        lines.append(f"{name:<12} = ${value:04X}")
    return "\n".join(lines) + "\n\n"


def load_profile(rom):
    md5 = hashlib.md5(rom).hexdigest()
    if md5 not in ROM_PROFILES:
        raise SystemExit(
            f"unrecognized ROM (md5 {md5}); this patch only knows "
            + ", ".join(p["name"] for p in ROM_PROFILES.values()))
    return ROM_PROFILES[md5]


def assemble_code(profile):
    """The patch's routines, as (bytes, labels), placed at the profile's org."""
    source = build_preamble(profile) + open(os.path.join(HERE, "bb2scroll.asm")).read()
    org = profile["org_body"]
    code, labels, _ = asm.assemble(source, org=org)
    if labels["code_end"] - org != len(code):
        raise SystemExit("assembled size does not match the routine's labels")
    return code, labels


def bank_address(offset):
    """The address the CPU sees for a ROM offset, given the bank that is mapped."""
    return offset if offset < 0x4000 else 0x4000 + offset % 0x4000


def check_bytes(rom, offset, expected, what):
    got = bytes(rom[offset:offset + len(expected)])
    if got != expected:
        raise SystemExit(f"{what} at {offset:#07x}: expected {expected.hex()}, found {got.hex()}")


def check_no_branches_into(rom, address, span, what):
    """Nothing may jump or call into the middle of code that is being retired."""
    targets = {address + k for k in range(1, span)}
    for i in range(0, len(rom) - 2):
        if rom[i] in BRANCHES and (rom[i + 1] | rom[i + 2] << 8) in targets:
            raise SystemExit(f"{what}: {rom[i:i + 3].hex()} at {i:#07x} branches into it")


def patch(rom_bytes, verbose=True):
    rom = bytearray(rom_bytes)
    profile = load_profile(rom_bytes)
    say = print if verbose else (lambda *a, **k: None)
    say(f"ROM: {profile['name']}")

    for start, end, md5 in profile["filler"]:
        got = hashlib.md5(rom_bytes[start:end]).hexdigest()
        if got != md5:
            raise SystemExit(f"filler {start:#06x}-{end:#06x} is not what the profile expects")

    code, labels = assemble_code(profile)
    org = profile["org_body"]
    body_end = org + len(code)
    if not any(s <= org and body_end <= e for s, e, _ in profile["filler"]):
        raise SystemExit(f"the code (${org:04X}-${body_end - 1:04X}) does not fit the filler")
    rom[org:body_end] = code
    say(f"injected {len(code)} bytes at ${org:04X}-${body_end - 1:04X}")

    c = profile["consts"]
    for vector, label, pend in ((profile["rst_y"], "defer_y", "PEND_Y"),
                                (profile["rst_x"], "defer_x", "PEND_X")):
        stub = bytes([OP_LDH_A, c[pend], OP_JP, labels[label] & 0xFF, labels[label] >> 8])
        if not any(s <= vector and vector + len(stub) <= e for s, e, _ in profile["filler"]):
            raise SystemExit(f"RST vector ${vector:02X} is outside the filler")
        rom[vector:vector + len(stub)] = stub
        say(f"RST ${vector:02X}: ldh (${c[pend]:02X}),a / jp ${labels[label]:04X} {label}")

    off, old = profile["scroll_copy"]
    check_bytes(rom_bytes, off, old, "scroll copy")
    check_no_branches_into(rom_bytes, bank_address(off), len(old), "scroll copy")
    a = labels["scroll_copy"]
    rom[off:off + 3] = bytes([OP_JP, a & 0xFF, a >> 8])
    say(f"scroll copy at {off:#07x} -> jp ${a:04X} scroll_copy")

    for off, axis, before, after in profile["direct_writes"]:
        reg = c["SCY"] if axis == "y" else c["SCX"]
        check_bytes(rom_bytes, off, bytes([OP_LDH_A, reg]), f"direct SC{axis.upper()} write")
        check_bytes(rom_bytes, off - len(before) // 2, bytes.fromhex(before), "context before")
        check_bytes(rom_bytes, off + 2, bytes.fromhex(after), "context after")
        rom[off:off + 2] = bytes([OP_RST_08 if axis == "y" else OP_RST_10, 0x00])
        say(f"direct SC{axis.upper()} write at {off:#07x} -> rst ${0x08 if axis == 'y' else 0x10:02X}")

    off, old = profile["vblank_dma_call"]
    check_bytes(rom_bytes, off, old, "VBlank OAM DMA call")
    a = labels["vblank_scroll"]
    rom[off:off + 3] = bytes([OP_CALL, a & 0xFF, a >> 8])
    say(f"VBlank handler's OAM DMA call at {off:#07x} -> call ${a:04X} vblank_scroll")

    off, old = profile["boot_call"]
    check_bytes(rom_bytes, off, old, "boot's WRAM clear call")
    a = labels["boot_init"]
    rom[off:off + 3] = bytes([OP_CALL, a & 0xFF, a >> 8])
    say(f"boot's WRAM clear call at {off:#07x} -> call ${a:04X} boot_init")

    if header_checksum(rom) != rom[OFF_HDR_SUM]:
        raise SystemExit("header checksum no longer matches - the header was touched")
    g = global_checksum(rom)
    rom[OFF_GLOBAL_SUM], rom[OFF_GLOBAL_SUM + 1] = g >> 8, g & 0xFF
    say(f"header unchanged; global checksum {g:#06x}")
    return bytes(rom)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rom", help="stock Bubble Bobble Part 2 ROM")
    ap.add_argument("-o", "--output", help="patched ROM to write")
    ap.add_argument("--ips", help="IPS patch to write")
    args = ap.parse_args()
    original = open(args.rom, "rb").read()
    patched = patch(original)
    if args.output:
        open(args.output, "wb").write(patched)
        print(f"wrote {args.output}  (md5 {hashlib.md5(patched).hexdigest()})")
    if args.ips:
        ips = make_ips(original, patched)
        open(args.ips, "wb").write(ips)
        print(f"wrote {args.ips}  ({len(ips)} bytes)")


if __name__ == "__main__":
    main()
