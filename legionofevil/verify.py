#!/usr/bin/env python3
"""Checks for the Legion of Evil patch, run in PyBoy on the real ROM.

    python3 verify.py STOCK PATCHED

STOCK is the original ROM; PATCHED is what patch.py built from it. Each check
says what it proved. Where a check covers a fault in the stock game, it runs
the same thing on a control (the stock ROM with only the music-bank fix, which
a plain 32 KB cartridge needs to boot here) and shows the fault there first.

What these cannot show: sound (the music position after CONTINUE, and whether
the sampled frames have the right audio), a real battery cartridge, double
speed on real hardware, and how the game feels to play.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import patch as patcher

from pyboy import PyBoy

STOCK_MD5 = "cd544132f9d06ca9fe4f552ddc202878"
# Shades the game picks from, and the color theme the patch starts with (the DMG screen)
PY_DMG = [(255, 255, 255), (169, 169, 169), (84, 84, 84), (0, 0, 0)]
THEME0 = [(0xC6, 0xDE, 0x8C), (0x84, 0xA5, 0x63), (0x39, 0x61, 0x39), (0x08, 0x18, 0x10)]   # DMG, lightest first

WORK = tempfile.mkdtemp(prefix="loe-verify-")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


# ---------------------------------------------------------------- emulator
class Game:
    """A PyBoy instance on its own copy of a ROM; the battery file sits beside it."""

    def __init__(self, rom, tag, fresh=True):
        self.path = os.path.join(WORK, tag + ".gb")
        if fresh and os.path.exists(self.path + ".ram"):
            os.remove(self.path + ".ram")
        shutil.copy(rom, self.path)
        self.pb = PyBoy(self.path, window="null", sound_emulated=False)
        self.m = self.pb.memory

    def tick(self, n=1, render=True):
        self.pb.tick(n, render)

    def press(self, button, hold=4, after=40):
        self.pb.button_press(button)
        self.pb.tick(hold, True)
        self.pb.button_release(button)
        self.pb.tick(after, True)

    def stop(self):
        self.pb.stop(save=True)
        return open(self.path + ".ram", "rb").read()

    def screen(self):
        return self.pb.screen.image.convert("RGB")

    def wram(self):
        return bytes(self.m[0xC000:0xCA20])


def script(f):
    """Held buttons at frame f: walk a square, pick level-ups with A."""
    d = ["up", "right", "down", "left"][(f // 240) % 4]
    return {d} | ({"a"} if f % 90 < 3 else set())


def play(game, frames, start=0, keep_alive=True):
    held = set()
    for f in range(start, start + frames):
        want = script(f)
        for b in held - want:
            game.pb.button_release(b)
        for b in want - held:
            game.pb.button_press(b)
        held = want
        if keep_alive:
            game.m[0xC0CC] = 20
        game.tick(1, False)
    for b in held:
        game.pb.button_release(b)


def start_run(game):
    game.tick(200)
    game.press("start", after=200)


def until_live(game):
    """Dismiss level-up menus until the run is on its main screen."""
    m = game.m
    for _ in range(600):
        if m[0xC5B5] == 0 and m[0xC5B6] == 0 and not any(m[a] for a in range(0xC5D9, 0xC5DF)):
            return
        game.press("a", after=10)
    raise SystemExit("never reached a live run")


def masked(wram):
    """Game memory without the VBlank frame counter, the music player, and the
    banked-money bookkeeping that differs by design."""
    w = bytearray(wram)
    w[0xA3] = w[0xA4] = 0
    w[0x56E:0x5B2] = bytes(0x44)
    return bytes(w)


def near(px, palette):
    return min(range(4), key=lambda i: sum((px[k] - palette[i][k]) ** 2 for k in range(3)))


def shades(img, palette):
    return [near(p, palette) for p in img.getdata()]


def fix_header(rom):
    x = 0
    for i in range(0x134, 0x14D):
        x = (x - rom[i] - 1) & 0xFF
    rom[0x14D] = x


# ---------------------------------------------------------------- ROMs
def apply_ips(original, ips):
    out = bytearray(original)
    assert ips[:5] == b"PATCH"
    i = 5
    while ips[i:i + 3] != b"EOF":
        off = int.from_bytes(ips[i:i + 3], "big")
        size = int.from_bytes(ips[i + 3:i + 5], "big")
        i += 5
        if size:
            data = ips[i:i + size]
            i += size
        else:
            run = int.from_bytes(ips[i:i + 2], "big")
            data = bytes([ips[i + 2]]) * run
            i += 3
        if off + len(data) > len(out):
            out.extend(b"\xFF" * (off + len(data) - len(out)))
        out[off:off + len(data)] = data
    return bytes(out)


def build_control(stock):
    """The stock game with only the music-bank fix."""
    rom = bytearray(stock)
    profile = patcher.ROM_PROFILES[STOCK_MD5]
    for at in profile["music_bank_loads"]:
        rom[at - 7] = 0x01
    return bytes(rom)


# ---------------------------------------------------------------- checks
def check_rom(stock, rom, ips_path, rumble):
    print("ROM")
    check("stock ROM is the profiled release", hashlib.md5(stock).hexdigest() == STOCK_MD5)
    kind = "MBC5+RUMBLE+RAM+BATTERY" if rumble else "MBC1+RAM+BATTERY"
    check(f"patched ROM is 64 KB {kind} with 8 KB RAM and the color flag",
          len(rom) == 0x10000 and rom[0x147] == (0x1E if rumble else 0x03) and rom[0x148] == 1 and rom[0x149] == 2 and rom[0x143] == 0x80)
    check("header checksum is valid", patcher.header_checksum(rom) == rom[0x14D])
    g = patcher.global_checksum(rom)
    check("global checksum is valid", g == (rom[0x14E] << 8 | rom[0x14F]))
    check("music player asks for bank 1 at all seven calls",
          all(rom[a - 7] == 1 and stock[a - 7] == 2 for a in patcher.ROM_PROFILES[STOCK_MD5]["music_bank_loads"]))
    if ips_path and os.path.exists(ips_path):
        check("the committed IPS applied to the stock ROM gives this ROM", apply_ips(stock, open(ips_path, "rb").read()) == rom)
    check("patch.py is deterministic", patcher.patch(stock, verbose=False, rumble=rumble) == rom)


def check_motor_harmless(rom):
    """On the MBC1 build the motor writes go to a 2-bit register, so the bank at
    $4000 must be the one mapped before each of them, through hits and a boss."""
    print("Motor writes on MBC1")
    data = open(rom, "rb").read()
    bank2 = data[0x8000:0x8040]                         # the patch's code runs with bank 2 mapped
    g = Game(rom, "mh")
    names = ("hr_on_st", "hr_off_st", "hr_big_st")
    writes, back, bad = dict.fromkeys(names, 0), dict.fromkeys(names, 0), [0]

    def before(name):
        writes[name] += 1

    def after(name):
        # A write that switched the ROM bank would take this code away, and the
        # next instruction would never run in bank 2, so this count would fall short.
        back[name] += 1
        if bytes(g.m[0x4000 + i] for i in range(0x40)) != bank2:
            bad[0] += 1
    for name in names:
        g.pb.hook_register(2, _LABELS[name], before, name)
        g.pb.hook_register(2, _LABELS[name] + 3, after, name)    # the instruction after the write
    g.tick(200)
    g.press("start", after=0)
    g.tick(1200)
    for _ in range(600):
        g.tick(1, False)
        if g.m[0xC0CC] < 5:
            g.m[0xC0CC] = 20
    ok = writes["hr_on_st"] > 20 and writes == back and not bad[0]
    check("MBC1 build: every motor write leaves bank 2 mapped at $4000", ok,
          f"{sum(writes.values())} writes ({writes['hr_on_st']} on), {sum(back.values())} returned in bank 2, "
          f"{bad[0]} with another bank there")


def check_no_save_start(rom):
    print("Start without a save")
    g = Game(rom, "nosave")
    g.tick(200)
    check("the title shows and the patch is ready", g.m[0xD000] == 0xA5 and g.m[0xD001] == 0x5A)
    g.press("start", after=200)
    a = g.m[0xC0D9]
    g.tick(10)
    check("START starts a run straight away, as stock does",
          g.m[0xFF40] == 0xE3 and g.m[0xC5B5] == 0 and g.m[0xC0D9] != a)


def check_power_on_bank(rom, label=""):
    print(label + "A mapper that powers up on another bank")
    up = []
    for bank in (0, 2, 3):
        g = Game(rom, f"bank{bank}")
        g.m[0x2000] = bank
        g.tick(200)
        up.append(g.m[0xD000] == 0xA5 and g.m[0xD001] == 0x5A and g.m[0xFF40] & 0x80 != 0)
        g.stop()
    check(label + "the title shows with bank 0, 2 or 3 mapped at $4000 at power-on", all(up),
          f"banks 0, 2, 3: {up}")


def check_held_start(control, rom):
    print("START held from the title")
    for name, path in (("stock", control), ("patched", rom)):
        g = Game(path, "hold-" + name)
        g.tick(200)
        g.pb.button_press("start")
        g.tick(40)
        g.pb.button_release("start")
        g.tick(60)
        frozen = g.m[0xC5B6] == 1
        if name == "stock":
            check("stock: a START held into the run sets off the stock pause, a frozen run with nothing shown (the control)", frozen)
        else:
            check("patched: the run starts and plays; the stock pause never sees START", not frozen and g.m[0xC5B5] == 0
                  and g.m[0xFF4A] == 0x80)


def hit_pattern(path, cgb, motor=None):
    """Frames with the player on the hit palette, as the hardware's sprite table
    holds them, next to the frames the game registered a hit. With a list in
    motor, also whether the rumble motor is on in each frame (the patch's two
    writes to the RAM bank register)."""
    data = bytearray(open(path, "rb").read())
    if not cgb and data[0x143]:
        data[0x143] = 0
        fix_header(data)
    p = os.path.join(WORK, f"hit-{'cgb' if cgb else 'dmg'}-{os.path.basename(path)}")
    open(p, "wb").write(data)
    g = Game(p, "hit" + ("c" if cgb else "d") + os.path.basename(path)[:4])
    g.tick(200)
    g.press("start", after=0)
    g.tick(1200)                                        # the enemies reach a player standing still
    shown, hits = [], []
    g.pb.hook_register(1, 0x4ACC, lambda c: hits.append(len(shown)), None)   # the game's non-fatal hit
    on = [False]
    loop = [0]
    if motor is not None:
        g.pb.hook_register(1, 0x58B8, lambda c: loop.__setitem__(0, loop[0] + 1), None)   # the run loop's wait
        g.pb.hook_register(2, _LABELS["hr_on_st"], lambda c: on.__setitem__(0, True), None)
        g.pb.hook_register(2, _LABELS["hr_off_st"], lambda c: on.__setitem__(0, False), None)
        g.pb.hook_register(2, _LABELS["hr_big_st"], lambda c: on.__setitem__(0, True), None)
    for _ in range(600):
        g.tick(1, False)
        if motor is not None:
            motor.append((on[0], loop[0]))
            loop[0] = 0
        # the player's four sprites always sit at the middle of the screen
        # (OAM y $50/$58, x $48/$50; the game sets them at $3B15)
        lit = any(g.m[0xFE03 + i * 4] & 0x10 for i in range(40)
                  if g.m[0xFE00 + i * 4] in (0x50, 0x58) and g.m[0xFE01 + i * 4] in (0x48, 0x50))
        shown.append(lit)
        if g.m[0xC0CC] < 5:
            g.m[0xC0CC] = 20
    return shown, hits


def runs(shown):
    """(start, length) of each stretch of frames on the hit palette."""
    out, start = [], None
    for f, lit in enumerate(shown + [False]):
        if lit and start is None:
            start = f
        elif not lit and start is not None:
            out.append((start, f - start))
            start = None
    return out


def check_hit_pulse(control, rom, rumble=True):
    print("Hit pulse")
    shown, hits = hit_pattern(control, False)
    lit = {f for f, x in enumerate(shown) if x}
    check("stock shows the hit palette only on the frames with a hit, one frame each (the control)",
          len(hits) > 20 and lit == set(hits), f"{len(hits)} hits, {len(lit)} lit frames")
    for cgb, name in ((False, "original Game Boy"), (True, "Game Boy Color")):
        motor = [] if rumble else None
        shown, hits = hit_pattern(rom, cgb, motor)
        r = runs(shown)
        pulses_ok = all(n == 2 and s in hits for s, n in r)
        gaps_ok = all(b[0] - (a[0] + a[1]) >= 2 for a, b in zip(r, r[1:]))
        covered = all(any(s <= h < s + 4 for s, n in r) for h in hits)
        check(f"{name}: every pulse is 2 frames on the hit palette from a hit, then at least 2 normal; no hit goes unshown",
              len(r) > 20 and pulses_ok and gaps_ok and covered, f"{len(hits)} hits, {len(r)} pulses")
        if not rumble:
            continue
        kick = 6                                         # HIT_KICK, counted in run-loop frames: a frame
        due = set()                                      # the game drops (a menu being drawn) holds it on
        for st, n in r:
            done, f = 0, st
            while done < kick and f < len(motor):
                due.add(f)
                done += motor[f][1] > 0
                f += 1
            due |= set(range(st, st + n))
        on = {f for f, (x, _) in enumerate(motor) if x}
        check(f"{name}: each hit runs the rumble motor solid for its first {kick} frames, and only then",
              len(r) > 20 and on == {f for f in due if f < len(motor)},
              f"{len(r)} pulses" + ("" if on == due else f", on but not due {sorted(on - due)[:4]}, due but off {sorted(due - on)[:4]}"))


def check_save_cycle(rom):
    print("Saving the upgrades")
    g = Game(rom, "save")
    start_run(g)
    g.m[0xC5E5], g.m[0xC5E6] = 0xF4, 0x01              # 500 from the run
    g.m[0xC5DB] = 1                                     # what a fatal hit sets
    g.tick(300)
    check("dying banks the run's money", g.m[0xC5DF] | g.m[0xC5E0] << 8 == 500)
    ram = g.stop()
    check("the upgrades are in battery RAM with a valid check",
          ram[:4] == b"LOE1" and ram[0x11] | ram[0x12] << 8 == 500 and
          ((sum(ram[4:19]) & 0xFF) ^ 0xA5) == ram[0x13])
    g2 = Game(rom, "save", fresh=False)
    g2.tick(200)
    check("after a power cycle the money is back", g2.m[0xC5DF] | g2.m[0xC5E0] << 8 == 500)
    g2.press("start", after=30)
    menu_open = g2.m[0xFF40] & 0x20 and g2.m[0xFF4A] == 0
    g2.press("a", after=200)                            # NEW RUN is the first row (no run saved)
    check("START opens the menu and NEW RUN opens the store",
          menu_open and g2.m[0xC5DC] == 1 and g2.m[0xC5B5] == 1)
    g2.press("down", after=20)
    g2.press("down", after=20)                          # molotov, 200
    g2.press("a", after=40)
    ram = g2.stop()
    check("a purchase is written at once",
          ram[4 + 8] == 1 and ram[0x11] | ram[0x12] << 8 == 300, f"money {ram[0x11] | ram[0x12] << 8}")


def check_erase(rom):
    print("Erasing")
    g = Game(rom, "erase")
    g.tick(200)
    g.press("select", after=40)                         # pick a color theme first: it must survive an erase
    start_run(g)
    g.m[0xC5E5], g.m[0xC5E6] = 0x2C, 0x01
    g.m[0xC5DB] = 1
    g.tick(300)
    g.stop()
    g2 = Game(rom, "erase", fresh=False)
    g2.tick(200)
    g2.press("start", after=30)
    g2.press("down", after=10)                          # ERASE SAVE
    g2.press("a", after=30)                             # the confirm page; NO is the default
    g2.press("a", after=30)
    check("NO on the confirm page keeps the save", g2.m[0xC5DF] | g2.m[0xC5E0] << 8 == 300 and g2.m[0xD002] & 1)
    g2.press("down", after=10)                          # back on the menu: ERASE SAVE again
    g2.press("a", after=30)
    g2.press("down", after=10)                          # YES
    g2.press("a", after=60)
    ram = g2.stop()
    check("YES erases the save", ram[:4] == b"\0\0\0\0" and g2.m[0xD002] == 0 and g2.m[0xC5DF] | g2.m[0xC5E0] << 8 == 0)
    check("the color theme is kept", ram[0x14] == 1 and ram[0x14] ^ 0x5A == ram[0x15])
    g3 = Game(rom, "erase", fresh=False)
    g3.tick(200)
    g3.press("start", after=200)
    check("with nothing saved START starts a run again", g3.m[0xFF40] == 0xE3 and g3.m[0xC5B5] == 0)


def check_pause(rom):
    print("Pause menu")
    g = Game(rom, "pause")
    start_run(g)
    play(g, 600)
    until_live(g)
    g.tick(3)
    g.press("start", after=40)
    tick = g.m[0xC0D9]
    g.tick(60)
    check("START opens the menu and the game stands still behind it",
          g.m[0xFF40] & 0x20 and g.m[0xFF4A] == 0 and g.m[0xC0D9] == tick)
    rows = [bytes(g.m[0x9C00 + y * 32 + 4 + k] for k in range(13)) for y in (7, 9, 11)]
    check("the pause menu offers RESUME and SAVE & QUIT, and nothing below them",
          rows[0].startswith(bytes([0x66, 0x59, 0x67, 0x69])) and rows[1][:4] == bytes([0x67, 0x55, 0x6A, 0x59]) and rows[2] == bytes([0x7F] * 13))
    g.press("a", after=20)
    check("RESUME returns to the run: the game ticks again, the HUD window and sprites are back",
          g.m[0xC0D9] != tick and g.m[0xFF4A] == 0x80 and g.m[0xFF40] & 0x02 and g.m[0xC5B5] == 0)


def check_continue(rom, tick_count=900, label=""):
    print(f"Save and quit, continue{' (' + label.rstrip(': ') + ')' if label else ''}")

    def sync(g, target):
        for _ in range(1200):
            g.tick(1)
            if g.m[0xC0D9] == target and g.m[0xC5B5] == 0 and g.m[0xC0A3] != 0:
                break
        else:
            raise SystemExit("never reached the sync point")
        g.m[0xC0A3] = g.m[0xC0A4] = 0
        g.m[0xD010] = 0                                  # the sprite-rotation phase is not game state

    def record(g, n):
        """n frames, each sampled at the same point in the game's loop (the frame
        wait), so the sampling does not depend on where the logic sits relative to
        the frame boundary."""
        out = []

        def grab(ctx):
            if len(out) < n:
                ys = [g.m[0xFE00 + i * 4] for i in range(40)]
                crowded = any(sum(1 for y in ys if y - 16 <= ly < y - 8) > 10 for ly in range(144))
                out.append((g.screen().tobytes(), masked(g.wram()), crowded, bytes(g.m[0xFE00:0xFEA0]), 0,
                            bytes(g.m[0x9800:0x9FFF]) + bytes(g.m[0x8000 + k] for k in range(0x1800))))
        g.pb.hook_register(1, 0x7AFD, grab, None)
        while len(out) < n:
            g.m[0xC0CC] = 20
            g.tick(1)
        g.pb.hook_deregister(1, 0x7AFD)
        return out

    ref = Game(rom, "ref")
    start_run(ref)
    play(ref, 1500)
    until_live(ref)
    ref.tick(3)
    t0 = ref.m[0xC0D9]
    ref.press("start", after=40)
    ref.pb.button_press("a")
    ref.tick(1)
    ref.pb.button_release("a")
    sync(ref, (t0 + 25) & 0xFF)
    rec_ref = record(ref, tick_count)

    sub = Game(rom, "sub")
    start_run(sub)
    play(sub, 1500)
    until_live(sub)
    sub.tick(3)
    sub.press("start", after=40)
    sub.press("down", after=10)
    sub.press("a", after=400)                           # SAVE & QUIT
    title_back = sub.m[0xFF40] == 0xC1
    ram = sub.stop()
    check(label + "SAVE & QUIT writes a snapshot and lands on the title", ram[0x16] == 0x5A and title_back)
    sub2 = Game(rom, "sub", fresh=False)
    sub2.tick(200)
    check(label + "after a power cycle the title offers CONTINUE", sub2.m[0xD002] & 3 == 3)
    sub2.press("start", after=30)
    sub2.pb.button_press("a")
    sub2.tick(1)
    sub2.pb.button_release("a")
    sync(sub2, (t0 + 25) & 0xFF)
    rec_sub = record(sub2, tick_count)
    # Game memory, the sprite table and video memory must match on every frame.
    # Screens may differ only on at most two adjacent lines: the game streams the
    # camera's edge column or row into the background map while the picture is
    # drawn, and the music player (the one state left out above,
    # since it keeps playing behind the menu) changes how long a frame's first
    # work takes, which can move that write by a scanline. Frames where a line
    # holds more than ten sprites are skipped, because the enemy order on such a
    # line follows a counter that is not game state.
    state_bad, screen_bad, slivers = [], [], 0
    for i in range(tick_count):
        a, b = rec_ref[i], rec_sub[i]
        sprites = lambda t: sorted(t[k:k + 4] for k in range(0, 160, 4))     # the order rotates; the set must not change
        if a[1] != b[1] or sprites(a[3]) != sprites(b[3]) or a[5] != b[5]:
            state_bad.append(i)
            print(f"    frame {i}: differs in " + ", ".join(n for n, x, y in (("memory", a[1], b[1]), ("sprites", sprites(a[3]), sprites(b[3])), ("video memory", a[5], b[5])) if x != y)
                  + "; first bytes " + ",".join(hex(k) for k in range(len(a[1])) if a[1][k] != b[1][k])[:60])
        if a[0] != b[0] and not (a[2] or b[2]):
            px = [k // 3 for k in range(0, len(a[0]), 3) if a[0][k:k + 3] != b[0][k:k + 3]]
            lines = sorted({p // 160 for p in px})
            xs = sorted({p % 160 for p in px})
            if lines[-1] - lines[0] > 1:                     # over more than two lines
                screen_bad.append(i)
                rows = sorted({p // 160 for p in px})
                cols = sorted({p % 160 for p in px})
                order = "same sprite order" if a[3] == b[3] else "sprite order differs"
                print(f"    frame {i}: {len(px)} pixels differ, lines {rows[0]}-{rows[-1]}, columns {cols[0]}-{cols[-1]}; {order}")
            else:
                slivers += 1
    bad = state_bad + screen_bad
    check(label + f"a continued run is identical to an uninterrupted one for {tick_count} frames",
          not bad, f"{len(state_bad)} frames with different memory, {len(screen_bad)} with different screens" if bad else
          f"memory, sprites and video memory on every frame; {slivers} frame(s) differ on one or two lines")
    ram = sub2.stop()
    check(label + "CONTINUE uses the snapshot up", ram[0x16] == 0)

    # a damaged snapshot must not be offered
    sub3 = Game(rom, "sub3")
    start_run(sub3)
    play(sub3, 600)
    until_live(sub3)
    sub3.press("start", after=40)
    sub3.press("down", after=10)
    sub3.press("a", after=400)
    ram = bytearray(sub3.stop())
    ram[0x100 + 2000] ^= 0xFF
    open(sub3.path + ".ram", "wb").write(ram)
    sub4 = Game(rom, "sub3", fresh=False)
    sub4.tick(200)
    check(label + "a damaged snapshot is not offered", sub4.m[0xD002] & 2 == 0 and sub4.m[0xD002] & 1 == 1)


def font_tiles(text):
    """The game's tile codes for upper-case text, digits and spaces."""
    return bytes(0x7F if c == " " else 0x55 + ord(c) - 65 for c in text)


