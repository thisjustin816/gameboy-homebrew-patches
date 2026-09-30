#!/usr/bin/env python3
"""Check a built multicart against the four stock ROMs in PyBoy.

    python3 verify.py MULTICART DUCKTALES DUCKTALES2 TALESPIN DARKWING bundleMain.mbundle

1. The header is valid and says 2 MiB MBC1 without RAM.
2. Each quarter holds its game byte for byte, apart from the boot hook and header
   fields in quarter 0.
3. The splash and all four menu screens appear as built, PRESS START blinks,
   the cursor wraps both ways, and B, SELECT and left/right do nothing.
4. For each game, launched from the menu, every frame of scripted play matches
   the stock ROM given the same input, on a DMG and on a Game Boy Color.
   The multicart starts a few frames later (the launcher clears WRAM and waits
   for line 0), so the delay is found once on the attract mode, and the streams
   must then agree on every frame.
"""
import hashlib, multiprocessing, os, queue, random, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build, mbundle, pictures
from pyboy import PyBoy

PLAY_FRAMES = 11000          # about three minutes of play per game
ALIGN_WINDOW = 12            # the multicart may start up to this many frames later
ALIGN_FRAMES = 600           # attract-mode frames used to find that delay
SESSION_TIMEOUT = 900        # seconds; a stuck emulator counts as a failure
BOOT_WAIT = 300              # PyBoy's own boot logo, then our splash
DMG_SHADES = [(255, 255, 255), (153, 153, 153), (85, 85, 85), (0, 0, 0)]

failures = []
temp_dirs = {}               # PyBoy objects take no new attributes


def check(ok, what):
    print(('PASS ' if ok else 'FAIL ') + what, flush=True)
    if not ok:
        failures.append(what)


def emu(rom_bytes, cgb=False):
    d = tempfile.mkdtemp()
    path = os.path.join(d, 'rom.gb')
    open(path, 'wb').write(rom_bytes)
    pb = PyBoy(path, window='null', sound_emulated=False, cgb=cgb)
    temp_dirs[id(pb)] = d
    return pb


def done(pb):
    pb.stop(save=False)
    shutil.rmtree(temp_dirs.pop(id(pb)), ignore_errors=True)


def frame_hash(pb):
    return hashlib.md5(pb.screen.image.tobytes()).digest()


def as_dmg(img):
    """A built screen as PyBoy's DMG shows it, as raw RGB bytes."""
    to_dmg = {bytes(s): bytes(DMG_SHADES[i]) for i, s in enumerate(build.SHADES)}
    raw = img.convert('RGB').tobytes()
    return b''.join(to_dmg[raw[i:i + 3]] for i in range(0, len(raw), 3))


def screen_matches(pb, expected):
    """Compare the DMG screen with a built screen, shade for shade."""
    return pb.screen.image.convert('RGB').tobytes() == as_dmg(expected)


def without_prompt(splash):
    """The splash in the blink's off phase: the PRESS START row blank."""
    img = splash.copy()
    row = pictures.PROMPT_ROW * 8
    img.paste(build.SHADES[0], (0, row, 160, row + 8))
    return img


def on_splash(pb, screens):
    return screen_matches(pb, screens[0]) or screen_matches(pb, without_prompt(screens[0]))


def press(pb, button, frames=20):
    pb.button(button, 3)
    pb.tick(frames, True)


# ---- static -------------------------------------------------------------------

def static_checks(multi, roms):
    check(len(multi) == build.ROM_SIZE and multi[0x147] == 0x01 and multi[0x148] == 0x06
          and multi[0x149] == 0x00, 'header: 2 MiB, MBC1, no RAM')
    check(multi[0x14D] == build.header_checksum(multi), 'header checksum')
    check(int.from_bytes(multi[0x14E:0x150], 'big') == build.global_checksum(multi), 'global checksum')
    check(multi[0x104:0x134] == roms[0][0x104:0x134], 'Nintendo logo intact')
    boot = build.build_code()[0]
    changed = {0x102, 0x103} | set(range(build.HOOK, build.HOOK + len(boot))) | set(range(0x134, 0x150))
    for q, (g, r) in enumerate(zip(build.GAMES, roms)):
        base = q * build.QUARTER
        diff = [i for i in range(len(r)) if multi[base + i] != r[i] and base + i not in changed]
        check(not diff, f"quarter {q} holds {g['label']} unchanged"
                        + (f' (first diff at {diff[0]:#x})' if diff else ''))


