#!/usr/bin/env python3
"""Fix the screen tearing in Bubble Bobble Part 2 (Game Boy), and optionally
remember the last stage played (--save).

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
  6. Repair the global checksum. Without --save the header is untouched.

With --save it also makes the cartridge battery-backed and adds a bank:

  7. Grow the ROM to 256 KB, mark the header MBC1+RAM+BATTERY with 8 KB of
     RAM, and repair the header checksum.
  8. Put the game's own password encoder, copied unchanged, and the new
     routines from bb2save.asm into bank 8, with trampolines in bank 0.
  9. Save the password on every stage load, and pre-fill the PASSWORD screen
     with it.

It refuses any ROM it has no profile for, and checks every byte it replaces
before replacing it.
"""
import argparse
import hashlib
import os
import re
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

OP_RST_08 = 0xCF
OP_RST_10 = 0xD7
OP_LDH_A = 0xE0
BANK_WINDOW = 0x4000            # where a switchable bank appears
BANK_SIZE = 0x4000
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
        # The optional save feature (--save)
        "save": {
            "rom_size": 0x40000,
            "header": {0x147: (0x01, 0x03),     # MBC1 -> MBC1+RAM+BATTERY
                       0x148: (0x02, 0x03),     # 128 KB -> 256 KB
                       0x149: (0x00, 0x02)},    # no RAM -> 8 KB
            "bank": 8,
            # The game's password encoder (bank 6 $7EDC-$7F34): the world, stage
            # and extra bits -> the four symbols. It has no absolute jumps, so a
            # copy at the start of bank 8 works unchanged.
            "encoder": (0x1BEDC, 0x59, "bfccdfb088863887cea21b92766046e4"),
            "stage_load": (0x09D7, bytes.fromhex("fa0ac1")),   # ld a,(C10A), after the world and stage are derived
            "pw_init": (0x35E3, bytes.fromhex("cd8c2e")),      # call 2E8C, which ends the PASSWORD screen's setup
            "pw_step": (0x35E7, bytes.fromhex("2171c1")),      # ld hl,C171, the input handler's first instruction
            "far8_org": 0x0018,                                # RST $18-$30 vectors' junk, unused
            "t_save_org": 0x0030,
            "filler": [(0x0018, 0x0040, "f797c607f66cfbcd2b5b010550474ef0")],
            "consts": {
                "SAVE_BANK": 8, "BANK_NOW": 0xCE73, "MBC_BANK": 0x2100,
                "SRAM_ENABLE": 0x0000, "SRAM": 0xA000,
                "SIG_1": 0xB0, "SIG_2": 0xB2, "SUM_XOR": 0xA5,
                "PW_0": 0xCE6C, "PW_1": 0xCE6D, "PW_2": 0xCE6E, "PW_3": 0xCE6F,
                "WORLD": 0xC10A, "NEXT_SUBSTATE": 0x2E8C,
                "CURSOR_X": 0xC211, "CURSOR_END": 0x6C,
                "VBLANK_FLAGS": 0xC102,
                "Q_HIGH": 0xC111, "Q_LOW": 0xC112, "Q_COUNT": 0xC113, "Q_TILE": 0xC114,
                "SLOT_HIGH": 0x98, "SLOT_LOW": 0x86,          # slot 0 is $9886: the game adds 3 to the slot number
                "PF_LEFT": 0xA5,                # HRAM the game never reads or writes
            },
        },
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


def assemble_code(profile):
    """The patch's routines, as (bytes, labels), placed at the profile's org."""
    source = build_preamble(profile) + open(os.path.join(HERE, "bb2scroll.asm")).read()
    org = profile["org_body"]
    code, labels, _ = asm.assemble(source, org=org)
    if labels["code_end"] - org != len(code):
        raise SystemExit("assembled size does not match the routine's labels")
    return code, labels


def assemble_save(profile, tear_end):
    """The save feature's routines: ([(address, bytes)], labels). Bank 8 code
    follows the copied encoder at $4000; the trampolines go in the bank 0 junk,
    the last ones right after the tear fix's code."""
    sv = profile["save"]
    text = open(os.path.join(HERE, "bb2save.asm")).read()
    sections = re.split(r"^; ==== org (\w+) ====\n", text, flags=re.M)
    header, pairs = sections[0], list(zip(sections[1::2], sections[2::2]))
    consts = dict(sv["consts"])
    consts["ENCODE"] = BANK_WINDOW
    consts["BANK8_CODE"] = BANK_WINDOW + sv["encoder"][1]
    consts["FAR8_ORG"] = sv["far8_org"]
    consts["T_SAVE_ORG"] = sv["t_save_org"]
    consts["T_INIT_ORG"] = tear_end
    pre = "\n".join(f"{k:<12} = ${v:04X}" for k, v in consts.items()) + "\n\n"
    a = asm.Assembler()
    out = []
    for name, body in pairs:
        org = consts[name]
        code = a.assemble(pre + header + body, org)
        out.append((org, code))
    return out, a.labels


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