def check_new_run_confirm(rom):
    print("NEW RUN with a saved run")
    g = Game(rom, "nr")
    start_run(g)
    play(g, 600)
    until_live(g)
    g.press("start", after=40)
    g.press("down", after=10)
    g.press("a", after=400)                             # SAVE & QUIT
    g.stop()
    g2 = Game(rom, "nr", fresh=False)
    g2.tick(200)
    g2.press("start", after=30)
    at = lambda col, row, n: bytes(g2.m[0x9C00 + row * 32 + col + k] for k in range(n))
    menu_heading = at(3, 3, 14)
    g2.press("down", after=10)                          # NEW RUN
    g2.press("a", after=30)
    check("NEW RUN asks first when a run is saved, in the same columns as the title menu",
          menu_heading == font_tiles("LEGION OF EVIL") and at(3, 3, 7) == font_tiles("NEW RUN")
          and at(3, 6, 15) == font_tiles("RUN IN PROGRESS") and at(3, 8, 13) == font_tiles("WILL BE LOST") [:12] + b"\xF2"
          and at(3, 10, 13)[:12] == font_tiles("ARE YOU SURE") and at(3, 10, 13)[-1] == 0xF0
          and at(4, 13, 2) == font_tiles("NO") and at(4, 15, 3) == font_tiles("YES")
          and g2.m[0x9C00 + 13 * 32 + 2] == 0x7E, "heading in column 3, NO and YES in column 4, cursor in 2")
    check("the store has not opened behind it", g2.m[0xC5DC] == 0 and g2.m[0xD002] & 2)
    g2.press("a", after=30)                             # NO is the default
    check("NO keeps the saved run and returns to the menu", g2.m[0xD002] & 2 and g2.m[0xC5DC] == 0
          and at(4, 7, 8) == font_tiles("CONTINUE"))
    g2.press("down", after=10)
    g2.press("a", after=30)
    g2.press("down", after=10)                          # YES
    g2.press("a", after=200)
    check("YES opens the store and throws the saved run away", g2.m[0xC5DC] == 1 and g2.m[0xD002] & 2 == 0)
    ram = g2.stop()
    check("the snapshot is gone from battery RAM", ram[0x16] == 0)
    g3 = Game(rom, "nr", fresh=False)
    g3.tick(200)
    g3.press("start", after=30)
    check("after a power cycle the title no longer offers CONTINUE", g3.m[0xD002] & 2 == 0 and g3.m[0xD002] & 1
          and bytes(g3.m[0x9C00 + 7 * 32 + 4 + k] for k in range(7)) == font_tiles("NEW RUN"))


