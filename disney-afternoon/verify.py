#!/usr/bin/env python3
"""Check a built multicart against the four stock ROMs in PyBoy.

    python3 verify.py MULTICART DUCKTALES DUCKTALES2 TALESPIN DARKWING bundleMain.mbundle

1. The header is valid and says 2 MiB MBC1 with 8 KiB of RAM and no battery.
2. Each quarter holds its game byte for byte, apart from the title patch, and in
   quarter 0 the boot hook and header.
3. The splash and all four menu screens appear as built, the cursor wraps both
   ways, and B, SELECT and left/right do nothing.
4. B on each game's title screen, and on DuckTales 2's difficulty screen,
   brings back the menu with that game highlighted, and B on DuckTales' LAND
   SELECT, which shares the title's menu code, does nothing.
5. For each game, launched from the menu, every frame of scripted play matches
   the stock ROM given the same input, on a DMG and on a Game Boy Color. So
   does a second launch after going back with B. The multicart starts a few
   frames later (the launcher clears WRAM and waits for line 0), so the delay is
   found once on the attract mode, and the streams must then agree on every
   frame. B now means something on a title screen, so the script's B presses
   that land on one are dropped, and the stock run is repeated until none do.
"""
import hashlib, multiprocessing, os, queue, random, shutil, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build, mbundle
from pyboy import PyBoy

PLAY_FRAMES = 11000          # about three minutes of play per game
# Frames after a launch to reach each title screen, and presses on the way.
TO_TITLE = [(200, []), (700, [(400, 'start')]), (500, []), (2500, [])]
ALIGN_WINDOW = 12            # the multicart may start up to this many frames later
ALIGN_FRAMES = 600           # attract-mode frames used to find that delay
DROP_ROUNDS = 8              # stock runs allowed to clear B presses off the title
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


def screen_matches(pb, expected):
    """Compare the DMG screen with a built screen, shade for shade."""
    got = pb.screen.image.convert('RGB')
    want = expected.convert('RGB')
    to_dmg = {s: DMG_SHADES[i] for i, s in enumerate(build.SHADES)}
    return all(got.getpixel((x, y)) == to_dmg[want.getpixel((x, y))]
               for y in range(144) for x in range(160))


def press(pb, button, frames=20):
    pb.button(button, 3)
    pb.tick(frames, True)


# ---- static -------------------------------------------------------------------

def static_checks(multi, roms):
    check(len(multi) == build.ROM_SIZE and multi[0x147] == 0x02 and multi[0x148] == 0x06
          and multi[0x149] == 0x02, 'header: 2 MiB, MBC1 with 8 KiB of RAM, no battery')
    check(multi[0x14D] == build.header_checksum(multi), 'header checksum')
    check(int.from_bytes(multi[0x14E:0x150], 'big') == build.global_checksum(multi), 'global checksum')
    check(multi[0x104:0x134] == roms[0][0x104:0x134], 'Nintendo logo intact')
    boot, _, labels = build.build_code()
    changed = {0x102, 0x103} | set(range(build.HOOK, build.HOOK + len(boot))) | set(range(0x134, 0x150))
    for at, data in build.title_patches(roms, labels, len(boot)):
        changed |= set(range(at, at + len(data)))
    for q, (g, r) in enumerate(zip(build.GAMES, roms)):
        base = q * build.QUARTER
        diff = [i for i in range(len(r)) if multi[base + i] != r[i] and base + i not in changed]
        check(not diff, f"quarter {q} holds {g['label']} unchanged but for its patches"
                        + (f' (first diff at {diff[0]:#x})' if diff else ''))


# ---- menu ---------------------------------------------------------------------

def menu_checks(multi, screens):
    pb = emu(multi)
    pb.tick(BOOT_WAIT, True)
    check(screen_matches(pb, screens[0]), 'splash screen as built')
    for b in ('b', 'select', 'left', 'right', 'up', 'down'):
        press(pb, b)
    check(screen_matches(pb, screens[0]), 'splash ignores everything but A and START')
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


def to_title(pb, sel):
    frames, presses = TO_TITLE[sel]
    for f in range(frames):
        for pf, b in presses:
            if pf == f:
                pb.button(b, 4)
        pb.tick(1, True)


