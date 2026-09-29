#!/usr/bin/env python3
"""Retune Bub's jumping and falling in Classic Bubble Bobble (Game Boy Color)
to match the Master System version, and remember the last round started.

The game moves Bub once every two frames. Against the Master System game it
jumps slowly and almost linearly, barely moves sideways in a jump, and falls
off ledges at less than half the speed while drifting twice as far. This:

  1. Assembles cbbphysics.asm into the padding at the end of bank 2: a new
     jump table and a replacement for the per-tick sideways movement and
     gravity.
  2. Points the jump at the new table and gives its three starts the new
     length.
  3. Jumps from the start of the stock sideways movement to the new code,
     which rejoins the stock landing check.
  4. Assembles cbbsave.asm into the empty end of bank 0.
  5. Saves the round on every round load, and pre-fills the PASSWORD screen
     with its password, made by the game's own encoder.
  6. Marks the header MBC5+RAM+BATTERY with 8 KB of RAM and repairs both
     checksums.

It refuses any ROM it has no profile for, checks every byte it replaces before
replacing it, and checks that nothing outside the retired code branches into
it.
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
IPS_RLE_MIN = 12               # shortest run of one byte that an RLE record beats
IPS_EOF_OFFSET = 0x454F4F
BANK_SIZE = 0x4000
OP_JP = 0xC3
OP_LD_A = 0x3E
OP_LD_HL = 0x21
OP_CALL = 0xCD
OP_NOP = 0x00
BRANCHES = (0xC3, 0xC2, 0xCA, 0xD2, 0xDA, 0xCD, 0xC4, 0xCC, 0xD4, 0xDC)
RELATIVE = (0x18, 0x20, 0x28, 0x30, 0x38)

ROM_PROFILES = {
    "4bc8467ed91a94ba23648706b551cef5": {
        "name": "Classic Bubble Bobble (USA)",
        "bank": 2,                      # the player's movement code
        "consts": {
            "X": 0xD527, "Y": 0xD526,   # Bub's position
            "JUMP": 0xC47D,             # jump countdown, 0 when not jumping
            "LOCK": 0xC47E,             # direction held at take-off: 0 none, 1 left, 2 right
            "LOCK_LEFT": 1, "LOCK_RIGHT": 2,
            "GROUND": 0xC47C,           # stood on something at the end of the last tick
            "WALL_L": 0xC47A, "WALL_R": 0xC47B,
            "PAD": 0xC026, "PAD_LEFT": 0x20, "PAD_RIGHT": 0x10,   # buttons held
            "FACE": 0xD302, "FACE_LEFT": 0x80, "FACE_RIGHT": 0x00, "FACE_WALK": 0x01,
            "SHOES": 0xC04A,            # the speed item
            "TICK": 0xCEC0,             # WRAM the game never names or changes
            "COOL": 0xCEC2,             # ticks until Bub may fire again, also unnamed
            "COOL_TICKS": 11,           # the Master System's rate: a shot every 22 frames (stock 28)
            "SHOT": 0xD536,             # the shot's state, 0 while the slot is free
            "BUBBLE_STATE": 0xD538,     # the first floating bubble's state, then one per 2 bytes
            "BUBBLE_X": 0xD509, "BUBBLE_Y": 0xD508,
            "RANGE_ITEM": 0xC048,       # set by the item that makes shots go further
            "PAD_JUMP": 0x01,
            # Where the bounce test goes on: the bubble loop, then the loop over enemies in bubbles
            "BUBBLE_POP": 0x541C, "BUBBLE_NEXT": 0x544D, "BUBBLE_BURST": 0x56C0, "BUBBLE_BOUNCE": 0x542A,
            "ENEMY_POP": 0x5649, "ENEMY_NEXT": 0x5676, "ENEMY_BURST": 0x5715, "ENEMY_BOUNCE": 0x5657,
            # The Master System's bounce, by the bubble's Y less Bub's (0-15 here)
            "LATE_JUMP": 13,            # JUMP from 5 frames before the end of the top on
            "EARLY_TOP": 14,            # before then, or standing: 14-15 is left alone, less pops
            "LATE_POP": 9,              # from then on: less than 9 pops
            "LATE_CLEAN": 11,           # 9-10 bounces and pops, 11-15 bounces
            "RESUME": 0x4BD3,           # the stock landing check
            # 8-tick patterns of extra pixels
            "MASK_FALL": 0x55,          # 2 + 4/8
            "MASK_PUSH": 0x11,          # 2 + 2/8
            "MASK_COAST": 0x55,         # 2 - 4/8
            "MASK_AGAINST": 0x77,       # 6/8
            "MASK_STEER": 0xAD,         # 5/8
        },
        "phys_org": 0x7E00,             # bank 2 padding ($6D1B-$7FFF is all zero)
        "padding": (0x6D1B, 0x8000),
        # The stock sideways movement and gravity, retired by a jp at its start
        "retired": (0x4AEF, 0x4BD3, "fa7ac4a72067fa7ec4fe01200afa27d53dea27d5c3c64b"),
        "table_ptr": (0x4AA8, bytes.fromhex("212a68")),        # ld hl,$682A
        "jump_starts": [0x4A4B],                               # ld a,$21 -> JUMP, from the ground
        "bounce_starts": [0x542A, 0x5657],                     # the same, bouncing on a bubble or a trapped enemy
        "bounce_gates": [(0x5421, "bg_bubble"), (0x564E, "bg_enemy")],   # the bounce's jump-held test
        "old_length": 0x21,
        "wram": [0xCEC0, 0xCEC1, 0xCEC2],
        # The shot: twice as fast for half as long. (address, stock bytes, new bytes)
        "shot": [(0x4C7E, "c601", "c604"),     # starts 4 px ahead facing right, where stock is after its first tick
                 (0x4C81, "3e03", "3e06"),     # 6 px a tick to the right
                 (0x4C92, "d602", "d605"),     # 5 px ahead facing left
                 (0x4C95, "3efd", "3efa"),     # 6 px a tick to the left
                 (0x5B29, "fe0e", "fe07"),     # becomes a bubble after 7 ticks, not 14
                 (0x5B2D, "fe0a", "fe05"),     # and its two sprite frames switch at half the tick counts
                 (0x5B32, "fe08", "fe04"),
                 (0x5B3B, "fe18", "fe0c"),     # the same with the longer-range item
                 (0x5B3F, "fe10", "fe08"),
                 (0x5B44, "fe0a", "fe05")],
        "fire_gate": (0x4C4C, "2136d57e"),     # ld hl,$D536 / ld a,(hl) in the fire check
        # Landing on a bubble: the contact test ($67DD) takes Bub and a bubble as
        # touching within 6 px either side, 13 px in all; the Master System's is 23
        "bubbles": [(0x6815, "fe07", "fe0c"),  # 0 to 11 px to one side
                    (0x6819, "fefa", "fef5")], # 1 to 11 px to the other
        # Starting a jump: the start branches past the table step ($4A7C) to the
        # wall checks ($4AC3), so Bub first moves a tick later. These go through
        # the step instead, which does the same wall checks first.
        "takeoff": [(0x4A64, "185d", "1816"),  # locked left
                    (0x4A6B, "2856", "280f"),  # straight up
                    (0x4A7A, "1847", "1800")], # locked right
        # The save
        "save": {
            "org": 0x3E00,
            "padding": (0x1665, 0x4000),        # bank 0 from here on is all zero
            "header": {0x147: (0x19, 0x1B),     # MBC5 -> MBC5+RAM+BATTERY
                       0x149: (0x00, 0x02)},    # no RAM -> 8 KB
            # (bank, address, stock bytes, label): each becomes a call
            "hooks": [(0x01, 0x419B, "fa4fc0", "save_round"),  # ld a,(ROUND) in the round load
                      (0x3C, 0x4036, "ea83d6", "pf_init"),     # ld (SLOT),a in the PASSWORD screen's setup
                      (0x3C, 0x4196, "fa83d6", "pf_step")],    # ld a,(SLOT) in its per-frame code
            "consts": {
                "ROUTE": 0xC04E, "ROUND": 0xC04F,       # the round: route 0-2, round 0-59
                "ROUTES": 3, "ROUNDS": 60,
                "ENCODE": 0x154E,               # route and round -> four letter tiles at BUFFER
                "BUFFER": 0xD679,               # the PASSWORD screen's four letters, $FF when empty
                "SLOT": 0xD683, "ROW": 0xD682, "ROW_END": 4,
                "SLOT_VRAM": 0x9887,            # slot n is drawn at SLOT_VRAM + 2n
                "QUEUE_COPY": 0x0BF5,           # queue a copy for VBlank
                "BANK_NOW": 0xC022,             # the mapped ROM bank
                "SRAM": 0xA000, "SRAM_ENABLE": 0x0000, "SRAM_BANK": 0x4000,
                "SIG_1": 0xB0, "SIG_2": 0xB1, "SUM_XOR": 0xA5,
                "PF_PENDING": 0xCEC1,           # WRAM the game never names or changes
            },
        },
        # Bank 0 jumps that land in the retired range's addresses but in another
        # bank: (site, where the bank switch starts, its bytes)
        "other_bank_jumps": [(0x1325, 0x1315, "3e38f5fa22c0ea23c0f1ea0020ea22c0")],   # bank $38
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
    """An IPS patch from original to patched. The patched image may be longer;
    the extra bytes become records past the end of the original."""
    if len(patched) < len(original):
        raise SystemExit("IPS generation expects the patched image to be at least as long")
    runs = []
    for i in range(len(patched)):
        if i < len(original) and patched[i] == original[i]:
            continue
        if runs and i - runs[-1][1] <= IPS_MERGE_GAP:
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1])
    out = bytearray(b"PATCH")

    def header(offset):
        return bytes([(offset >> 16) & 0xFF, (offset >> 8) & 0xFF, offset & 0xFF])

    for start, end in runs:
        if start == IPS_EOF_OFFSET:
            start -= 1
        while start < end:
            same = 1
            while start + same < end and patched[start + same] == patched[start] and same < MAX_IPS_RECORD:
                same += 1
            if same >= IPS_RLE_MIN:
                out += header(start) + b"\x00\x00" + bytes([same >> 8, same & 0xFF, patched[start]])
                start += same
                continue
            stop = start + 1
            while stop < end and stop - start < MAX_IPS_RECORD:
                ahead = 1
                while stop + ahead < end and patched[stop + ahead] == patched[stop] and ahead < IPS_RLE_MIN:
                    ahead += 1
                if ahead >= IPS_RLE_MIN:
                    break
                stop += 1
            out += header(start) + bytes([(stop - start) >> 8, (stop - start) & 0xFF]) + patched[start:stop]
            start = stop
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


def check_bytes(rom, offset, expected, what):
    got = bytes(rom[offset:offset + len(expected)])
    if got != expected:
        raise SystemExit(f"{what} at {offset:#07x}: expected {expected.hex()}, found {got.hex()}")



def file_offset(profile, address):
    return profile["bank"] * BANK_SIZE + address - BANK_SIZE


def assemble_code(profile):
    """The patch's code and table, as (bytes, labels), at the profile's org."""
    source = build_preamble(profile) + open(os.path.join(HERE, "cbbphysics.asm")).read()
    org = profile["phys_org"]
    code, labels, _ = asm.assemble(source, org=org)
    if labels["code_end"] - org != len(code):
        raise SystemExit("assembled size does not match the routine's labels")
    return code, labels


def assemble_save(profile):
    sv = profile["save"]
    lines = [f"{k:<12} = ${v:04X}" for k, v in sv["consts"].items()] + [f"SAVE_ORG     = ${sv['org']:04X}"]
    code, labels, _ = asm.assemble("\n".join(lines) + "\n\n" + open(os.path.join(HERE, "cbbsave.asm")).read(),
                                   org=sv["org"])
    if labels["save_end"] - sv["org"] != len(code):
        raise SystemExit("assembled size does not match the save routine's labels")
    return code, labels


def add_save(rom, original, profile, say):
    sv = profile["save"]
    code, labels = assemble_save(profile)
    lo, hi = sv["padding"]
    if any(original[lo:hi]):
        raise SystemExit("the end of bank 0 is not all zero")
    if not (lo <= sv["org"] and sv["org"] + len(code) <= hi):
        raise SystemExit("the save code does not fit the end of bank 0")
    rom[sv["org"]:sv["org"] + len(code)] = code
    say(f"injected {len(code)} bytes at bank 0 ${sv['org']:04X}")
    for bank, address, stock, label in sv["hooks"]:
        f = bank * BANK_SIZE + address - BANK_SIZE if bank else address
        check_bytes(original, f, bytes.fromhex(stock), f"hook for {label}")
        a = labels[label]
        rom[f:f + 3] = bytes([0xCD, a & 0xFF, a >> 8])
        say(f"bank {bank:#04x} ${address:04X} -> call ${a:04X} {label}")
    for at, (was, now) in sv["header"].items():
        if original[at] != was:
            raise SystemExit(f"header byte {at:#05x} is {original[at]:#04x}, expected {was:#04x}")
        rom[at] = now
    rom[OFF_HDR_SUM] = header_checksum(rom)
    say("header: MBC5+RAM+BATTERY, 8 KB RAM; header checksum repaired")


def bank_view(rom, bank):
    """The 64 KB address space with bank 0 and the given bank mapped."""
    view = bytearray(0x10000)
    view[0:BANK_SIZE] = rom[0:BANK_SIZE]
    view[BANK_SIZE:2 * BANK_SIZE] = rom[bank * BANK_SIZE:(bank + 1) * BANK_SIZE]
    return bytes(view)


def check_retired(rom, profile):
    """Nothing outside the retired code may jump or branch into its body."""
    start, end, _ = profile["retired"]
    view = bank_view(rom, profile["bank"])
    body = range(start + 1, end)
    exempt = set()
    for site, switch, stock in profile["other_bank_jumps"]:
        check_bytes(rom, switch, bytes.fromhex(stock), "bank switch before an other-bank jump")
        if switch + len(bytes.fromhex(stock)) != site:
            raise SystemExit(f"the bank switch at ${switch:04X} does not lead to ${site:04X}")
        exempt.add(site)
    for i in range(0, 0x8000 - 2):
        if start <= i < end or i in exempt:
            continue
        if view[i] in BRANCHES and (view[i + 1] | view[i + 2] << 8) in body:
            raise SystemExit(f"{view[i:i + 3].hex()} at ${i:04X} branches into the retired code")
        if view[i] in RELATIVE:
            target = i + 2 + (view[i + 1] - 256 if view[i + 1] > 127 else view[i + 1])
            if target in body and abs(target - i) < 130 and not (start - 130 < i < start):
                raise SystemExit(f"{view[i:i + 2].hex()} at ${i:04X} may branch into the retired code")


def check_no_branch_into(rom, profile, lo, hi):
    """Nothing in bank 0 or the profile's bank may jump or branch to lo..hi-1."""
    view = bank_view(rom, profile["bank"])
    for i in range(0, 0x8000 - 2):
        if view[i] in BRANCHES and lo <= (view[i + 1] | view[i + 2] << 8) < hi:
            raise SystemExit(f"{view[i:i + 3].hex()} at ${i:04X} branches into ${lo:04X}-${hi - 1:04X}")
        if view[i] in RELATIVE:
            target = i + 2 + (view[i + 1] - 256 if view[i + 1] > 127 else view[i + 1])
            if lo <= target < hi and abs(target - i) < 130:
                raise SystemExit(f"{view[i:i + 2].hex()} at ${i:04X} may branch into ${lo:04X}-${hi - 1:04X}")