def check_no_flash(control, rom):
    """Every change of screen with the LCD left on. Turning the LCD off shows a
    white screen on a Game Boy Color, and the first frame after it comes back on
    is not shown, which is the flash between menus this checks for."""
    print("No flashing")
    sites = [0x019D, 0x57B1, 0x57B7, 0x5824, 0x582A, 0x7B1D]       # the game's own LCDC writes

    def trace(path, tag):
        g = Game(path, tag)
        cycles = []

        def cb(site):
            new, old = g.pb.register_file.A, g.m[0xFF40]
            if (old ^ new) & 0x80 and not new & 0x80:
                cycles.append(site)
        for a in sites:
            g.pb.hook_register(0 if a < 0x4000 else 1, a, cb, a)
        data = open(path, "rb").read()
        for org, off, code in PIECES:
            if 0x4000 <= org < 0x8000:
                for i in range(len(code) - 1):
                    if code[i] == 0xE0 and code[i + 1] == 0x40:        # ldh (LCDC),a
                        g.pb.hook_register(2, org + i, cb, org + i)
        return g, cycles

    g, off = trace(control, "nf-stock")
    g.tick(200)
    del off[:]
    g.press("start", after=200)
    g.m[0xC5DB] = 1
    g.tick(300)
    for _ in range(4):
        g.press("start", after=80)
    check("the stock game changes screens without turning the LCD off (the control)", not off)

    g, off = trace(rom, "nf-patched")
    g.tick(200)
    del off[:]
    steps = []

    def step(name, *keys, after=60):
        del off[:]
        for k in keys:
            g.press(k, after=10)
        g.tick(after)
        steps.append((name, len(off)))
    g.press("start", after=200)
    g.m[0xC5DB] = 1
    g.tick(300)
    step("game over to store", "start")
    step("store to difficulty", "start")
    step("difficulty to weapon", "start")
    step("weapon to run", "start", after=200)
    for _ in range(200):
        g.m[0xC0CC] = 20
        g.tick(1)
    until_live(g)
    step("pause menu", "start")
    step("theme change in the menu", "select")
    step("resume", "a")
    step("pause again", "start")
    del off[:]
    g.press("down", after=10)
    g.press("a", after=300)
    quit_cycles = len(off)
    step("title menu", "start")
    step("NEW RUN confirm page", "down", "a")
    step("NO back to the menu", "a")
    step("ERASE SAVE page", "down", "down", "a")
    step("B back to the menu", "b")
    step("CONTINUE into the run", "up", "up", "a", after=300)
    flashes = [(n, c) for n, c in steps if c]
    check("no menu, page or CONTINUE change turns the LCD off", not flashes,
          ", ".join(f"{n}: {c}" for n, c in flashes) if flashes else f"{len(steps)} changes")
    check("SAVE & QUIT turns it off once, for the restart (as at power-on)", quit_cycles == 1,
          f"{quit_cycles} time(s)")