# ---- menu ---------------------------------------------------------------------

def menu_checks(multi, screens):
    pb = emu(multi)
    pb.tick(BOOT_WAIT, True)
    on, off = as_dmg(screens[0]), as_dmg(without_prompt(screens[0]))
    phases = []
    for _ in range(5 * build.BLINK_FRAMES):
        pb.tick(1, True)
        got = pb.screen.image.convert('RGB').tobytes()
        phases.append('on' if got == on else 'off' if got == off else '?')
    check('?' not in phases, 'splash screen as built, with PRESS START shown or blank')
    runs, n = [], 1                  # lengths of the shown and blank stretches
    for a, b in zip(phases, phases[1:]):
        if a == b:
            n += 1
        else:
            runs.append(n)
            n = 1
    inner = runs[1:]                 # the first stretch was already under way
    check(len(inner) >= 3 and all(r == build.BLINK_FRAMES for r in inner),
          f'PRESS START blinks every {build.BLINK_FRAMES} frames (stretches {runs + [n]})')
    for b in ('b', 'select', 'left', 'right', 'up', 'down'):
        press(pb, b)
    check(on_splash(pb, screens), 'splash ignores everything but A and START')
    press(pb, 'start', 30)
    check(screen_matches(pb, screens[1]), 'START opens the menu on DUCKTALES')
    for i in range(1, 4):
        press(pb, 'down')
        check(screen_matches(pb, screens[1 + i]), f"down highlights {build.GAMES[i]['label']}")
    press(pb, 'down')
    check(screen_matches(pb, screens[1]), 'down from the last game wraps to the first')
    press(pb, 'up')
    check(screen_matches(pb, screens[4]), 'up from the first game wraps to the last')
    for b in ('b', 'select', 'left', 'right'):
        press(pb, b)
    check(screen_matches(pb, screens[4]), 'menu ignores B, SELECT, left and right')
    done(pb)


# ---- play ---------------------------------------------------------------------

def input_script(seed):
    """(frame, button, hold) presses, timed from the game's entry."""
    rng = random.Random(seed)
    buttons = ['a', 'b', 'left', 'right', 'up', 'down']
    out, f = [], 30
    while f < PLAY_FRAMES:
        if f % 600 < 20:              # tap START to get through menus and pauses
            out.append((f, 'start', 3))
            f += 20
            continue
        n = rng.randint(4, 40)
        out.append((f, rng.choice(buttons), n))
        if rng.random() < .5:
            out.append((f, rng.choice(['a', 'b']), rng.randint(2, 12)))
        f += n
    return out


def start_stock(rom, cgb):
    pb = emu(rom, cgb)
    hit = []
    pb.hook_register(0, 0x100, lambda c: hit.append(1), None)
    for _ in range(600):
        pb.tick(1, True)
        if hit:
            return pb
    raise SystemExit('stock ROM never reached $0100')


def start_multi(multi, sel, go, cgb):
    """Launch game sel from the menu; stop in the frame the launcher is entered.

    PyBoy hooks patch memory when registered, so the launch stub in HRAM and a
    game's entry in a remapped quarter can't be hooked; the menu's jump to the
    stub, in bank 4, can.
    """
    pb = emu(multi, cgb)
    hit = []
    pb.hook_register(build.MENU_BANK, go, lambda c: hit.append(1), None)
    pb.tick(BOOT_WAIT, True)
    press(pb, 'start', 30)
    for _ in range(sel):
        press(pb, 'down')
    pb.button('a', 3)
    for _ in range(600):
        pb.tick(1, True)
        if hit:
            return pb
    raise SystemExit('menu never launched a game')


