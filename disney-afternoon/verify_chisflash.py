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
   stub opens with the writes the cart's CPLD takes as "switch to this slot".
   Launched from the menu, with the test putting the slot's ROM in place as the
   CPLD's switch does, each game matches its reference on every frame of the same
   scripted play, after the start-up delay the warm start adds.
4. Each game, converted to MBC5 and run as its own cart, matches the stock ROM on
   every frame of the same scripted play as verify.py, on a DMG and on a Game Boy
   Color. TaleSpin is matched against the stock ROM with the same patch, which on
   MBC1 only changes timing: MBC1 turns bank 0 into bank 1 itself.
5. TaleSpin's level-data read at $0E9D takes its bank from $CD9C, which can be 0.
   PyBoy's scripted play doesn't reach that case, so the check sets $CD9C to 0
   before one read and makes sure bank 1 is mapped there, as MBC1 maps it. As a
   control, TaleSpin converted without its patch must show bank 0 there.
6. Each game, padded to its slot as on the cart, and the menu ROM come up the same
   whatever bank the mapper holds at power-on: with bank 0, 2, 3 or 4 to 9 at $4000
   instead of bank 1, the first POWER_ON_FRAMES frames match a start with bank 1.
   A CPLD that resets the console into the slot leaves whatever bank the cart's
   MBC5 mapper holds, and the menu's last bank write is one of its own, 4 to 9,
   unless the stub's write of bank 1 comes first. As a control,
   DuckTales 2 with its first bank write taken out must start differently.
"""
import hashlib, multiprocessing, os, queue, shutil, sys, tempfile
import build, chisflash, mbundle, verify
from pyboy import PyBoy
from verify import check, emu, done, press

POWER_ON_BANKS = (0, 2, 3, 4, 5, 6, 7, 8, 9)
POWER_ON_FRAMES = 1500        # through each game's title screen
DT2_FIRST_BANK_WRITE = 0x02A1 # DuckTales 2's first ld ($2000),a, for the control

# The writes the stub opens with, as the cart's CPLD sees them (see chis_stub.asm).
STUB_WRITES = [0x3E, 0x50, 0xEA, 0x00, 0x40,    # $4000 = $50     arm
               0x3E, None, 0xEA, 0x00, 0xB0,    # $B000 = slot    pick the slot
               0x3E, 0x01, 0xEA, 0x00, 0x20,    # $2000 = 1       bank 1 at $4000
               0xAF, 0xEA, 0x00, 0x30,          # $3000 = 0
               0x3C, 0xEA, 0x00, 0xA0,          # $A000 = 1       switch to the slot
               0xAF, 0xEA, 0x00, 0x40]          # $4000 = 0       disarm


def stub_for(slot):
    stub = chisflash.launch_stub(slot)
    assert stub[:len(STUB_WRITES)] == bytes(slot if b is None else b for b in STUB_WRITES)
    return stub


def static_checks(image, roms, art):
    check(image == chisflash.build_image(roms, art), 'image is exactly what chisflash.py makes')
    menu = image[:chisflash.MENU_SIZE]
    check(menu[0x147] == chisflash.MBC5 and menu[0x148] == 0x03 and menu[0x149] == 0,
          'menu header: 256 KiB, MBC5, no RAM')
    check(menu[0x104:0x134] == roms[0][0x104:0x134], 'menu has the Nintendo logo')
    check(menu[0x14D] == build.header_checksum(menu), 'menu header checksum')
    for slot, (g, rom) in enumerate(zip(build.GAMES, roms)):
        base = chisflash.slot_offset(slot)
        game = image[base:base + len(rom)]
        allowed = {0x147, 0x14D, 0x14E, 0x14F}
        if g['key'] == 'talespin':
            allowed |= set(range(chisflash.TS_PATCH, chisflash.TS_PATCH + len(chisflash.TS_PATCH_BYTES)))
            allowed |= set(range(chisflash.TS_ROUTINE, chisflash.TS_ROUTINE + 3))
        diff = [i for i in range(len(rom)) if game[i] != rom[i] and i not in allowed]
        check(not diff and game[0x147] == chisflash.MBC5 and game[0x14D] == build.header_checksum(game),
              f"slot {slot} holds {g['label']} as MBC5, otherwise unchanged"
              + (f' (first diff at {diff[0]:#x})' if diff else ''))


def launch_checks(menu, go):
    for sel, g in enumerate(build.GAMES):
        pb = emu(menu)
        hit = []
        pb.hook_register(build.MENU_BANK, go, lambda c: hit.append(bytes(pb.memory[build.LAUNCH:build.LAUNCH + len(stub_for(sel))])), None)
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
              f"picking {g['label']} readies the switch to slot {sel}")


def cart_view(image):
    """The menu slot as PyBoy runs it: MBC5, padded to 2 MiB so that a game's banks
    fit once the test switches the cart to the game's slot."""
    view = bytearray(image[:chisflash.MENU_SIZE]) + bytes([0xFF]) * (2 * chisflash.MIB - chisflash.MENU_SIZE)
    view[0x148] = 0x06
    view[0x14D] = build.header_checksum(view)
    return bytes(view)