def check_menu_exits(rom):
    """NEW RUN and CONTINUE leave the title menu through the game's run start-up,
    which also shows the title and its wipe. Between the menu and the store, or
    the restored run, every frame must be one flat shade."""
    print("Leaving the title menu")
    for console in ("dmg", "cgb"):
        data = bytearray(open(rom, "rb").read())
        if console == "dmg":
            data[0x143] = 0
            fix_header(data)
        p = os.path.join(WORK, f"mx-{console}.gb")
        open(p, "wb").write(data)
        for choice in ("NEW RUN", "CONTINUE"):
            g = Game(p, "mx")
            start_run(g)
            if choice == "CONTINUE":
                until_live(g)
                g.tick(100)
                g.press("start", after=30)
                g.press("down", after=10)
                g.press("a", after=300)
            else:
                g.m[0xC5DB] = 1
                g.tick(300)
            g.stop()
            g = Game(p, "mx", fresh=False)
            g.tick(200)
            g.press("start", after=30)
            menu = g.screen().tobytes()
            restored = []
            frame = [0]
            g.pb.hook_register(2, _LABELS["restore_run"], lambda ctx: restored.append(frame[0]), None)
            shots = []
            g.pb.button_press("a")
            for f in range(90):
                frame[0] = f
                g.tick(1)
                if f == 4:
                    g.pb.button_release("a")
                im = g.screen()
                shots.append((im.tobytes(), len(im.getcolors(256) or ())))
            if choice == "NEW RUN":
                end = next(i for i, (b, _) in enumerate(shots) if b == shots[-1][0])
            else:
                end = restored[0] + 1 if restored else len(shots)
            between = [i for i, (b, n) in enumerate(shots[:end]) if b != menu and n > 1]
            check(f"{console}: {choice} goes from the menu to {'the store' if choice == 'NEW RUN' else 'the run'} "
                  "through one flat shade", end < len(shots) and not between,
                  f"frames {between[:8]} show something else" if between else f"{end} frames")


