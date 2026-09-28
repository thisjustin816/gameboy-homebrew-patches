#!/usr/bin/env python3
"""Add resume-a-run saving to Roguecraft GB.

The game already has the whole mechanism - GB Studio save slots, a
RESUME GAME option, and a resume that restarts the saved floor with the hero
carried over. It never writes the run slot on the way into a floor. This adds
that write, and fixes three bugs along the way:

  1. Assemble roguesave.asm into an empty ROM bank.
  2. Repoint each floor script's native call to the floor setup (bank 2
     $401B) at that code, which runs the stock setup and then the game's own
     data_save(0).
  3. Chest counts: skip the last floor's unreachable layout in the chest
     total, and bring an opened chest back as its gold, not shut, when you
     re-enter its room (apply_chest_fixes).
  4. Mini-map: put back the enemies the map hid even when the close falls
     inside the game's post-attack animation lock (apply_map_fix).
  5. Title screen: redraw the version, v1.0000, as v1.000+ to mark the
     patched build (apply_title_version).
  6. Repair the global checksum. The header is untouched: the cartridge
     already declares 32 KB of battery-backed RAM.

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

BANK_SIZE = 0x4000
OP_VM_CALL_NATIVE = 0x2D
# The bytes around every floor script's call to the setup, as a sanity check
# that each site is the instruction it should be, not data that happens to
# look like it.
SITE_BEFORE = bytes.fromhex("635a060202")
SITE_AFTER = bytes.fromhex("1815fe0005")
CARD_WINDOW = 0x300          # how far after the call a floor script shows its card

ROM_PROFILES = {
    "6de80f13b9ab562de2227ea5dd818275": {
        "name": "Roguecraft GB v1.0000 (Rocketship Park)",
        "consts": {
            "BANKED_CALL": 0x3E01,      # ld e,bank / ld hl,fn / call - the engine's far call
            "SETUP_BANK": 0x02, "SETUP_FN": 0x401B,   # floor setup: hero <- variables
            "SAVE_BANK": 0x14, "SAVE_FN": 0x44E7,     # data_save(slot)
            "FLOOR": 0xCC4D,            # variable 75, the floor index
            # chest bookkeeping
            "FINAL_FLOOR": 10,          # It Waits Dreaming: one boss arena
            "CHESTS_TOTAL": 0xCCE5,     # variable 151
            "CHESTS_FOUND": 0xCCE7,     # variable 152
            "ROOM_COL": 0xCBCD,         # variable 11, current room column
            "ROOM_ROW": 0xCBCF,         # variable 12, current room row
            "ROOM_ITEMS": 0xD9BD,       # 25 words of item bits, by 5 * row + column
            "CHEST_HP": 0xDC4A,         # the chest entity's hp: 2 shut, 1 its gold
            "CHEST_SHUT": 2,
            "CHESTS_OPENED": 0xDD4A,    # 4 bytes of WRAM: a bit per room, chest opened this floor
            # mini-map
            "MAP_BANK": 0x02,
            "MAP_OPEN_FN": 0x5876,      # hide the entities under the map
            "MAP_HIDE_FN": 0x5903,      # one entity -> its empty animation set
            "MAP_CLOSE_FN": 0x58E3,     # refresh every entity
            "REFRESH_FN": 0x5972,       # (entity, 0): reload its animation set
            "ATTACK_LOCK": 0xDD1D,      # frames left in which REFRESH_FN skips enemies
            "ENTITY_COUNT": 0xDCC9,
            "ENTITY_ACTOR": 0xDCA3,     # entity -> actor index
            "ACTORS": 0xC0D1,           # 52-byte actor structs
            "ACTOR_FRAME_START": 0x0C,
            "ACTOR_ANIMS": 0x12,        # the actor's current animation set
            "MAX_ENTITIES": 19,         # the length of the entity tables
            "MAP_HIDDEN": 0xDD37,       # 19 bytes of WRAM nothing else uses
        },
        "hook_bank": 27,                # empty in the stock ROM
        "hook_org": 0x4000,
        # ROM offsets of the VM_CALL_NATIVE opcode in each floor script
        "call_sites": [0x244B8, 0x30E2C, 0x317B7, 0x32146, 0x3310B, 0x33A9A,
                       0x34BCB, 0x35558, 0x35F15, 0x368A2, 0x3722F],
        # The floors come in a fixed order; the first is always this one, and
        # its script is the one site that goes to run_start.
        "first_floor_site": 0x30E2C,
        "first_floor_card": b"- the wilderness -",
        # 13-byte counter increments replaced by a banked call (8) + 5 nops
        "counter_sites": [
            (0x116CE, bytes.fromhex("21e5cc2a4f460321e5cc792270"), "count_chest"),   # bank 4 $56CE
            (0x0A44A, bytes.fromhex("21e7cc2a4f460321e7cc792270"), "chest_opened"),  # bank 2 $644A
        ],
        # room entry: `if (items & 2) chest hp = 2` (bank 2 $44F5-$4507)
        "chest_spawn_site": (0x084F5, bytes.fromhex("f87d2ae6024f060079d602b0200521" "4adc3602")),
        # the map script's two native calls (bank 25 $6036, $609C)
        "map_natives": [(0x66036, "MAP_OPEN_FN", "map_open"),
                        (0x6609C, "MAP_CLOSE_FN", "map_close")],
        # the stock map-open's banked call to MAP_HIDE_FN (bank 2 $58D6)
        "map_hide_call": 0x098D6,
        # The title background's tilemap and attribute map (bank 23 $61B1,
        # $6035), 20 x 19 cells
        "title_map": (0x5E1B1, 0x5E035, 20, 19),
        # The version, drawn into the title background at row 17, columns
        # 16-19, in palette 3: 1 is the text, 3 the background, 2 dither.
        # Only the last tile changes: its last 0 becomes a +.
        # (ROM offset, row, column, stock rows, new rows)
        "version_tiles": [
            (0x2E978, 17, 19,                  # bank 11 $6978: the end of a 0, then 0 -> +; the art on the right stays
             ["33333331", "11311131", "31313131", "31313131",
              "31313132", "11311133", "33333333", "33333312"],
             ["33333331", "11333331", "31331331", "31311131",
              "31331332", "11333333", "33333333", "33333312"]),
        ],
    },
}

OFF_HDR_SUM = 0x14D
OFF_GLOBAL_SUM = 0x14E
MAX_IPS_RECORD = 0xFFFF
IPS_MERGE_GAP = 8
IPS_EOF_OFFSET = 0x454F4F


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
            f"unrecognised ROM (md5 {md5}); this patch only knows "
            + ", ".join(p["name"] for p in ROM_PROFILES.values()))
    return ROM_PROFILES[md5]


def banked_call(bank, addr, trampoline):
    """ld e,bank / ld hl,addr / call trampoline"""
    return bytes([0x1E, bank, 0x21, addr & 0xFF, addr >> 8,
                  0xCD, trampoline & 0xFF, trampoline >> 8])


def apply_chest_fixes(rom, original, profile, labels, say):
    c = profile["consts"]
    hook_bank, tramp = profile["hook_bank"], c["BANKED_CALL"]

    for off, expect, label in profile["counter_sites"]:
        if original[off:off + len(expect)] != expect:
            raise SystemExit(f"counter increment at {off:#07x} is not the expected code")
        if original.count(expect) != 1:
            raise SystemExit(f"counter increment at {off:#07x} is not unique")
        call = banked_call(hook_bank, labels[label], tramp)
        rom[off:off + len(expect)] = call + bytes(len(expect) - len(call))
        say(f"counter at {off:#07x} -> {label} (${labels[label]:04X})")

    # The room entry's `if (items & 2) chest hp = 2`, as
    #   ld hl,sp+125 / ld a,(hl) / and 2 / jr z,+8 / call chest_spawn / nop x4
    # The item word it tests is the same local the stock code reads.
    off, expect = profile["chest_spawn_site"]
    if original[off:off + len(expect)] != expect or original.count(expect) != 1:
        raise SystemExit(f"the room entry's chest spawn is not at {off:#07x}")
    if expect[14:17] != bytes([0x21, c["CHEST_HP"] & 0xFF, c["CHEST_HP"] >> 8]) or expect[18] != c["CHEST_SHUT"]:
        raise SystemExit("the room entry's chest spawn does not set the chest's hp as expected")
    new = bytes.fromhex("f87d7ee6022808") + banked_call(hook_bank, labels["chest_spawn"], tramp)
    rom[off:off + len(expect)] = new + bytes(len(expect) - len(new))
    say(f"room entry's chest spawn at {off:#07x} -> chest_spawn (${labels['chest_spawn']:04X})")


def apply_map_fix(rom, original, profile, labels, say):
    c = profile["consts"]
    hook_bank, tramp = profile["hook_bank"], c["BANKED_CALL"]

    for off, fn, label in profile["map_natives"]:
        expect = bytes([OP_VM_CALL_NATIVE, c[fn] >> 8, c[fn] & 0xFF, c["MAP_BANK"]])
        if original[off:off + 4] != expect or original.count(expect) != 1:
            raise SystemExit(f"map script call at {off:#07x} is not the expected native call")
        a = labels[label]
        rom[off + 1:off + 4] = bytes([a >> 8, a & 0xFF, hook_bank])
        say(f"map script native call at {off:#07x} -> {label} (${a:04X})")

    off = profile["map_hide_call"]
    expect = banked_call(c["MAP_BANK"], c["MAP_HIDE_FN"], tramp)
    if original[off:off + 8] != expect or original.count(expect) != 1:
        raise SystemExit(f"the map-open's call to hide an entity is not at {off:#07x}")
    rom[off:off + 8] = banked_call(hook_bank, labels["map_hide"], tramp)
    say(f"map-open's hide call at {off:#07x} -> map_hide (${labels['map_hide']:04X})")

    # The fixes keep a byte per entity (the map) and a bit per room (the
    # chests) in WRAM past the end of the game's data; no instruction in the
    # ROM names any of those addresses.
    lo, hi = c["MAP_HIDDEN"], c["CHESTS_OPENED"] + 4
    for i in range(len(original) - 2):
        if original[i] in (0x01, 0x11, 0x21, 0x31, 0x08, 0xEA, 0xFA) and \
                lo <= (original[i + 1] | original[i + 2] << 8) < hi:
            raise SystemExit(f"ROM offset {i:#07x} refers to the fix's WRAM")


def tile_bytes(rows):
    """8 rows of colour indexes -> a 2bpp tile, leftmost pixel in bit 7"""
    out = bytearray()
    for row in rows:
        lo = hi = 0
        for ch in row:
            lo, hi = lo << 1 | int(ch) & 1, hi << 1 | int(ch) >> 1
        out += bytes([lo, hi])
    return bytes(out)


def apply_title_version(rom, original, profile, say):
    tilemap, attrs, width, height = profile["title_map"]
    # each cell as (tile index, VRAM bank)
    cells = [(original[tilemap + i], original[attrs + i] >> 3 & 1) for i in range(width * height)]
    for off, row, col, old, new in profile["version_tiles"]:
        expect = tile_bytes(old)
        if original[off:off + 16] != expect or original.count(expect) != 1:
            raise SystemExit(f"the title's version tile is not at {off:#07x}")
        # GB Studio shares identical tiles across an image: redrawing one
        # that another cell also uses would change that cell too.
        index, vbank = cells[row * width + col]
        if cells.count((index, vbank)) != 1:
            raise SystemExit(f"title tile {index:#04x} (VRAM bank {vbank}) is not the version text's alone")
        rom[off:off + 16] = tile_bytes(new)
        say(f"title version tile at {off:#07x} (row {row}, column {col}) redrawn")


def patch(rom_bytes, verbose=True):
    rom = bytearray(rom_bytes)
    profile = load_profile(rom_bytes)
    say = print if verbose else (lambda *a, **k: None)
    say(f"ROM: {profile['name']}")

    source = build_preamble(profile) + open(os.path.join(HERE, "roguesave.asm")).read()
    code, labels, _ = asm.assemble(source, org=profile["hook_org"])
    if labels["code_end"] - profile["hook_org"] != len(code):
        raise SystemExit("assembled size does not match the routine's labels")

    base = profile["hook_bank"] * BANK_SIZE + (profile["hook_org"] - 0x4000)
    region = rom[base:base + len(code)]
    if any(b != 0xFF for b in region):
        raise SystemExit(f"bank {profile['hook_bank']} is not empty where the code goes")
    rom[base:base + len(code)] = code
    say(f"injected {len(code)} bytes at bank {profile['hook_bank']} "
        f"${profile['hook_org']:04X} (ROM {base:#07x})")

    c = profile["consts"]
    old_operands = bytes([c["SETUP_FN"] >> 8, c["SETUP_FN"] & 0xFF, c["SETUP_BANK"]])

    def operands(label):
        # VM_CALL_NATIVE's operands, as the stock scripts store them:
        # address high, address low, bank
        a = labels[label]
        return bytes([a >> 8, a & 0xFF, profile["hook_bank"]])

    # Every site must be exactly where the profile says, and nowhere else may
    # hold the same instruction: a missed floor would silently never save.
    needle = SITE_BEFORE + bytes([OP_VM_CALL_NATIVE]) + old_operands + SITE_AFTER
    found = []
    i = rom_bytes.find(needle)
    while i != -1:
        found.append(i + len(SITE_BEFORE))
        i = rom_bytes.find(needle, i + 1)
    if sorted(found) != sorted(profile["call_sites"]):
        raise SystemExit(f"floor-script call sites differ from the profile: found "
                         f"{[hex(f) for f in found]}")
    loose = rom_bytes.count(bytes([OP_VM_CALL_NATIVE]) + old_operands)
    if loose != len(found):
        raise SystemExit(f"{loose} native calls to the setup, but only {len(found)} "
                         f"in recognisable floor scripts")
    # Each floor script shows its name on a card a few hundred bytes after
    # the call; the first floor's must be the one named in the profile, and
    # no other site's may be.
    card = profile["first_floor_card"]
    for off in profile["call_sites"]:
        names_it = rom_bytes.find(card, off, off + CARD_WINDOW) != -1
        if names_it != (off == profile["first_floor_site"]):
            raise SystemExit(f"floor script at {off:#07x} "
                             f"{'shows' if names_it else 'does not show'} the first floor's card")
    for off in profile["call_sites"]:
        label = "run_start" if off == profile["first_floor_site"] else "floor_start"
        rom[off + 1:off + 4] = operands(label)
    say(f"repointed {len(found)} floor-script native calls (bank {c['SETUP_BANK']} "
        f"${c['SETUP_FN']:04X}): first floor -> ${labels['run_start']:04X} run_start, "
        f"{len(found) - 1} more -> ${labels['floor_start']:04X} floor_start")

    apply_chest_fixes(rom, rom_bytes, profile, labels, say)
    apply_map_fix(rom, rom_bytes, profile, labels, say)
    apply_title_version(rom, rom_bytes, profile, say)

    if header_checksum(rom) != rom[OFF_HDR_SUM]:
        raise SystemExit("header checksum no longer matches - the header was touched")
    g = global_checksum(rom)
    rom[OFF_GLOBAL_SUM], rom[OFF_GLOBAL_SUM + 1] = g >> 8, g & 0xFF
    say(f"header unchanged (cart type {rom[0x147]:#04x}, RAM size {rom[0x149]:#04x}); "
        f"global checksum {g:#06x}")
    return bytes(rom)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rom", help="stock Roguecraft GB ROM")
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
