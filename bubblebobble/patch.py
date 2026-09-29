#!/usr/bin/env python3
"""Remember the last round started in Bubble Bobble (Game Boy), and offer its
password on the PASSWORD screen.

  1. Assembles bb1save.asm: the round save and the SRAM switches into the run
     of unused bytes between the interrupt vectors and the header in bank 0,
     and the PASSWORD screen's two routines into the unused end of bank 3.
  2. Saves the round and the password flags on every round load.
  3. Pre-fills the PASSWORD screen with the saved round's password, made by
     the game's own encoder.
  4. Marks the header MBC1+RAM+BATTERY with 8 KB of RAM and repairs both
     checksums.

It refuses any ROM it has no profile for and checks every byte it replaces
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
IPS_RLE_MIN = 12               # shortest run of one byte that an RLE record beats
IPS_EOF_OFFSET = 0x454F4F
BANK_SIZE = 0x4000
OP_CALL = 0xCD
PF_MARKER = "; ==== org PF_ORG ===="

ROM_PROFILES = {
    "11c49d405eef2174d9c14682204bb458": {
        "name": "Bubble Bobble (USA, Europe)",
        "save_org": 0x0061,             # bank 0, between the vectors and the header
        "save_padding": (0x0061, 0x0100),       # all $FF
        "pf_bank": 3,                   # the PASSWORD screen's bank
        "pf_org": 0x7800,
        "pf_padding": (0x771B, 0x7F00),         # all $FF
        "header": {0x147: (0x01, 0x03),         # MBC1 -> MBC1+RAM+BATTERY
                   0x149: (0x00, 0x02)},        # no RAM -> 8 KB
        # (bank, address, stock bytes, label): each becomes a call
        "hooks": [(0, 0x1848, "2180dc", "save_round"),   # ld hl,$DC80, the round loader's first instruction
                  (3, 0x7104, "ea13c9", "pf_init"),      # ld (SLOT),a in the PASSWORD screen's setup
                  (3, 0x7129, "fa1cc9", "pf_step")],     # ld a,(PW_FLAGS) in its per-frame code
        "wram": [0xD780],
        "consts": {
            "ROUND": 0xC200,            # round - 1
            "ROUNDS": 100,
            "FLAGS_A": 0xC4B5, "FLAGS_B": 0xC202,       # OR'd, as the game-over password does
            "LOADER_HL": 0xDC80,
            "ENCODE": 0x7650,           # bank 3: D = round, E = flags -> four letter tiles at SHOWN
            "SHOWN": 0xC918,
            "BUFFER": 0xC914,           # the four letters typed, which A on END checks
            "SLOT": 0xC913,             # the slot the next letter goes in
            "PW_FLAGS": 0xC91C,
            "DRAW_SLOTS": 0x7391,       # bank 3: queue the four slots for VBlank
            "MARK_X": 0xC109, "MARK_X2": 0xC10D,        # the slot marker's two sprites
            "HAND_Y": 0xC110, "HAND_X": 0xC111,         # the hand's two sprites
            "HAND_Y2": 0xC114, "HAND_X2": 0xC115,
            "HAND_END_Y": 124, "HAND_END_X": 68,        # the hand on END
            "HAND_COL": 0xC912,         # the hand's grid X, kept while it is below the grid
            "MENU": 0xC911, "MENU_END": 24,             # the grid position of END
            "SRAM": 0xA000, "SRAM_ENABLE": 0x0000,
            "SIG_1": 0xB0, "SIG_2": 0xB1, "SUM_XOR": 0xA5,
            "PF_PENDING": 0xD780,       # WRAM the game never names or uses; the boot clears it
        },
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



def file_offset(bank, address):
    return bank * BANK_SIZE + address - BANK_SIZE if bank else address


def assemble(profile, source=None):
    """(bank 0 code, bank 3 code, labels), from bb1save.asm or the given source."""
    text = source if source is not None else open(os.path.join(HERE, "bb1save.asm")).read()
    if text.count(PF_MARKER) != 1:
        raise SystemExit("bb1save.asm needs exactly one PF_ORG section")
    first, second = text.split(PF_MARKER)
    consts = "\n".join(f"{k:<12} = ${v:04X}" for k, v in profile["consts"].items()) + "\n"
    head = f"; ==== generated from the ROM profile: {profile['name']} ====\n" + consts
    code0, labels0, _ = asm.assemble(head + f"SAVE_ORG     = ${profile['save_org']:04X}\n" + first,
                                     org=profile["save_org"])
    if labels0["save_end"] - profile["save_org"] != len(code0):
        raise SystemExit("assembled size does not match the bank 0 labels")
    shared = "".join(f"{k} = ${labels0[k]:04X}\n" for k in ("sram_on", "sram_off"))
    code3, labels3, _ = asm.assemble(head + shared + second, org=profile["pf_org"])
    if labels3["pf_end"] - profile["pf_org"] != len(code3):
        raise SystemExit("assembled size does not match the bank 3 labels")
    return code0, code3, {**labels0, **labels3}


def place(rom, original, bank, org, padding, code, what, say):
    lo, hi = padding
    if any(b != 0xFF for b in original[file_offset(bank, lo):file_offset(bank, hi)]):
        raise SystemExit(f"{what}: the unused bytes are not all $FF")
    if not (lo <= org and org + len(code) <= hi):
        raise SystemExit(f"{what}: {len(code)} bytes do not fit ${lo:04X}-${hi - 1:04X}")
    f = file_offset(bank, org)
    rom[f:f + len(code)] = code
    say(f"injected {len(code)} bytes at bank {bank} ${org:04X} ({what})")


def patch(rom_bytes, verbose=True, source=None):
    rom = bytearray(rom_bytes)
    profile = load_profile(rom_bytes)
    say = print if verbose else (lambda *a, **k: None)
    say(f"ROM: {profile['name']}")

    code0, code3, labels = assemble(profile, source)
    place(rom, rom_bytes, 0, profile["save_org"], profile["save_padding"], code0, "round save", say)
    place(rom, rom_bytes, profile["pf_bank"], profile["pf_org"], profile["pf_padding"], code3,
          "PASSWORD screen", say)

    for w in profile["wram"]:
        for i in range(len(rom_bytes) - 2):
            if rom_bytes[i] in (0xFA, 0xEA, 0x21, 0x11, 0x01) and abs((rom_bytes[i + 1] | rom_bytes[i + 2] << 8) - w) <= 16:
                raise SystemExit(f"the game names ${rom_bytes[i + 1] | rom_bytes[i + 2] << 8:04X}, near the patch's ${w:04X}")

    for bank, address, stock, label in profile["hooks"]:
        f = file_offset(bank, address)
        check_bytes(rom_bytes, f, bytes.fromhex(stock), f"hook for {label}")
        a = labels[label]
        rom[f:f + 3] = bytes([OP_CALL, a & 0xFF, a >> 8])
        say(f"bank {bank} ${address:04X} -> call ${a:04X} {label}")

    for at, (was, now) in profile["header"].items():
        if rom_bytes[at] != was:
            raise SystemExit(f"header byte {at:#05x} is {rom_bytes[at]:#04x}, expected {was:#04x}")
        rom[at] = now
    rom[OFF_HDR_SUM] = header_checksum(rom)
    g = global_checksum(rom)
    rom[OFF_GLOBAL_SUM], rom[OFF_GLOBAL_SUM + 1] = g >> 8, g & 0xFF
    say(f"header: MBC1+RAM+BATTERY, 8 KB RAM; header checksum {rom[OFF_HDR_SUM]:#04x}, global checksum {g:#06x}")
    return bytes(rom)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rom", help="stock Bubble Bobble ROM")
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