def check_menu_screens(rom):
    """Each menu page goes on screen in one step, cursor included, and SAVE &
    QUIT hides the run until its restart, which then looks like a power-on."""
    print("Menu pages and SAVE & QUIT")
    for console in ("dmg", "cgb"):
        data = bytearray(open(rom, "rb").read())
        if console == "dmg":
            data[0x143] = 0
            fix_header(data)
        p = os.path.join(WORK, f"ms-{console}.gb")
        open(p, "wb").write(data)

        def changes(g, button, n=40):
            g.pb.button_press(button)
            seen, prev = 0, g.screen().tobytes()
            for f in range(n):
                g.tick(1)
                if f == 4:
                    g.pb.button_release(button)
                b = g.screen().tobytes()
                seen += b != prev and g.m[0xFF4A] == 0 and g.m[0xFF40] & 0x20 != 0   # the menu's window
                prev = b
            return seen
        g = Game(p, "ms")
        cold = []
        for _ in range(300):
            g.tick(1)
            cold.append(g.screen().tobytes())
        start_run(g)
        until_live(g)
        g.tick(60)
        steps = [("pause menu", changes(g, "start"))]
        g.press("down", after=10)
        g.pb.button_press("a")
        menu = g.screen().tobytes()
        shown, off_at = [], None
        for f in range(400):
            g.tick(1)
            if f == 4:
                g.pb.button_release("a")
            im = g.screen()
            if off_at is None:
                if not g.m[0xFF40] & 0x80:
                    off_at = f
                elif im.tobytes() != menu and len(im.getcolors(256) or ()) > 1:
                    shown.append(f)
        last = g.screen().tobytes()
        check(f"{console}: SAVE & QUIT shows one flat shade until the LCD goes off for the restart",
              off_at is not None and not shown, f"frames {shown[:8]} show something else" if shown else f"{off_at} frames")
        check(f"{console}: the restart ends on the title a power-on shows", last == cold[-1])
        g.press("start", after=40)
        g.pb.button_release("start")
        for name, keys in (("NEW RUN confirm", ("down", "a")), ("NO", ("a",)),
                           ("ERASE SAVE page", ("down", "down", "a")), ("B back to the menu", ("b",))):
            for k in keys[:-1]:
                g.press(k, after=20)
            steps.append((name, changes(g, keys[-1])))
        bad = [f"{n}: {c}" for n, c in steps if c != 1]
        check(f"{console}: every menu page goes on screen in one step, with its cursor", not bad,
              ", ".join(bad) if bad else f"{len(steps)} pages")


def check_cross_console(rom):
    """A run saved on one kind of console and continued on the other: the run
    must draw its sprites the way this console does, and the restart after the
    next SAVE & QUIT must still know which console it is on."""
    print("Continuing on the other kind of console")
    data = bytearray(open(rom, "rb").read())
    data[0x143] = 0
    fix_header(data)
    paths = {"cgb": os.path.join(WORK, "xc-cgb.gb"), "dmg": os.path.join(WORK, "xc-dmg.gb")}
    open(paths["cgb"], "wb").write(rom if isinstance(rom, bytes) else open(rom, "rb").read())
    open(paths["dmg"], "wb").write(data)
    for saved_on, continued_on in (("dmg", "cgb"), ("cgb", "dmg")):
        g = Game(paths[saved_on], "xc")
        start_run(g)
        until_live(g)
        g.tick(100)
        g.press("start", after=40)
        g.press("down", after=10)
        g.press("a", after=300)
        ram = g.stop()
        g = Game(paths[continued_on], "xc")
        g.pb.stop(save=False)
        open(g.path + ".ram", "wb").write(ram)
        g = Game(paths[continued_on], "xc", fresh=False)
        g.tick(200)
        g.press("start", after=30)
        g.press("a", after=200)
        live = g.m[0xFF40] == 0xE3
        g.tick(30)
        page = g.m[0xFF92]
        player = (g.m[0xC090], g.m[0xC091])
        oam = [(g.m[0xFE00 + 4 * i], g.m[0xFE01 + 4 * i]) for i in range(40)]
        sprites = page == (0xDA if continued_on == "cgb" else 0xC0) and player in oam
        g.press("start", after=40)
        g.press("down", after=10)
        g.press("a", after=600)
        colors = len(g.screen().getcolors(256) or ())
        cgb = g.m[0xD011]
        check(f"saved on {saved_on}, continued on {continued_on}: the run's sprites come from the game's table",
              live and sprites, f"continued {live}, DMA page ${page:02X}, player {'in' if player in oam else 'not in'} OAM")
        check(f"saved on {saved_on}, continued on {continued_on}: SAVE & QUIT comes back to a visible title "
              "on the right console", live and colors > 1 and cgb == (continued_on == "cgb"),
              f"continued {live}, {colors} colors, color flag {cgb}")