def play(pb, script, frames, offset=0):
    """Run frames, applying script shifted by offset; return per-frame hashes."""
    by_frame = {}
    for f, b, n in script:
        by_frame.setdefault(f + offset, []).append((b, n))
    hashes = []
    for f in range(frames):
        for b, n in by_frame.get(f, []):
            pb.button(b, n)
        pb.tick(1, True)
        hashes.append(frame_hash(pb))
    return hashes


def session(rom, sel, go, cgb, script, frames, offset=0):
    """One emulator run: the stock ROM if sel is None, else game sel from the menu."""
    pb = start_stock(rom, cgb) if sel is None else start_multi(rom, sel, go, cgb)
    hashes = play(pb, script, frames, offset)
    done(pb)
    return hashes


def _child(q, args):
    q.put(session(*args))


def run(*args):
    """Run a session in a child process. A build that crashes can leave PyBoy stuck
    inside a single tick, so a session that outlives SESSION_TIMEOUT returns None."""
    ctx = multiprocessing.get_context('fork')
    q = ctx.Queue()
    p = ctx.Process(target=_child, args=(q, args))
    p.start()
    try:
        return q.get(timeout=SESSION_TIMEOUT)
    except queue.Empty:
        return None
    finally:
        p.kill()
        p.join()


def delay(probe, probe_want):
    """The multicart's start-up delays that fit the stock attract mode."""
    return [o for o in range(ALIGN_WINDOW) if probe[o + 10:o + ALIGN_FRAMES] == probe_want[10:]]


def play_checks(multi, roms, cgb):
    go = build.build_code()[2]['go']
    tag = 'CGB' if cgb else 'DMG'
    for sel, (g, rom) in enumerate(zip(build.GAMES, roms)):
        name = f"{tag} {g['label']}"
        # Find the start-up delay on the attract mode, before any input. Its
        # opening screens hold still for a while, so it takes a long window to
        # leave only one delay that fits.
        probe_want = run(rom, None, go, cgb, [], ALIGN_FRAMES)
        probe = run(multi, sel, go, cgb, [], ALIGN_FRAMES + ALIGN_WINDOW)
        if probe is None:
            check(False, f'{name}: the multicart hung')
            continue
        offsets = delay(probe, probe_want)
        if len(offsets) != 1:
            check(False, f'{name}: start-up delay not pinned down (fits: {offsets})')
            continue
        off = offsets[0]
        script = input_script(1000 + sel)
        want = run(rom, None, go, cgb, script, PLAY_FRAMES)
        got = run(multi, sel, go, cgb, script, PLAY_FRAMES + off, off)
        if got is None:
            check(False, f'{name}: the multicart hung during play')
            continue
        got = got[off:]
        bad = [i for i in range(10, PLAY_FRAMES) if got[i] != want[i]]
        check(not bad, f'{name}: {PLAY_FRAMES - 10} frames of play match stock '
                       f'(start-up delay {off} frames)' + (f'; first mismatch at frame {bad[0]}' if bad else ''))


def main():
    if len(sys.argv) != 7:
        sys.exit(__doc__)
    multi = open(sys.argv[1], 'rb').read()
    roms = [build.load_checked(p, g['md5'], g['label']) for p, g in zip(sys.argv[2:6], build.GAMES)]
    build.load_checked(sys.argv[6], build.BUNDLE_MD5, 'bundleMain.mbundle')
    art = mbundle.read(sys.argv[6])
    check(multi == build.build(roms, art), 'multicart is exactly what build.py makes')
    static_checks(multi, roms)
    screens = build.screens(roms, art)
    menu_checks(multi, screens)
    play_checks(multi, roms, cgb=False)
    play_checks(multi, roms, cgb=True)
    print(f'\n{len(failures)} failure(s)' if failures else '\nall checks pass')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
