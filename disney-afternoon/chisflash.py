#!/usr/bin/env python3
"""Build the Disney Afternoon Collection for a ChisFlash MAX 16-in-1 cart.

That cart only does MBC5 banking, which always shows bank 0 at $0000, so the
MBC1 collection's way of starting a game can't work there. Instead the cart's
CPLD can reset the console into any of its 16 slots, each holding one game as
its own cart. This build puts the same splash and menu in the cart's menu slot,
and the four games, converted to MBC5, in slots 0 to 3. Picking a game resets
the console into its slot, so it starts cold, exactly like its own cart.

Inputs are the same, checked by md5, as for build.py:

    python3 chisflash.py DUCKTALES DUCKTALES2 TALESPIN DARKWING bundleMain.mbundle -o out.gb
"""
import argparse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build, mbundle
from asm import assemble
from build import BANK, GAMES, consts, db_lines, src, header_checksum, global_checksum

MIB = 0x100000
MENU_SIZE = 0x40000          # the menu ROM: 16 banks, 256 KiB
IMAGE_SIZE = 8 * MIB         # through the end of slot 3; later slots are left alone
MBC5 = 0x19                  # cartridge type: MBC5, no RAM

# TaleSpin switches banks through one routine at $02C7, sometimes with bank 0.
# MBC1 turns 0 into 1 there, MBC5 doesn't, so the routine jumps to a copy in bank
# 0's free padding that does the same, leaving A and the flags as they were.
TS_ROUTINE = 0x02C7
TS_ROUTINE_BYTES = bytes([0xEA, 0xB8, 0xC0, 0xEA, 0x00, 0x21, 0xC9])   # ld ($C0B8),a / ld ($2100),a / ret
TS_PATCH = 0x0070
TS_PATCH_BYTES = bytes([
    0xEA, 0xB8, 0xC0,        # ld ($C0B8),a     the game's copy of the bank, as before
    0xF5,                    # push af
    0xA7,                    # and a
    0x20, 0x01,              # jr nz,+1
    0x3C,                    # inc a            bank 0 means bank 1, as on MBC1
    0xEA, 0x00, 0x21,        # ld ($2100),a
    0xF1,                    # pop af
    0xC9,                    # ret
])


def slot_offset(slot):
    """Where a game slot starts in the cart's flash: slot 0 is 1 MiB at 1 MiB, then 2 MiB each."""
    return MIB if slot == 0 else slot * 2 * MIB


def slot_size(slot):
    return MIB if slot == 0 else 2 * MIB


def to_mbc5(rom, key):
    """The game as an MBC5 cart. All four only write banks 1 to 7 to the $2000 register,
    which MBC5 treats as MBC1 does, apart from TaleSpin's bank 0."""
    out = bytearray(rom)
    if key == 'talespin':
        if rom[TS_ROUTINE:TS_ROUTINE + len(TS_ROUTINE_BYTES)] != TS_ROUTINE_BYTES:
            sys.exit('TaleSpin: the bank-switch routine is not where expected')
        if any(rom[TS_PATCH:TS_PATCH + len(TS_PATCH_BYTES)]):
            sys.exit('TaleSpin: the padding for the patch is not free')
        out[TS_PATCH:TS_PATCH + len(TS_PATCH_BYTES)] = TS_PATCH_BYTES
        out[TS_ROUTINE:TS_ROUTINE + 3] = bytes([0xC3, TS_PATCH & 0xFF, TS_PATCH >> 8])   # jp TS_PATCH
    out[0x147] = MBC5
    out[0x14D] = header_checksum(out)
    out[0x14E:0x150] = global_checksum(out).to_bytes(2, 'big')
    return bytes(out)


