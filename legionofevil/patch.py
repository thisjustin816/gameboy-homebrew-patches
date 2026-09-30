#!/usr/bin/env python3
"""Add saving, a pause menu and fewer dropped sprites to Legion of Evil (Game Boy).

The stock cartridge is a plain 32 KB ROM with no save RAM. This patch:

  1. Grows the ROM to 64 KB and marks the header MBC1+RAM+BATTERY with 8 KB of
     RAM, then repairs both checksums. The game already writes bank numbers to
     $2000, so an MBC1 board takes them.
  2. Points the seven music-player calls at bank 1. Stock passes bank 2, which
     a plain ROM ignores but a banked cartridge or emulator would map.
  3. Puts the new code in bank 2, reached through small stubs in bank 0's
     unused bytes, and hooks the boot, the title, the main loop's frame wait,
     the store and the run loop.

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
IPS_RLE_MIN = 12
IPS_EOF_OFFSET = 0x454F4F
OP_CALL = 0xCD
OP_JP = 0xC3
BANK_SIZE = 0x4000
BANK_WINDOW = 0x4000
HRAM_SRC = 0x7C00               # where the bank 2 copy of the HRAM code lives
BRANCHES = (0xC3, 0xC2, 0xCA, 0xD2, 0xDA, 0xCD, 0xC4, 0xCC, 0xD4, 0xDC)

ROM_PROFILES = {
    "cd544132f9d06ca9fe4f552ddc202878": {
        "name": "Legion of Evil (Rev 1)",
        "rom_size": 0x10000,
        "code_bank": 2,
        # (offset, stock, patched): MBC1 -> +RAM+BATTERY, 32 KB -> 64 KB, no RAM -> 8 KB
        "header": [(0x143, 0x00, 0x80), (0x147, 0x00, 0x03), (0x148, 0x00, 0x01), (0x149, 0x00, 0x02)],
        # Bank 0 bytes the game never reads: (start, end, md5 of the stock bytes)
        "filler": [
            (0x0048, 0x0080, "74444b7e7b01632f3277365c8ca35ec2"),
            (0x00CE, 0x0100, "be581b8c27c28a84b5fe49d1cbc831ff"),
            (0x01E1, 0x0200, "3498b0e2e50d0de1f6c63c5d7e4fac22"),
        ],
        # Each gbt_play call loads HL with (bank, n); the bank byte is 2 in stock.
        "music_bank_loads": [0x0216, 0x022F, 0x19C7, 0x1A19, 0x31E1, 0x56CE, 0x595E],
        "consts": {},        # BUILD_LO, BUILD_HI are added when assembling
        # (what, offset, stock bytes, stub label). Each call or instruction
        # is replaced by a 3-byte call to the stub that does the same and
        # then runs the new code; shorter stock bytes are padded with nops.
        # The game's scroll and palette writes go to HRAM shadows ($FF94-$FF98)
        # that the VBlank hook copies to the hardware. (offset, stock bytes, shadow)
        "shadow_writes": [
            (0x0173, "e042", 0x95), (0x0175, "e043", 0x94),
            (0x2EF2, "e043", 0x94), (0x2EF6, "e042", 0x95),
            (0x3BA1, "f043", 0x94), (0x3BA4, "e043", 0x94),
            (0x3BBC, "f043", 0x94), (0x3BBF, "e043", 0x94),
            (0x3BD3, "f042", 0x95), (0x3BD6, "e042", 0x95),
            (0x3BEE, "f042", 0x95), (0x3BF1, "e042", 0x95),
            (0x0193, "e047", 0x96), (0x0195, "e048", 0x97), (0x0199, "e049", 0x98),
            (0x56E8, "e047", 0x96), (0x56EC, "e048", 0x97), (0x56F0, "e049", 0x98),
        ],
        # The VBlank handler's "call $FF80" (the OAM DMA routine)
        "vblank_dma": (0x00A4, "cd80ff"),
        "hooks": [
            ("boot: after the WRAM defaults copy", 0x01B0, "cdeb7f", "t_boot"),
            ("title: joypad read", 0x57C5, "cdb27b", "t_joy"),
            ("run loop: joypad read", 0x58BB, "cdb27b", "t_joy"),
            ("store: buy routine", 0x5ABB, "cdcf22", "t_buy"),
            ("game over screen", 0x5947, "cd7519", "t_over"),
            ("frame wait", 0x7AF8, "f040e680", "t_wait"),
            ("the non-fatal hit", 0x4ACC, "21d0c7", "t_hit"),
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


def check_no_branches_into(rom, address, span, what):
    """Nothing may jump or call into the middle of code that is being replaced."""
    targets = {address + k for k in range(1, span)}
    for i in range(0, min(len(rom), 0x8000) - 2):
        if rom[i] in BRANCHES and (rom[i + 1] | rom[i + 2] << 8) in targets:
            raise SystemExit(f"{what}: {rom[i:i + 3].hex()} at {i:#07x} branches into it")


def assemble_sections(profile):
    """The patch's routines: ([(cpu address, file offset, bytes)], labels).

    loe.asm is split by "; ==== org NAME ====" lines. NAME is a bank 0 filler
    ("stub_a" ...) or "bank2", the code bank's window at $4000."""
    path = os.path.join(HERE, "loe.asm")
    if not os.path.exists(path):
        return [], {}
    text = open(path).read()
    sections = re.split(r"^; ==== org (\w+) ====\n", text, flags=re.M)
    header, pairs = sections[0], list(zip(sections[1::2], sections[2::2]))
    origins = {"stub_a": 0x0048, "stub_b": 0x00CE, "stub_c": 0x01E1, "bank2": BANK_WINDOW, "hram": 0xFF99}
    consts = dict(profile["consts"], BUILD_LO=0, BUILD_HI=0, hram_src=HRAM_SRC, hram_len=0)
    for attempt in range(2):
        # A saved run holds return addresses, so a snapshot is only good for the
        # build that made it. The id is a sum of the addresses it depends on.
        a = asm.Assembler()
        pre = "\n".join(f"{k:<12} = ${v:04X}" for k, v in consts.items()) + "\n\n"
        out = _assemble_all(a, pre, header, pairs, origins, profile)
        hram_len = len(next(c for o, _, c in out if o == 0xFF99))
        if attempt == 0:
            consts["hram_len"] = hram_len
            ids = [a.labels[n] for n in ("t_joy", "t_wait", "joy_hook", "run_logic", "pause_menu", "suspend")]
            build = sum((i + 1) * v for i, v in enumerate(ids)) & 0xFFFF
            consts["BUILD_LO"], consts["BUILD_HI"] = build & 0xFF, build >> 8
    return out, a.labels