def start_chis(view, game, sel, go, cgb):
    """Pick game sel from the menu, then do what the CPLD does on the stub's $A000
    write: put the slot's ROM where the menu's was. The stub then spends about five
    frames clearing WRAM in HRAM, so the frame the menu reaches go in is early enough."""
    pb = emu(view, cgb)
    hit = []
    pb.hook_register(build.MENU_BANK, go, lambda c: hit.append(1), None)
    pb.tick(verify.BOOT_WAIT, True)
    press(pb, 'start', 30)
    for _ in range(sel):
        press(pb, 'down')
    pb.button('a', 3)
    for _ in range(600):
        pb.tick(1, True)
        if hit:
            pb.hook_deregister(build.MENU_BANK, go)
            assert pb.register_file.PC >= build.LAUNCH, 'not in the stub yet'
            for b in range(len(game) // build.BANK):
                base = 0x4000 if b else 0
                for i in range(build.BANK):
                    pb.memory[b, base + i] = game[b * build.BANK + i]
            return pb
    raise SystemExit('menu never launched a game')


def chis_session(view, game, sel, go, cgb, script, frames, offset=0):
    pb = start_chis(view, game, sel, go, cgb)
    hashes = verify.play(pb, script, frames, offset)
    done(pb)
    return hashes


def _child(q, args):
    q.put(chis_session(*args))


def run_chis(*args):
    ctx = multiprocessing.get_context('fork')
    q = ctx.Queue()
    p = ctx.Process(target=_child, args=(q, args))
    p.start()
    try:
        return q.get(timeout=verify.SESSION_TIMEOUT)
    except queue.Empty:
        return None
    finally:
        p.kill()
        p.join()


def menu_play_checks(image, games, go, cgb):
    """Each game launched from the menu matches its reference on every frame, after the
    start-up delay the warm start adds, as in verify.py."""
    view = cart_view(image)
    tag = 'CGB' if cgb else 'DMG'
    for sel, (name, ref, game) in enumerate(games):
        name = f'{tag} {name} from the menu'
        want = verify.run(ref, None, 0, cgb, [], verify.ALIGN_FRAMES)
        probe = run_chis(view, game, sel, go, cgb, [], verify.ALIGN_FRAMES + verify.ALIGN_WINDOW)
        if probe is None:
            check(False, f'{name}: hung')
            continue
        offsets = verify.delay(probe, want)
        if len(offsets) != 1:
            check(False, f'{name}: start-up delay not pinned down (fits: {offsets})')
            continue
        off = offsets[0]
        script = verify.input_script(1000 + sel)
        want = verify.run(ref, None, 0, cgb, script, verify.PLAY_FRAMES)
        got = run_chis(view, game, sel, go, cgb, script, verify.PLAY_FRAMES + off, off)
        if got is None:
            check(False, f'{name}: hung during play')
            continue
        got = got[off:]
        bad = [f for f in range(10, verify.PLAY_FRAMES) if got[f] != want[f]]
        check(not bad, f'{name}: {verify.PLAY_FRAMES - 10} frames of play match (start-up delay {off} frames)'
                       + (f'; first mismatch at frame {bad[0]}' if bad else ''))


def play_checks(cgb, games):
    """games: (name, stock ROM, converted ROM)."""
    tag = 'CGB' if cgb else 'DMG'
    for i, (name, rom, conv) in enumerate(games):
        script = verify.input_script(1000 + i)
        want = verify.run(rom, None, 0, cgb, script, verify.PLAY_FRAMES)
        got = verify.run(conv, None, 0, cgb, script, verify.PLAY_FRAMES)
        if got is None:
            check(False, f'{tag} {name}: the converted game hung')
            continue
        bad = [f for f in range(10, verify.PLAY_FRAMES) if got[f] != want[f]]
        check(not bad, f'{tag} {name}: {verify.PLAY_FRAMES - 10} frames of play match'
                       + (f'; first mismatch at frame {bad[0]}' if bad else ''))


def _bank0_probe(rom, q):
    """Play to the title, then make TaleSpin's next level-data read ask for bank 0
    and report the first 16 bytes the switchable bank shows at the read."""
    d = tempfile.mkdtemp()
    path = os.path.join(d, 'rom.gb')
    open(path, 'wb').write(rom)
    pb = PyBoy(path, window='null', sound_emulated=False)
    state = {'armed': False, 'forced': False, 'bank': None}
    def at_load(_):                       # ld a,($CD9C): the bank about to be switched in
        if state['armed'] and not state['forced']:
            pb.memory[chisflash.TS_READ_BANK] = 0
            state['forced'] = True
    def at_read(_):                       # ld b,(hl): the switchable bank is now in place
        if state['forced'] and state['bank'] is None:
            state['bank'] = bytes(pb.memory[0x4000 + i] for i in range(16))
    pb.hook_register(0, chisflash.TS_READ - 6, at_load, None)
    pb.hook_register(0, chisflash.TS_READ, at_read, None)
    by_frame = {}
    for f, b, n in verify.input_script(1002):
        by_frame.setdefault(f, []).append((b, n))
    for f in range(verify.PLAY_FRAMES):
        state['armed'] = f >= 600
        for b, n in by_frame.get(f, []):
            pb.button(b, n)
        pb.tick(1, False)
        if state['bank'] is not None:
            break
    pb.stop(save=False)
    shutil.rmtree(d, ignore_errors=True)
    q.put(state['bank'])


def bank0_probe(rom):
    ctx = multiprocessing.get_context('fork')
    q = ctx.Queue()
    p = ctx.Process(target=_bank0_probe, args=(rom, q))
    p.start()
    try:
        return q.get(timeout=verify.SESSION_TIMEOUT)
    except queue.Empty:
        return None
    finally:
        p.kill()
        p.join()


def talespin_read_checks(stock, converted):
    bank0, bank1 = stock[0:16], stock[0x4000:0x4010]
    got = bank0_probe(converted)
    check(got == bank1, 'TALESPIN: a level-data read that asks for bank 0 gets bank 1, as on MBC1'
                        + ('' if got == bank1 else f" (got {'bank 0' if got == bank0 else got!r})"))
    plain = bytearray(stock)
    plain[0x147] = chisflash.MBC5
    plain[0x14D] = build.header_checksum(plain)
    got = bank0_probe(bytes(plain))
    check(got == bank0, 'TALESPIN without its patch gets bank 0 there instead, as it should'
                        + ('' if got == bank0 else f' (got {got!r})'))


def _boot(rom, bank, q):
    d = tempfile.mkdtemp()
    path = os.path.join(d, 'rom.gb')
    open(path, 'wb').write(rom)
    pb = PyBoy(path, window='null', sound_emulated=False)
    if bank is not None:
        pb.memory[0x2000] = bank          # the bank the mapper holds when the game starts
    frames = []
    for _ in range(POWER_ON_FRAMES):
        pb.tick(1, True)
        frames.append(hashlib.md5(pb.screen.image.tobytes()).digest())
    pb.stop(save=False)
    shutil.rmtree(d, ignore_errors=True)
    q.put(frames)


def boot(rom, bank):
    """Frame hashes of a cold start with bank at $4000, or None if it got stuck."""
    ctx = multiprocessing.get_context('fork')
    q = ctx.Queue()
    p = ctx.Process(target=_boot, args=(rom, bank, q))
    p.start()
    try:
        return q.get(timeout=verify.SESSION_TIMEOUT)
    except queue.Empty:
        return None
    finally:
        p.kill()
        p.join()


def power_on_checks(image):
    parts = [(g['label'], image[chisflash.slot_offset(s):chisflash.slot_offset(s) + chisflash.slot_size(s)])
             for s, g in enumerate(build.GAMES)]
    parts.append(('the menu', image[:chisflash.MENU_SIZE]))
    for name, rom in parts:
        want = boot(rom, None)
        differ = [b for b in POWER_ON_BANKS if boot(rom, b) != want]
        check(not differ, f'{name} starts the same with bank 0, 2, 3 or 4 to 9 at power-on'
                          + (f' (differs with {differ})' if differ else ''))
    # the control: DuckTales 2 with its first bank write, at $02A1, taken out
    dt2 = bytearray(parts[1][1])
    assert dt2[DT2_FIRST_BANK_WRITE:DT2_FIRST_BANK_WRITE + 3] == bytes([0xEA, 0x00, 0x20]), 'ld ($2000),a not at $02A1'
    dt2[DT2_FIRST_BANK_WRITE:DT2_FIRST_BANK_WRITE + 3] = bytes(3)
    want = boot(bytes(dt2), None)
    differ = [b for b in POWER_ON_BANKS if boot(bytes(dt2), b) != want]
    check(bool(differ), 'DUCKTALES 2 without its first bank write starts differently, as it should'
                        + (f' (with {differ})' if differ else ''))


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
    power_on_checks(image)
    games = []
    for slot, (g, rom) in enumerate(zip(build.GAMES, roms)):
        base = chisflash.slot_offset(slot)
        converted = image[base:base + len(rom)]
        if g['key'] == 'talespin':
            talespin_read_checks(rom, converted)
            games.append((g['label'] + ' against stock with the same patch', chisflash.patch_talespin(rom), converted))
        else:
            games.append((g['label'] + ' against stock', rom, converted))
    go = chisflash.build_code()[2]['go']
    for cgb in (False, True):
        play_checks(cgb, games)
        menu_play_checks(image, games, go, cgb)
    print(f'\n{len(verify.failures)} failure(s)' if verify.failures else '\nall checks pass')
    sys.exit(1 if verify.failures else 0)


if __name__ == '__main__':
    main()