def patch(rom_bytes, verbose=True, save=False):
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

    if save:
        add_save(rom, rom_bytes, profile, body_end, say)
    elif header_checksum(rom) != rom[OFF_HDR_SUM]:
        raise SystemExit("header checksum no longer matches - the header was touched")
    g = global_checksum(rom)
    rom[OFF_GLOBAL_SUM], rom[OFF_GLOBAL_SUM + 1] = g >> 8, g & 0xFF
    say(f"global checksum {g:#06x}" + ("" if save else "; header unchanged"))
    return bytes(rom)


def add_save(rom, original, profile, tear_end, say):
    """Grow the ROM by a bank of code, make the cartridge battery-backed, and
    hook the stage load and the PASSWORD screen."""
    sv = profile["save"]
    for start, end, md5 in sv["filler"]:
        if hashlib.md5(original[start:end]).hexdigest() != md5:
            raise SystemExit(f"filler {start:#06x}-{end:#06x} is not what the profile expects")
    pieces, labels = assemble_save(profile, tear_end)
    if len(rom) > sv["rom_size"]:
        raise SystemExit("the ROM is already larger than the save feature's size")
    rom.extend(b"\xFF" * (sv["rom_size"] - len(rom)))

    off, length, md5 = sv["encoder"]
    encoder = original[off:off + length]
    if hashlib.md5(encoder).hexdigest() != md5:
        raise SystemExit("the password encoder is not the routine the profile expects")
    base = sv["bank"] * BANK_SIZE
    rom[base:base + length] = encoder
    say(f"copied the {length}-byte password encoder to bank {sv['bank']} ${BANK_WINDOW:04X}")

    for org, code in pieces:
        if org >= BANK_WINDOW:
            at = base + org - BANK_WINDOW
            if any(b != 0xFF for b in rom[at:at + len(code)]):
                raise SystemExit("bank 8 is not empty where the code goes")
        else:
            end = org + len(code)
            if not any(s <= org and end <= e for s, e, _ in sv["filler"] + profile["filler"]):
                raise SystemExit(f"the code at ${org:04X}-${end - 1:04X} is outside the filler")
            at = org
        rom[at:at + len(code)] = code
        say(f"injected {len(code)} bytes at ${org:04X}")
    if labels["t_end"] > 0x100:
        raise SystemExit("the trampolines run past the filler")

    for what, key, target in (("stage load", "stage_load", "t_save"),
                              ("PASSWORD screen setup", "pw_init", "t_init"),
                              ("PASSWORD screen input", "pw_step", "t_step")):
        off, old = sv[key]
        check_bytes(original, off, old, what)
        rom[off:off + 3] = bytes([OP_CALL, labels[target] & 0xFF, labels[target] >> 8])
        say(f"{what} at {off:#07x} -> call ${labels[target]:04X} {target}")

    for at, (was, now) in sv["header"].items():
        if original[at] != was:
            raise SystemExit(f"header byte {at:#05x} is {original[at]:#04x}, expected {was:#04x}")
        rom[at] = now
    rom[OFF_HDR_SUM] = header_checksum(rom)
    say("header: MBC1+RAM+BATTERY, 256 KB ROM, 8 KB RAM; header checksum repaired")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rom", help="stock Bubble Bobble Part 2 ROM")
    ap.add_argument("-o", "--output", help="patched ROM to write")
    ap.add_argument("--ips", help="IPS patch to write")
    ap.add_argument("--save", action="store_true",
                    help="also remember the last stage played (battery save, 256 KB ROM)")
    args = ap.parse_args()
    original = open(args.rom, "rb").read()
    patched = patch(original, save=args.save)
    if args.output:
        open(args.output, "wb").write(patched)
        print(f"wrote {args.output}  (md5 {hashlib.md5(patched).hexdigest()})")
    if args.ips:
        ips = make_ips(original, patched)
        open(args.ips, "wb").write(ips)
        print(f"wrote {args.ips}  ({len(ips)} bytes)")


if __name__ == "__main__":
    main()