def _assemble_all(a, pre, header, pairs, origins, profile):
    for name, body in pairs:
        try:
            a.assemble(pre + header + body, origins[name])     # collects labels; forward references fail
        except asm.AsmError:
            pass
    out = []
    for name, body in pairs:
        org = origins[name]
        code = a.assemble(pre + header + body, org)
        if org == 0xFF99:                   # runs from HRAM; stored in the code bank
            offset = profile["code_bank"] * BANK_SIZE + HRAM_SRC - BANK_WINDOW
        else:
            offset = org if org < BANK_WINDOW else profile["code_bank"] * BANK_SIZE + org - BANK_WINDOW
        out.append((org, offset, code))
    return out


def patch(rom_bytes, verbose=True):
    rom = bytearray(rom_bytes)
    profile = load_profile(rom_bytes)
    say = print if verbose else (lambda *a, **k: None)
    say(f"ROM: {profile['name']}")

    for start, end, md5 in profile["filler"]:
        if hashlib.md5(rom_bytes[start:end]).hexdigest() != md5:
            raise SystemExit(f"filler {start:#06x}-{end:#06x} is not what the profile expects")
    if len(rom) > profile["rom_size"]:
        raise SystemExit("the ROM is already larger than the patched size")
    rom.extend(b"\xFF" * (profile["rom_size"] - len(rom)))

    for at in profile["music_bank_loads"]:
        # ld hl,$0n02: the low byte, 2, is the music bank; the high byte is the song count
        check_bytes(rom_bytes, at - 8, b"\x21\x02", "music call's bank load")
        rom[at - 7] = 0x01
    say(f"music player bank 2 -> 1 at {len(profile['music_bank_loads'])} calls")

    pieces, labels = assemble_sections(profile)
    for org, offset, code in pieces:
        if org == 0xFF99:
            pass
        elif org < BANK_WINDOW:
            end = org + len(code)
            if not any(s <= org and end <= e for s, e, _ in profile["filler"]):
                raise SystemExit(f"the code at ${org:04X}-${end - 1:04X} is outside the filler")
        elif any(b != 0xFF for b in rom[offset:offset + len(code)]):
            raise SystemExit("the code bank is not empty where the code goes")
        rom[offset:offset + len(code)] = code
        say(f"injected {len(code)} bytes at ${org:04X} (file {offset:#07x})")

    for what, at, old, label in profile["hooks"]:
        old = bytes.fromhex(old)
        check_bytes(rom_bytes, at, old, what)
        check_no_branches_into(rom_bytes, at, len(old), what)
        target = labels[label]
        rom[at:at + len(old)] = bytes([OP_CALL, target & 0xFF, target >> 8]) + b"\x00" * (len(old) - 3)
        say(f"{what}: {at:#06x} -> call ${target:04X} {label}")

    for at, old, shadow in profile["shadow_writes"]:
        old = bytes.fromhex(old)
        check_bytes(rom_bytes, at, old, "scroll or palette access")
        rom[at + 1] = shadow
    say(f"scroll and palette accesses -> HRAM shadows: {len(profile['shadow_writes'])} sites")
    at, old = profile["vblank_dma"]
    check_bytes(rom_bytes, at, bytes.fromhex(old), "VBlank handler's OAM DMA call")
    rom[at + 1], rom[at + 2] = labels["isr_ext"] & 0xFF, labels["isr_ext"] >> 8
    say(f"VBlank handler's OAM DMA call -> call ${labels['isr_ext']:04X} isr_ext (HRAM)")

    for at, was, now in profile["header"]:
        if rom_bytes[at] != was:
            raise SystemExit(f"header byte {at:#05x} is {rom_bytes[at]:#04x}, expected {was:#04x}")
        rom[at] = now
    rom[OFF_HDR_SUM] = header_checksum(rom)
    g = global_checksum(rom)
    rom[OFF_GLOBAL_SUM], rom[OFF_GLOBAL_SUM + 1] = g >> 8, g & 0xFF
    say(f"header: MBC1+RAM+BATTERY, 64 KB, 8 KB RAM; checksums repaired (global {g:#06x})")
    return bytes(rom)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rom", help="stock Legion of Evil ROM")
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
