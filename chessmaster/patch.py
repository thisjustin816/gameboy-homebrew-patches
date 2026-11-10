#!/usr/bin/env python3
"""Fix two bugs that crash The Chessmaster (Game Boy) while it thinks.

  1. The thinking clock in the VBlank handler adds an uninitialized register to
     the clock's address, so a tick can increment a byte of the search's data
     instead of the clock. cmfix.asm's tick block replaces the 14 bytes that
     form the address, in place, with code that takes the same cycles.
  2. After a root move fails high and its re-search does not improve, the root
     move list no longer starts with the principal variation's move, and the
     next iteration files a line under the wrong move. A routine in the unused
     bytes before the header puts the right node first at the start of each
     iteration.
  3. Repairs the global checksum. The header checksum is unchanged.

It refuses any ROM it has no profile for and checks every byte it replaces
before replacing it.
"""
import argparse
import hashlib
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "common"))
import asm
from checksum import OFF_GLOBAL_SUM, OFF_HDR_SUM, global_checksum, header_checksum
from ips import make_ips

HERE = os.path.dirname(os.path.abspath(__file__))

BANK_SIZE = 0x4000
OP_CALL = 0xCD
ORDER_MARKER = "; ==== org ORDER_ORG ===="

ROM_PROFILES = {
    "6b6d4a25d3c1e2890b22271c44e62dbf": {
        "name": "Chessmaster, The (USA) (Rev 1)",
        # bank 0, the thinking clock: ld a,(SIDE_FLAGS) / and $08 / jr z,+2 / ld a,$02 /
        # ld c,a / ld hl,CLOCK / add hl,bc, followed by the inc (hl) the block keeps
        "tick_org": 0x26EB,
        "tick_stock": "fa2dd0e60828023e024f2185d509",
        "tick_next": "34",
        "order_org": 0x0070,            # bank 0, between the vectors and the header
        "order_padding": (0x006A, 0x0100),      # $FF and $00 runs the game never runs or reads
        # (bank, address, stock bytes, label): each becomes a call
        "hooks": [(2, 0x41B7, "cdf741", "fix_root_order")],    # call ITER_LINE at each iteration start
        "consts": {
            "SIDE_FLAGS": 0xD02D,
            "CLOCK_LO": 0x85, "CLOCK_HI": 0xD5,         # the two 16-bit clocks at $D585 and $D587
            "ITER_LINE": 0x41F7,        # bank 2: copy the principal variation into the first line
            "PV_LEN": 0xD501,           # moves in the principal variation
            "PV_FROM": 0xD703, "PV_TO": 0xD704,         # its first move
            "ROOT_COUNT": 0xD700,       # root moves in the list
            "ROOT_ORDER": 0xDACC,       # the list: one node number per root move, best first
            "NODE_FROM": 0xD75F, "NODE_TO": 0xD7EC,     # each node's move
        },
    },
}


def load_profile(rom):
    md5 = hashlib.md5(rom).hexdigest()
    if md5 not in ROM_PROFILES:
        raise SystemExit(
            f"unrecognized ROM (md5 {md5}); this patch only knows "
            + ", ".join(p["name"] for p in ROM_PROFILES.values()))
    return ROM_PROFILES[md5]


def check_bytes(rom, offset, expected, what):
    got = bytes(rom[offset:offset + len(expected)])
    if got != expected:
        raise SystemExit(f"{what} at {offset:#07x}: expected {expected.hex()}, found {got.hex()}")


def file_offset(bank, address):
    return bank * BANK_SIZE + address - BANK_SIZE if bank else address


def assemble(profile, source=None):
    """(tick block, root order routine, labels), from cmfix.asm or the given source."""
    text = source if source is not None else open(os.path.join(HERE, "cmfix.asm")).read()
    if text.count(ORDER_MARKER) != 1:
        raise SystemExit("cmfix.asm needs exactly one ORDER_ORG section")
    first, second = text.split(ORDER_MARKER)
    consts = "\n".join(f"{k:<12} = ${v:04X}" for k, v in profile["consts"].items()) + "\n"
    head = f"; ==== generated from the ROM profile: {profile['name']} ====\n" + consts
    tick, labels_t, _ = asm.assemble(head + first, org=profile["tick_org"])
    if labels_t["tick_end"] - profile["tick_org"] != len(tick):
        raise SystemExit("assembled size does not match the tick labels")
    order, labels_o, _ = asm.assemble(head + second, org=profile["order_org"])
    if labels_o["order_end"] - profile["order_org"] != len(order):
        raise SystemExit("assembled size does not match the root order labels")
    return tick, order, {**labels_t, **labels_o}


def patch(rom_bytes, verbose=True, source=None):
    rom = bytearray(rom_bytes)
    profile = load_profile(rom_bytes)
    say = print if verbose else (lambda *a, **k: None)
    say(f"ROM: {profile['name']}")

    tick, order, labels = assemble(profile, source)

    stock = bytes.fromhex(profile["tick_stock"])
    org = profile["tick_org"]
    check_bytes(rom_bytes, org, stock, "thinking clock")
    check_bytes(rom_bytes, org + len(stock), bytes.fromhex(profile["tick_next"]), "the clock's inc (hl)")
    if len(tick) != len(stock):
        raise SystemExit(f"the tick block is {len(tick)} bytes; it must replace exactly {len(stock)}")
    rom[org:org + len(tick)] = tick
    say(f"bank 0 ${org:04X}: {stock.hex()} -> {tick.hex()} (thinking clock)")

    lo, hi = profile["order_padding"]
    if any(b not in (0x00, 0xFF) for b in rom_bytes[lo:hi]):
        raise SystemExit("root order: the unused bytes are not all $00 or $FF")
    at = profile["order_org"]
    if not (lo <= at and at + len(order) <= hi):
        raise SystemExit(f"root order: {len(order)} bytes do not fit ${lo:04X}-${hi - 1:04X}")
    rom[at:at + len(order)] = order
    say(f"injected {len(order)} bytes at bank 0 ${at:04X} (root order)")

    for bank, address, stock_call, label in profile["hooks"]:
        f = file_offset(bank, address)
        check_bytes(rom_bytes, f, bytes.fromhex(stock_call), f"hook for {label}")
        a = labels[label]
        rom[f:f + 3] = bytes([OP_CALL, a & 0xFF, a >> 8])
        say(f"bank {bank} ${address:04X} -> call ${a:04X} {label}")

    if rom[OFF_HDR_SUM] != header_checksum(rom):
        raise SystemExit("the header checksum no longer matches; the patch must not touch the header")
    g = global_checksum(rom)
    rom[OFF_GLOBAL_SUM], rom[OFF_GLOBAL_SUM + 1] = g >> 8, g & 0xFF
    say(f"header checksum {rom[OFF_HDR_SUM]:#04x} (unchanged), global checksum {g:#06x}")
    return bytes(rom)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rom", help="stock The Chessmaster ROM")
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