def patch(rom_bytes, verbose=True):
    rom = bytearray(rom_bytes)
    profile = load_profile(rom_bytes)
    say = print if verbose else (lambda *a, **k: None)
    say(f"ROM: {profile['name']}")
    c = profile["consts"]

    code, labels = assemble_code(profile)
    org = profile["phys_org"]
    lo, hi = profile["padding"]
    if not (lo <= org and org + len(code) <= hi):
        raise SystemExit("the code does not fit the padding")
    at = file_offset(profile, org)
    if any(rom[file_offset(profile, lo):file_offset(profile, hi)]):
        raise SystemExit("the padding at the end of the bank is not all zero")
    rom[at:at + len(code)] = code
    length = labels["jump_end"] - labels["jump_table"]
    say(f"injected {len(code)} bytes at bank {profile['bank']} ${org:04X}: "
        f"a {length}-step jump table and the movement code")

    for w in profile["wram"]:
        for i in range(len(rom_bytes) - 2):
            if rom_bytes[i] in (0xFA, 0xEA, 0x21, 0x11, 0x01) and abs((rom_bytes[i + 1] | rom_bytes[i + 2] << 8) - w) <= 8:
                raise SystemExit(f"the game names ${rom_bytes[i + 1] | rom_bytes[i + 2] << 8:04X}, near the patch's ${w:04X}")

    off, old = profile["table_ptr"]
    check_bytes(rom_bytes, file_offset(profile, off), old, "jump table pointer")
    t = labels["jump_table"]
    rom[file_offset(profile, off):file_offset(profile, off) + 3] = bytes([OP_LD_HL, t & 0xFF, t >> 8])
    say(f"jump table pointer at ${off:04X} -> ${t:04X}")

    for off in profile["jump_starts"]:
        f = file_offset(profile, off)
        check_bytes(rom_bytes, f, bytes([OP_LD_A, profile["old_length"], 0xEA, c["JUMP"] & 0xFF, c["JUMP"] >> 8]),
                    "jump start")
        rom[f + 1] = length
        say(f"jump start at ${off:04X}: {profile['old_length']} -> {length} steps")

    bs = labels["bounce_start"]
    for off in profile["bounce_starts"]:
        f = file_offset(profile, off)
        check_bytes(rom_bytes, f, bytes([OP_LD_A, profile["old_length"], 0xEA, c["JUMP"] & 0xFF, c["JUMP"] >> 8]),
                    "bounce start")
        check_no_branch_into(rom_bytes, profile, off + 1, off + 5)
        rom[f:f + 5] = bytes([OP_CALL, bs & 0xFF, bs >> 8, OP_NOP, OP_NOP])
        say(f"bounce start at ${off:04X} -> call ${bs:04X} bounce_start, with its first step taken")

    for off, label in profile["bounce_gates"]:
        # ld a,(PAD) / bit 0,a / jr nz,bounce / jr pop; the code jumped to goes on at one of the three
        f = file_offset(profile, off)
        check_bytes(rom_bytes, f, bytes([0xFA, c["PAD"] & 0xFF, c["PAD"] >> 8, 0xCB, 0x47, 0x20, 0x02, 0x18, 0xF2]),
                    "bounce test")
        check_no_branch_into(rom_bytes, profile, off + 1, off + 9)
        a = labels[label]
        rom[f:f + 3] = bytes([OP_JP, a & 0xFF, a >> 8])
        say(f"bounce test at ${off:04X} -> jp ${a:04X} {label}, the Master System's bounce by depth and jump phase")

    start, end, stock = profile["retired"]
    check_bytes(rom_bytes, file_offset(profile, start), bytes.fromhex(stock), "stock sideways movement")
    check_retired(rom_bytes, profile)
    m = labels["move"]
    f = file_offset(profile, start)
    rom[f:f + 3] = bytes([OP_JP, m & 0xFF, m >> 8])
    say(f"sideways movement and gravity at ${start:04X}-${end - 1:04X} -> jp ${m:04X}")

    for off, old, new in profile["shot"] + profile["bubbles"] + profile["takeoff"]:
        f = file_offset(profile, off)
        check_bytes(rom_bytes, f, bytes.fromhex(old), "shot constant")
        rom[f:f + len(bytes.fromhex(new))] = bytes.fromhex(new)
    off, old = profile["fire_gate"]
    f = file_offset(profile, off)
    check_bytes(rom_bytes, f, bytes.fromhex(old), "fire check")
    check_no_branch_into(rom_bytes, profile, off + 1, off + len(bytes.fromhex(old)))
    a = labels["fire_gate"]
    rom[f:f + 4] = bytes([OP_CALL, a & 0xFF, a >> 8, OP_NOP])
    say(f"shot: {len(profile['shot'])} constants for twice the speed over the same distance; "
        f"fire check at ${off:04X} -> call ${a:04X} fire_gate")

    add_save(rom, rom_bytes, profile, say)
    g = global_checksum(rom)
    rom[OFF_GLOBAL_SUM], rom[OFF_GLOBAL_SUM + 1] = g >> 8, g & 0xFF
    say(f"global checksum {g:#06x}")
    return bytes(rom)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rom", help="stock Classic Bubble Bobble ROM")
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