def start_multi(multi, sel, go, cgb, bounce=False):
    """Launch game sel from the menu; stop in the frame the launcher is entered.

    With bounce, go on to the game's title, back to the menu with B, and launch
    it again, stopping at that second launch.

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
    for launch in range(2 if bounce else 1):
        for _ in range(600):
            pb.tick(1, True)
            if len(hit) > launch:
                break
        else:
            raise SystemExit('menu never launched a game')
        if bounce and launch == 0:
            to_title(pb, sel)
            press(pb, 'b', 40)
            pb.button('a', 3)
    return pb


def title_b(pb, t):
    """Whether B is newly pressed on the title, judged where the patch judges it."""
    m = pb.memory
    if t['kind'] == 'loop':
        return m[t['new']] & 2
    if not m[0xFF00 + t['new']] & 2:
        return False
    hl = pb.register_file.HL
    if t['kind'] == 'menu':
        return hl == t['hl']
    return any(hl == h and m[hl + 1] == mask and m[hl + 2] | m[hl + 3] << 8 == target
               for h, mask, target in t['ops'])


def play(pb, script, frames, offset=0, clock=None):
    """Run frames, applying script shifted by offset; return per-frame hashes.
    clock[0] holds the frame being run, for hooks to read."""
    by_frame = {}
    for f, b, n in script:
        by_frame.setdefault(f + offset, []).append((b, n))
    hashes = []
    for f in range(frames):
        if clock is not None:
            clock[0] = f
        for b, n in by_frame.get(f, []):
            pb.button(b, n)
        pb.tick(1, True)
        hashes.append(frame_hash(pb))
    return hashes


def session(rom, sel, go, cgb, script, frames, offset=0, bounce=False, title=None):
    """One emulator run: the stock ROM if sel is None, else game sel from the menu.

    Returns the frame hashes, and for a stock run given its game's title profile,
    the frames in which B was newly pressed on the title.
    """
    pb = start_stock(rom, cgb) if sel is None else start_multi(rom, sel, go, cgb, bounce)
    clock, seen = [0], set()
    if title:
        bank, addr = title['site']
        pb.hook_register(bank, addr, lambda c: title_b(pb, title) and seen.add(clock[0]), None)
    hashes = play(pb, script, frames, offset, clock)
    done(pb)
    return hashes, sorted(seen)


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


def drop_title_b(script, frames):
    """Drop the B press behind each frame in which B landed on a title."""
    out = list(script)
    for f in frames:
        presses = [p for p in out if p[1] == 'b' and p[0] <= f]
        if presses:
            out.remove(max(presses))
    return out


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
        probe_want, _ = run(rom, None, go, cgb, [], ALIGN_FRAMES)
        probe = run(multi, sel, go, cgb, [], ALIGN_FRAMES + ALIGN_WINDOW)
        if probe is None:
            check(False, f'{name}: the multicart hung')
            continue
        offsets = delay(probe[0], probe_want)
        if len(offsets) != 1:
            check(False, f'{name}: start-up delay not pinned down (fits: {offsets})')
            continue
        off = offsets[0]
        again = run(multi, sel, go, cgb, [], ALIGN_FRAMES + ALIGN_WINDOW, 0, True)
        check(again is not None and delay(again[0], probe_want) == [off],
              f'{name}: launched again after B, it starts exactly as the first time')

        # Drop the script's B presses that land on a title screen, until a stock
        # run with it has none. A dropped press can change what stock does next
        # (B may still be held when the game starts), so each round runs again.
        script, dropped = input_script(1000 + sel), 0
        for _ in range(DROP_ROUNDS):
            want, landed = run(rom, None, go, cgb, script, PLAY_FRAMES, 0, False, g['title'])
            if not landed:
                break
            script = drop_title_b(script, landed)
            dropped += len(landed)
        check(not landed, f'{name}: a script with no B on a title screen ({dropped} B presses dropped)')
        if landed:
            continue
        got = run(multi, sel, go, cgb, script, PLAY_FRAMES + off, off)
        if got is None:
            check(False, f'{name}: the multicart hung during play')
            continue
        got = got[0][off:]
        bad = [i for i in range(10, PLAY_FRAMES) if got[i] != want[i]]
        check(not bad, f'{name}: {PLAY_FRAMES - 10} frames of play match stock '
                       f'(start-up delay {off} frames)' + (f'; first mismatch at frame {bad[0]}' if bad else ''))

        if sel == 0:
            # LAND SELECT runs the title's menu code with a different HL.
            frames, _ = TO_TITLE[0]
            land = [(frames, 'start', 3)] + [(frames + 60 + 12 * i, 'b', 3) for i in range(8)]
            want, landed = run(rom, None, go, cgb, land, frames + 200, 0, False, g['title'])
            got = run(multi, sel, go, cgb, land, frames + 200 + off, off)
            check(not landed and got is not None and got[0][off:] == want,
                  f'{name}: B on LAND SELECT does nothing, as in stock')


def b_checks(multi, screens):
    """B on each title screen, and on DuckTales 2's difficulty screen, which
    shows on its title, brings back the menu with that game highlighted."""
    go = build.build_code()[2]['go']
    cases = [(sel, []) for sel in range(4)] + [(1, [(0, 'start')])]
    for sel, extra in cases:
        pb = start_multi(multi, sel, go, False)
        to_title(pb, sel)
        for _, b in extra:
            press(pb, b, 60)
        where = 'difficulty screen' if extra else 'title screen'
        press(pb, 'b', 40)
        check(screen_matches(pb, screens[1 + sel]),
              f"B on the {build.GAMES[sel]['label']} {where} goes back to the menu on that game")
        done(pb)


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
    b_checks(multi, screens)
    play_checks(multi, roms, cgb=False)
    play_checks(multi, roms, cgb=True)
    print(f'\n{len(failures)} failure(s)' if failures else '\nall checks pass')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