def build_code():
    """Assemble the boot code, loader, launch stub and menu for the menu ROM.

    Returns (boot, menu, labels); labels merges the menu's and the launch stub's.
    """
    common = consts(MENU_BANK=build.MENU_BANK, MENU_STACK=build.MENU_STACK,
                    SAVED_REGS=build.SAVED_REGS)
    boot, _, _ = assemble(common + src('boot.asm'), build.DT_START)
    loader, _, _ = assemble(common + src('loader.asm'), build.LOADER)
    launch, lab, _ = assemble(common + src('chis_stub.asm'), build.LAUNCH)
    menu_src = (common + consts(
        SPLASH_BANK=build.SPLASH_BANK, FIRST_GAME_BANK=build.FIRST_GAME_BANK,
        PROMPT_MAP=0x9800 + 32 * build.pictures.PROMPT_ROW,
        BLINK_FRAMES=build.BLINK_FRAMES, BLINK_CYCLE=2 * build.BLINK_FRAMES,
        LOADER=build.LOADER, LOADER_LEN=len(loader), LAUNCH=build.LAUNCH, LAUNCH_LEN=len(launch),
        P_SLOT=lab['launch'] + 6)
        + src('menu.asm') + src('chis_launch.asm') + db_lines('loader_src', loader)
        + db_lines('launch_src', launch) + db_lines('games', bytes(range(len(GAMES)))))
    menu, menu_lab, _ = assemble(menu_src, 0x4000)
    # the patch point must be the operand the stub was assembled with
    assert launch[5] == 0x3E and launch[8:10] == bytes([0x00, 0xB0]), 'launch stub no longer has ld a,slot / ld ($B000),a'
    assert len(menu) <= BANK
    return boot, menu, {**menu_lab, **lab}


def menu_rom(roms, art):
    """The menu slot's ROM: header and boot in bank 0, the menu and screens where the
    MBC1 collection has them."""
    boot, menu, _ = build_code()
    out = bytearray([0xFF] * MENU_SIZE)
    out[0x0000:0x4000] = bytes(0x4000)
    out[0x100:0x104] = bytes([0x00, 0xC3]) + build.DT_START.to_bytes(2, 'little')   # nop / jp boot
    out[0x104:0x150] = roms[0][0x104:0x150]           # Nintendo logo and DuckTales' header fields
    out[build.DT_START:build.DT_START + len(boot)] = boot
    b = build.MENU_BANK
    out[b * BANK:b * BANK + len(menu)] = menu
    for i, img in enumerate(build.screens(roms, art)):
        blob = build.screen_bank(img)
        b = build.SPLASH_BANK + i
        out[b * BANK:b * BANK + len(blob)] = blob
    # Header: our title, MBC5 without RAM, 256 KiB, Capcom's licensee as on the MBC1
    # collection, so a CGB gives the menu the same palette.
    out[0x134:0x144] = b'DISNEYAFTERNOON\x00'
    out[0x147] = MBC5
    out[0x148] = 0x03
    out[0x149] = 0x00
    out[0x14D] = header_checksum(out)
    out[0x14E:0x150] = global_checksum(out).to_bytes(2, 'big')
    return bytes(out)


def build_image(roms, art):
    """The flash image: the menu at 0, then each game in its slot."""
    out = bytearray([0xFF] * IMAGE_SIZE)
    menu = menu_rom(roms, art)
    out[:len(menu)] = menu
    for slot, (g, rom) in enumerate(zip(GAMES, roms)):
        game = to_mbc5(rom, g['key'])
        assert len(game) <= slot_size(slot)
        out[slot_offset(slot):slot_offset(slot) + len(game)] = game
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for g in GAMES:
        ap.add_argument(g['key'], help=f"{g['label']} (USA) ROM")
    ap.add_argument('bundle', help='bundleMain.mbundle from the PC Disney Afternoon Collection')
    ap.add_argument('-o', '--out', required=True)
    a = ap.parse_args()
    roms = [build.load_checked(getattr(a, g['key']), g['md5'], g['label'] + ' (USA)') for g in GAMES]
    build.load_checked(a.bundle, build.BUNDLE_MD5, 'bundleMain.mbundle')
    image = build_image(roms, mbundle.read(a.bundle))
    open(a.out, 'wb').write(image)
    print(f'wrote {a.out} ({len(image) // MIB} MiB), md5 {build.md5(image)}')


if __name__ == '__main__':
    main()