def check_console_hops(rom):
    """One run saved and continued several times, moving between the two kinds
    of console. At each stop the run must come back as it was saved, behave as
    this console needs, keep playing, and quit to a visible title."""
    print("A run moving between consoles")
    data = bytearray(open(rom, "rb").read())
    paths = {"cgb": os.path.join(WORK, "hop-cgb.gb"), "dmg": os.path.join(WORK, "hop-dmg.gb")}
    open(paths["cgb"], "wb").write(data)
    data[0x143] = 0
    fix_header(data)
    open(paths["dmg"], "wb").write(data)
    fields = list(range(0xC5C1, 0xC5CD)) + [0xC5CF, 0xC5E5, 0xC5E6, 0xC0CB]     # upgrades, weapons, run money, max HP

    def quit_run(g):
        g.press("start", after=40)
        g.press("down", after=10)
        g.press("a", after=600)
        return g.m[0xFF40] == 0xC1 and len(g.screen().getcolors(256) or ()) > 1

    for chain in (("dmg", "cgb", "dmg"), ("cgb", "dmg", "cgb"), ("dmg", "dmg", "cgb"), ("cgb", "cgb", "dmg")):
        name = " > ".join(chain)
        g = Game(paths[chain[0]], "hop")
        start_run(g)
        play(g, 1500)
        until_live(g)
        g.tick(30)
        saved = [g.m[a] for a in fields]
        problems = [] if quit_run(g) else [f"{chain[0]}: SAVE & QUIT did not reach the title"]
        ram = g.stop()
        for console in chain[1:]:
            g = Game(paths[console], "hop")
            g.pb.stop(save=False)
            open(g.path + ".ram", "wb").write(ram)
            g = Game(paths[console], "hop", fresh=False)
            g.tick(200)
            g.press("start", after=30)
            back = []                                    # read once the restore has copied everything back
            g.pb.hook_register(2, _LABELS["rr_dma"], lambda ctx: back.extend(g.m[a] for a in fields), None)
            g.press("a", after=60)
            g.pb.hook_deregister(2, _LABELS["rr_dma"])
            if back != saved:
                print("    " + console + ": " + ", ".join(f"${a:04X} {x}->{y}" for a, x, y in zip(fields, saved, back) if x != y))
            cgb = console == "cgb"
            loops = [0]
            g.pb.hook_register(1, 0x58B8, lambda ctx: loops.__setitem__(0, loops[0] + 1), None)
            play(g, 600)
            g.pb.hook_deregister(1, 0x58B8)
            until_live(g)
            g.tick(30)
            oam = [(g.m[0xFE00 + 4 * i], g.m[0xFE01 + 4 * i]) for i in range(40)]
            expect = {"the run as saved": back == saved,
                      "the color flag": g.m[0xD011] == cgb,
                      "the sprite page": g.m[0xFF92] == (0xDA if cgb else 0xC0),
                      "the DMA wait": g.m[0xFF87] == (0x50 if cgb else 0x28),
                      "double speed": (g.m[0xFF4D] & 0x80 != 0) == cgb,
                      "playing on": loops[0] > 250 and g.m[0xFF40] == 0xE3,
                      "the player drawn": (g.m[0xC090], g.m[0xC091]) in oam}
            problems += [f"{console}: {k}" for k, ok in expect.items() if not ok]
            saved = [g.m[a] for a in fields]
            if not quit_run(g):
                problems.append(f"{console}: SAVE & QUIT did not reach a visible title")
            ram = g.stop()
        check(f"a run saved and continued {name} comes back each time as saved and as this console needs",
              not problems, ", ".join(problems) if problems else f"{len(chain) - 1} continues")


def check_motor_off(rom):
    """A hit just before the pause menu, a death or SAVE & QUIT must not leave
    the rumble motor running. A death keeps the run loop going, so a hit that
    came with it plays out its 6-frame kick."""
    print("Rumble motor off outside play")
    for console in ("dmg", "cgb"):
        data = bytearray(open(rom, "rb").read())
        if console == "dmg":
            data[0x143] = 0
            fix_header(data)
        p = os.path.join(WORK, f"mo-{console}.gb")
        open(p, "wb").write(data)
        g = Game(p, "mo")
        on = [False]
        g.pb.hook_register(2, _LABELS["hr_on_st"], lambda c: on.__setitem__(0, True), None)
        g.pb.hook_register(2, _LABELS["hr_off_st"], lambda c: on.__setitem__(0, False), None)
        g.pb.hook_register(2, _LABELS["hr_big_st"], lambda c: on.__setitem__(0, True), None)
        start_run(g)
        until_live(g)
        g.tick(30)
        bad = []

        def watch(name, frames, after_up=lambda: True, grace=0):
            for f in range(frames):
                g.tick(1)
                if f >= grace and after_up() and on[0]:
                    bad.append(f"{name} frame {f}")
                    return
        g.m[0xD01D] = 4                                  # a hit starts a pulse
        g.tick(1)
        started = on[0]
        g.press("start", after=0)
        watch("pause menu", 60, lambda: g.m[0xFF4A] == 0)
        g.press("a", after=30)                           # RESUME
        g.m[0xD01D] = 4
        g.m[0xC5DB] = 1                                  # and a death on the same frame: the hit's
        watch("game over", 300, lambda: g.m[0xC5B5] != 0, grace=8)   # 6-frame kick plays out
        for _ in range(3):
            g.press("start", after=60)                   # store, difficulty, weapon, into a run
        until_live(g)
        g.tick(30)
        g.m[0xD01D] = 4
        g.tick(1)
        g.press("start", after=40)
        g.press("down", after=10)
        g.pb.button_press("a")
        watch("SAVE & QUIT", 400, lambda: g.m[0xFF4A] == 0 or not g.m[0xFF40] & 0x80 or g.m[0xFF40] == 0xC1)
        check(f"{console}: the motor is off in menus, after a death's last hit kick and through SAVE & QUIT, even right after a hit",
              started and not bad, ", ".join(bad) if bad else "a hit started it each time")


def check_big_rumble(rom):
    """A boss's entrance runs the motor solid for a third of a second; a
    continued run with a boss already in play does not rumble."""
    print("Rumble on a boss's entrance")
    for console in ("dmg", "cgb"):
        data = bytearray(open(rom, "rb").read())
        if console == "dmg":
            data[0x143] = 0
            fix_header(data)
        p = os.path.join(WORK, f"br-{console}.gb")
        open(p, "wb").write(data)
        g = Game(p, "br")
        on = [False]
        for name, state in (("hr_on_st", True), ("hr_big_st", True), ("hr_off_st", False)):
            g.pb.hook_register(2, _LABELS[name], lambda c, s=state: on.__setitem__(0, s), None)
        start_run(g)
        held, motor, spawn = set(), [], None
        for f in range(20000):                          # play until the first boss comes in
            want = script(f)
            for b in held - want:
                g.pb.button_release(b)
            for b in want - held:
                g.pb.button_press(b)
            held = want
            g.m[0xC0CC] = 20
            g.tick(1, False)
            motor.append(on[0])
            if spawn is None and any(g.m[a] for a in range(0xC14A, 0xC15A)):
                spawn = f
            if spawn is not None and f > spawn + 40:
                break
        for b in held:
            g.pb.button_release(b)
        boss = spawn is not None and sum(motor[spawn:spawn + 20]) >= 19 and not any(motor[spawn + 22:spawn + 40])
        check(f"{console}: a boss's entrance runs the motor for 20 frames",
              boss, f"boss at frame {spawn}" if spawn is not None else "no boss in 20000 frames")
        until_live(g)
        g.press("start", after=40)
        g.press("down", after=10)
        g.press("a", after=400)
        ram = g.stop()
        g = Game(p, "br", fresh=False)
        on = [False]
        for name, state in (("hr_on_st", True), ("hr_big_st", True), ("hr_off_st", False)):
            g.pb.hook_register(2, _LABELS[name], lambda c, s=state: on.__setitem__(0, s), None)
        g.tick(200)
        g.press("start", after=30)
        g.press("a", after=10)
        quiet = []
        for _ in range(90):
            g.m[0xC0CC] = 20
            g.tick(1)
            quiet.append(on[0])
        longest = max((len(r) for r in "".join("#" if x else "." for x in quiet).split(".")), default=0)
        check(f"{console}: continuing a run with a boss in play does not rumble beyond hit pulses",
              any(g.m[a] for a in range(0xC14A, 0xC15A)) and longest <= 2, f"longest run {longest} frames")


