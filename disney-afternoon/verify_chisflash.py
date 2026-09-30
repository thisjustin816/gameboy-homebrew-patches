#!/usr/bin/env python3
"""Check a ChisFlash MAX image against the four stock ROMs in PyBoy.

    python3 verify_chisflash.py IMAGE DUCKTALES DUCKTALES2 TALESPIN DARKWING bundleMain.mbundle

PyBoy has no ChisFlash CPLD, so the menu and the games are checked apart:

1. The image is exactly what chisflash.py makes. The menu ROM's header is valid
   and says MBC5, and each slot holds its game, changed only in the header and,
   in TaleSpin, the bank-switch patch.
2. The menu ROM, run as an MBC5 cart, shows the splash and all four menu screens
   as built, PRESS START blinks and the cursor wraps, as in verify.py.
3. Picking each game leaves the launch stub in HRAM with that game's slot, and the
   stub makes the writes the cart's CPLD takes as "reset into this slot".
4. Each game, converted to MBC5 and run as its own cart, matches the stock ROM on
   every frame of the same scripted play as verify.py, on a DMG and on a Game Boy
   Color. As a control, TaleSpin converted without its patch must not match.
"""
import sys
import build, chisflash, mbundle, verify
from verify import check, emu, done, press

STUB = [0x3E, 0x40, 0xEA, 0x00, 0x40,           # ld a,$40 / ld ($4000),a   arm
        0x3E, None, 0xEA, 0x00, 0xB0,           # ld a,slot / ld ($B000),a  pick the slot
        0x3E, 0x01, 0xEA, 0x00, 0xA0,           # ld a,1 / ld ($A000),a     switch to it
        0xAF, 0xEA, 0x00, 0x40,                 # xor a / ld ($4000),a      reset
        0x18, 0xFE]                             # jr $                      wait for it


def stub_for(slot):
    return bytes(slot if b is None else b for b in STUB)


def static_checks(image, roms, art):
    check(image == chisflash.build_image(roms, art), 'image is exactly what chisflash.py makes')
    menu = image[:chisflash.MENU_SIZE]
    check(menu[0x147] == chisflash.MBC5 and menu[0x148] == 0x03 and menu[0x149] == 0,
          'menu header: 256 KiB, MBC5, no RAM')
    check(menu[0x104:0x134] == roms[0][0x104:0x134], 'menu has the Nintendo logo')
    check(menu[0x14D] == build.header_checksum(menu), 'menu header checksum')
    patch = set(range(chisflash.TS_PATCH, chisflash.TS_PATCH + len(chisflash.TS_PATCH_BYTES)))
    patch |= set(range(chisflash.TS_ROUTINE, chisflash.TS_ROUTINE + 3))
    for slot, (g, rom) in enumerate(zip(build.GAMES, roms)):
        base = chisflash.slot_offset(slot)
        game = image[base:base + len(rom)]
        allowed = {0x147, 0x14D, 0x14E, 0x14F} | (patch if g['key'] == 'talespin' else set())
        diff = [i for i in range(len(rom)) if game[i] != rom[i] and i not in allowed]
        check(not diff and game[0x147] == chisflash.MBC5 and game[0x14D] == build.header_checksum(game),
              f"slot {slot} holds {g['label']} as MBC5, otherwise unchanged"
              + (f' (first diff at {diff[0]:#x})' if diff else ''))


def launch_checks(menu, go):
    for sel, g in enumerate(build.GAMES):
        pb = emu(menu)
        hit = []
        pb.hook_register(build.MENU_BANK, go, lambda c: hit.append(bytes(pb.memory[build.LAUNCH:build.LAUNCH + len(STUB)])), None)
        pb.tick(verify.BOOT_WAIT, True)
        press(pb, 'start', 30)
        for _ in range(sel):
            press(pb, 'down')
        pb.button('a', 3)
        for _ in range(120):
            pb.tick(1, True)
            if hit:
                break
        done(pb)
        check(bool(hit) and hit[0] == stub_for(sel),
              f"picking {g['label']} readies a reset into slot {sel}")


def play_checks(roms, cgb, games):
    """games: (name, stock ROM, converted ROM, should match)."""
    tag = 'CGB' if cgb else 'DMG'
    for i, (name, rom, conv, should) in enumerate(games):
        script = verify.input_script(1000 + i)
        want = verify.run(rom, None, 0, cgb, script, verify.PLAY_FRAMES)
        got = verify.run(conv, None, 0, cgb, script, verify.PLAY_FRAMES)
        if got is None:
            check(not should, f'{tag} {name}: the converted game hung')
            continue
        bad = [f for f in range(10, verify.PLAY_FRAMES) if got[f] != want[f]]
        if should:
            check(not bad, f'{tag} {name}: {verify.PLAY_FRAMES - 10} frames of play match stock'
                           + (f'; first mismatch at frame {bad[0]}' if bad else ''))
        else:
            check(bool(bad), f'{tag} {name}: differs from stock, as it should'
                             + (f' (from frame {bad[0]})' if bad else ''))


def main():
    if len(sys.argv) != 7:
        sys.exit(__doc__)
    image = open(sys.argv[1], 'rb').read()
    roms = [build.load_checked(p, g['md5'], g['label']) for p, g in zip(sys.argv[2:6], build.GAMES)]
    build.load_checked(sys.argv[6], build.BUNDLE_MD5, 'bundleMain.mbundle')
    art = mbundle.read(sys.argv[6])
    static_checks(image, roms, art)
    menu = image[:chisflash.MENU_SIZE]
    verify.menu_checks(menu, build.screens(roms, art))
    launch_checks(menu, chisflash.build_code()[2]['go'])
    games = []
    for slot, (g, rom) in enumerate(zip(build.GAMES, roms)):
        base = chisflash.slot_offset(slot)
        games.append((g['label'], rom, image[base:base + len(rom)], True))
    # the control: MBC5 without the fix, which reads bank 0 where TaleSpin wants bank 1
    ts = bytearray(roms[2])
    ts[0x147] = chisflash.MBC5
    ts[0x14D] = build.header_checksum(ts)
    games.append(('TALESPIN without its patch', roms[2], bytes(ts), False))
    for cgb in (False, True):
        play_checks(roms, cgb, games)
    print(f'\n{len(verify.failures)} failure(s)' if verify.failures else '\nall checks pass')
    sys.exit(1 if verify.failures else 0)


if __name__ == '__main__':
    main()