def check_vram_timing(rom):
    """PyBoy lets the CPU reach video memory while the LCD is drawing a line;
    the hardware does not (the write is dropped, the read gives $FF). So every
    video memory and palette access the patch makes is checked here against the
    LCD's mode at that instruction."""
    print("Video memory access timing")
    for speed, path in (("original Game Boy", "dmg"), ("Game Boy Color, double speed", "cgb")):
        data = bytearray(open(rom, "rb").read())
        if path == "dmg":
            data[0x143] = 0
            fix_header(data)
        p = os.path.join(WORK, f"vt-{path}-rom.gb")
        open(p, "wb").write(data)
        g = Game(p, "vt-" + path)
        hits, bad = [0], [0]

        def cb(ctx):
            hits[0] += 1
            if g.m[0xFF41] & 3 == 3:
                bad[0] += 1
        # Only the stores are hooked: PyBoy stalls with hooks on two adjacent
        # one-byte instructions. vcopy's read (vc_ld) is the instruction right
        # before its store, 2 cycles earlier, and mode 3 lasts at least 43, so a
        # read in mode 3 puts its store there too and is caught here.
        for name in ("vc_st", "vf_st", "pf_st", "ov01_st", "bo_bgst", "bo_obst"):
            g.pb.hook_register(2, _LABELS[name], cb, None)
        start_run(g)
        play(g, 300)
        until_live(g)
        g.press("start", after=40)
        g.press("select", after=20)
        g.press("a", after=40)
        g.press("start", after=40)
        g.press("down", after=10)
        g.press("a", after=300)
        g.press("start", after=40)
        g.press("down", after=10)
        g.press("a", after=40)
        g.press("a", after=40)
        g.press("up", after=10)
        g.press("a", after=300)
        check(f"{speed}: no video memory or palette access while a line is drawn", hits[0] > 1000 and bad[0] == 0,
              f"{hits[0]} accesses, {bad[0]} in mode 3")


def check_glyphs(rom):
    print("Punctuation glyphs")
    data = open(rom, "rb").read()
    at = 2 * 0x4000 + _LABELS["glyphs"] - 0x4000
    g = Game(rom, "glyph")
    g.tick(200)
    vram = bytes(g.m[0x8F00 + i] for i in range(96))
    check("the six glyph tiles are in video memory", vram == data[at:at + 96] and any(vram))
    seen = {}
    for ch in "?!.,'&A0 :":
        stub = [0x3E, 0x02, 0xEA, 0x00, 0x20, 0x3E, ord(ch), 0xCD, _LABELS["tile_of"] & 0xFF, _LABELS["tile_of"] >> 8,
                0xEA, 0x20, 0xDC, 0x18, 0xFE]              # bank 2, ld a,ch, call tile_of, store, spin
        for i, b in enumerate(stub):
            g.m[0xDC00 + i] = b
        g.pb.register_file.PC = 0xDC00
        g.tick(2, False)
        seen[ch] = g.m[0xDC20]
    check("the game's text routine maps ? ! . , ' & to tiles $F0-$F5 and leaves the old characters alone",
          [seen[c] for c in "?!.,'&"] == [0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5] and seen["A"] == 0x55 and seen["0"] == 0x6F
          and seen[" "] == 0x7F and seen[":"] == 0x79)
    g = Game(rom, "glyph-save")                         # the routine test above leaves its emulator in a spin loop
    start_run(g)
    g.m[0xC5E5], g.m[0xC5E6] = 0x2C, 0x01
    g.m[0xC5DB] = 1
    g.tick(300)
    g.stop()
    g2 = Game(rom, "glyph-save", fresh=False)
    g2.tick(200)
    g2.press("start", after=30)
    g2.press("down", after=10)
    g2.press("a", after=30)
    row = bytes(g2.m[0x9C00 + 6 * 32 + 3 + k] for k in range(13))
    check("the erase page asks ARE YOU SURE? with a question mark", row[-1] == 0xF0 and row[0] == 0x55)
    g3 = Game(rom, "glyph3")
    start_run(g3)
    g3.press("start", after=40)
    row = bytes(g3.m[0x9C00 + 9 * 32 + 4 + k] for k in range(11))
    check("the pause menu reads SAVE & QUIT", row[5] == 0xF5 and row[0] == 0x67)


def sprite_overflow(game, frames):
    """Frames where a scanline holds more than ten sprites, and how many of
    those lose a piece of the player (shadow OAM $C090-$C09F)."""
    m = game.m
    over = dropped = 0
    for f in range(frames):
        want = script(f)
        for b in ("up", "right", "down", "left", "a"):
            (game.pb.button_press if b in want else game.pb.button_release)(b)
        m[0xC0CC] = 20
        game.tick(1, False)
        oam = [(m[0xFE00 + i * 4], m[0xFE00 + i * 4 + 1], m[0xFE00 + i * 4 + 2]) for i in range(40)]
        player = {tuple(m[0xC090 + k * 4 + j] for j in range(3)) for k in range(4)}
        hit = lost = False
        for ly in range(144):
            sel = [i for i, (y, x, t) in enumerate(oam) if y - 16 <= ly < y - 8]
            if len(sel) > 10:
                hit = True
                lost = lost or any(oam[i] in player and 0 < oam[i][1] < 168 for i in sel[10:])
        over += hit
        dropped += lost
    return over, dropped


def check_sprites(control, rom, frames=40000):
    print("Sprite limit")
    results = {}
    for name, path in (("stock", control), ("patched", rom)):
        g = Game(path, "spr-" + name)
        start_run(g)
        results[name] = sprite_overflow(g, frames)
    (so, sd), (po, pd) = results["stock"], results["patched"]
    check("stock loses part of the player on crowded lines (the control)", sd > 0, f"{sd} of {so} overflow frames")
    check("the player is never dropped in the patched game", pd == 0, f"{po} overflow frames, all enemy sprites")


def check_scroll(control, rom):
    print("Scroll tearing")
    # Stock: the game's four scroll writes, and whether they land on a visible line.
    g = Game(control, "scr-stock")
    hits = [0, 0]

    def count(ctx):
        hits[0 if g.m[0xFF44] < 144 else 1] += 1
    for at in (0x3BA4, 0x3BBF, 0x3BD6, 0x3BF1):
        g.pb.hook_register(0, at, count, None)
    start_run(g)
    play(g, 6000)
    check("stock writes the scroll registers during the visible picture (the control)",
          hits[0] > 0, f"{hits[0]} of {sum(hits)} writes")

    # Patched: compare the hardware registers where the VBlank handler finishes
    # ($00A7, after its call) and where the game's logic ends ($7AFD, the frame
    # wait). If they always match, nothing wrote them in between, which is all of
    # the visible picture.
    g = Game(rom, "scr-patched")
    seen = {}
    moved = [0, 0]                                      # frames where they differ, frames compared

    def after_vblank(ctx):
        seen["r"] = (g.m[0xFF42], g.m[0xFF43])

    def logic_done(ctx):
        if "r" in seen:
            moved[1] += 1
            moved[0] += seen["r"] != (g.m[0xFF42], g.m[0xFF43])
    g.pb.hook_register(0, 0x00A7, after_vblank, None)
    g.pb.hook_register(1, 0x7AFD, logic_done, None)
    start_run(g)
    play(g, 6000)
    scrolled = g.m[0xFF94] or g.m[0xFF95]
    check("the patched game never changes the scroll registers between VBlanks", moved[0] == 0 and moved[1] > 1000 and scrolled,
          f"{moved[1]} frames compared, camera at {g.m[0xFF94]},{g.m[0xFF95]}")


def check_color(stock, rom):
    print("Color and double speed")
    g = Game(rom, "col")
    g.tick(200)
    check("a Game Boy Color is detected and runs at double speed", g.m[0xD011] == 1 and g.m[0xFF4D] & 0x80)
    dmg = bytearray(open(rom, "rb").read())
    dmg[0x143] = 0
    fix_header(dmg)
    dpath = os.path.join(WORK, "dmg-rom.gb")
    open(dpath, "wb").write(dmg)
    d = Game(dpath, "dmg")
    d.tick(200)
    check("an original Game Boy stays at single speed with the game's own palettes",
          d.m[0xD011] == 0 and d.m[0xFF4D] & 0x80 == 0 and d.m[0xFF47] == 0xE1 and d.m[0xFF49] == 0x6C,
          f"BGP {d.m[0xFF47]:02x} OBP1 {d.m[0xFF49]:02x}")

    def enc(c):
        r, g_, b = c
        return (b >> 3) << 10 | (g_ >> 3) << 5 | (r >> 3)

    def palette(m, reg_i, reg_d, n):
        out = []
        for i in range(n):
            m[reg_i] = i
            out.append(m[reg_d])
        return [out[i] | out[i + 1] << 8 for i in range(0, n, 2)]

    want_bg = [enc(THEME0[s]) for s in (1, 0, 2, 3)]
    want_o1 = [enc(THEME0[s]) for s in (0, 3, 2, 1)]
    bg = palette(g.m, 0xFF68, 0xFF69, 8)
    ob = palette(g.m, 0xFF6A, 0xFF6B, 16)
    check("palette RAM holds the theme through the game's shades",
          bg == want_bg and ob[:4] == want_bg and ob[4:] == want_o1)

    shots = {}
    for name, game in (("dmg", d), ("cgb", g)):
        game.m[0xC5E5], game.m[0xC5E6] = 0x2C, 0x01
        game.press("start", after=120)
        game.m[0xC5DB] = 1
        game.tick(300)
        shots[name] = {"gameover": game.screen()}
        game.press("start", after=60)
        shots[name]["store"] = game.screen()
        game.press("start", after=60)
        shots[name]["difficulty"] = game.screen()
    same = all(shades(shots["dmg"][k], PY_DMG) == shades(shots["cgb"][k], THEME0) for k in shots["dmg"])
    check("game over, store and difficulty screens have the same shades in color and gray", same)

    g2 = Game(rom, "theme")
    g2.tick(200)
    first = palette(g2.m, 0xFF68, 0xFF69, 8)[0]
    g2.press("select", after=40)
    second = palette(g2.m, 0xFF68, 0xFF69, 8)[0]
    g2.press("select", after=40)
    ram = g2.stop()
    g3 = Game(rom, "theme", fresh=False)
    g3.tick(200)
    check("SELECT on the title changes the theme, and the choice is saved",
          first != second and ram[0x14] == 2 and ram[0x14] ^ 0x5A == ram[0x15] and g3.m[0xD012] == 2)

    # the theme can be changed anywhere: in a run, in the pause menu (which names it), in the store
    g4 = Game(rom, "theme2")
    start_run(g4)
    a = palette(g4.m, 0xFF68, 0xFF69, 8)[0]
    g4.press("select", after=10)
    b = palette(g4.m, 0xFF68, 0xFF69, 8)[0]
    until_live(g4)
    g4.press("start", after=40)
    name = lambda: bytes(g4.m[0x9C00 + 15 * 32 + 10 + k] for k in range(6))
    before = name()
    g4.press("select", after=10)
    c = palette(g4.m, 0xFF68, 0xFF69, 8)[0]
    line = bytes(g4.m[0x9C00 + 15 * 32 + 2 + k] for k in range(8))
    check("SELECT changes the theme during a run and in the pause menu, which names the theme",
          a != b and b != c and name() != before and line == bytes([0x67, 0x59, 0x60, 0x59, 0x57, 0x68, 0x79, 0x7F]),
          "SELECT: <name>")
    g4.press("b", after=30)
    g4.m[0xC5DB] = 1
    g4.tick(300)
    g4.press("start", after=60)
    d = palette(g4.m, 0xFF68, 0xFF69, 8)[0]
    g4.press("select", after=10)
    check("SELECT changes the theme in the store", g4.m[0xC5DC] == 1 and d != palette(g4.m, 0xFF68, 0xFF69, 8)[0])


def frame_budget(control, rom, frames=12000):
    print("Frame budget (informational)")

    def run(path, tag):
        g = Game(path, tag)
        start_run(g)
        use = []

        def w(ctx):
            use.append(((g.m[0xFF44] - 144) % 154) / 154)
        g.pb.hook_register(1, 0x7AFD, w, None)
        play(g, frames)
        s = sorted(use)
        return s[len(s) // 2], s[int(len(s) * 0.95)], s[-1]
    dmg = bytearray(open(rom, "rb").read())
    dmg[0x143] = 0
    fix_header(dmg)
    dpath = os.path.join(WORK, "dmg2-rom.gb")
    open(dpath, "wb").write(dmg)
    for name, path in (("stock", control), ("patched, single speed", dpath), ("patched, double speed", rom)):
        med, p95, peak = run(path, "fb-" + name[:4] + name[-5:-4])
        print(f"    {name:<24} median {med:4.0%}  p95 {p95:4.0%}  peak {peak:4.0%} of a frame")


_LABELS = {}
PIECES = []


def main():
    stock = open(sys.argv[1], "rb").read()
    rom = open(sys.argv[2], "rb").read()
    rumble = rom[0x147] == 0x1E                         # the rumble build, or the MBC1 one
    ips = os.path.join(HERE, "LegionOfEvil-rumble.ips" if rumble else "LegionOfEvil-save.ips")
    global _LABELS, PIECES
    profile = patcher.load_profile(stock)
    PIECES, _LABELS = patcher.assemble_sections(profile)
    control = os.path.join(WORK, "control.gb")
    open(control, "wb").write(build_control(stock))
    rompath = os.path.join(WORK, "patched.gb")
    open(rompath, "wb").write(rom)

    print("Build:", "MBC5+RUMBLE" if rumble else "MBC1, no rumble")
    check_rom(stock, rom, ips, rumble)
    check_no_save_start(rompath)
    check_power_on_bank(rompath)
    check_held_start(control, rompath)
    check_save_cycle(rompath)
    check_hit_pulse(control, rompath, rumble)
    if rumble:
        check_motor_off(rompath)
        check_big_rumble(rompath)
    else:
        check_motor_harmless(rompath)
    check_erase(rompath)
    check_pause(rompath)
    check_continue(rompath)
    dmgpath = os.path.join(WORK, "patched-dmg.gb")
    data = bytearray(rom)
    data[0x143] = 0
    fix_header(data)
    open(dmgpath, "wb").write(data)
    check_continue(dmgpath, label="dmg: ")
    check_power_on_bank(dmgpath, label="dmg: ")
    check_glyphs(rompath)
    check_new_run_confirm(rompath)
    check_no_flash(control, rompath)
    check_menu_exits(rompath)
    check_menu_screens(rompath)
    check_cross_console(rompath)
    check_console_hops(rompath)
    check_vram_timing(rompath)
    check_sprites(control, rompath)
    check_scroll(control, rompath)
    check_color(stock, rompath)
    frame_budget(control, rompath)

    failed = [n for n, ok in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)} of {len(RESULTS)} checks passed")
    shutil.rmtree(WORK, ignore_errors=True)
    if failed:
        print("failed:", *failed, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
