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
# Shades the game picks from, and the color theme the patch starts with
PY_DMG = [(255, 255, 255), (169, 169, 169), (84, 84, 84), (0, 0, 0)]
THEME0 = [(224, 248, 208), (136, 192, 112), (52, 104, 86), (8, 24, 32)]

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
def check_rom(stock, rom, ips_path):
    print("ROM")
    check("stock ROM is the profiled release", hashlib.md5(stock).hexdigest() == STOCK_MD5)
    check("patched ROM is 64 KB MBC1+RAM+BATTERY with 8 KB RAM and the color flag",
          len(rom) == 0x10000 and rom[0x147] == 3 and rom[0x148] == 1 and rom[0x149] == 2 and rom[0x143] == 0x80)
    check("header checksum is valid", patcher.header_checksum(rom) == rom[0x14D])
    g = patcher.global_checksum(rom)
    check("global checksum is valid", g == (rom[0x14E] << 8 | rom[0x14F]))
    check("music player asks for bank 1 at all seven calls",
          all(rom[a - 7] == 1 and stock[a - 7] == 2 for a in patcher.ROM_PROFILES[STOCK_MD5]["music_bank_loads"]))
    if ips_path and os.path.exists(ips_path):
        check("the committed IPS applied to the stock ROM gives this ROM", apply_ips(stock, open(ips_path, "rb").read()) == rom)
    check("patch.py is deterministic", patcher.patch(stock, verbose=False) == rom)


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
    check("the pause menu offers RESUME and SAVE AND QUIT, and nothing below them",
          rows[0].startswith(bytes([0x66, 0x59, 0x67, 0x69])) and rows[1][:4] == bytes([0x67, 0x55, 0x6A, 0x59]) and rows[2] == bytes([0x7F] * 13))
    g.press("a", after=20)
    check("RESUME returns to the run: the game ticks again, the HUD window and sprites are back",
          g.m[0xC0D9] != tick and g.m[0xFF4A] == 0x80 and g.m[0xFF40] & 0x02 and g.m[0xC5B5] == 0)


def check_continue(rom, tick_count=900):
    print("Save and quit, continue")

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
    sub.press("a", after=400)                           # SAVE AND QUIT
    title_back = sub.m[0xFF40] == 0xC1
    ram = sub.stop()
    check("SAVE AND QUIT writes a snapshot and lands on the title", ram[0x16] == 0x5A and title_back)
    sub2 = Game(rom, "sub", fresh=False)
    sub2.tick(200)
    check("after a power cycle the title offers CONTINUE", sub2.m[0xD002] & 3 == 3)
    sub2.press("start", after=30)
    sub2.pb.button_press("a")
    sub2.tick(1)
    sub2.pb.button_release("a")
    sync(sub2, (t0 + 25) & 0xFF)
    rec_sub = record(sub2, tick_count)
    # Game memory, the sprite table and video memory must match on every frame.
    # Screens may differ only by a sliver on one scanline: the stock game writes
    # its background map while the picture is drawn (about three quarters of its
    # tile writes land on a visible line), so the same state can draw a few
    # pixels of one line differently depending on the exact cycle. Frames where a
    # line holds more than ten sprites are skipped, because the enemy order on
    # such a line follows a counter that is not game state.
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
            if len(px) > 16 or len({p // 160 for p in px}) > 1:
                screen_bad.append(i)
            else:
                slivers += 1
    bad = state_bad + screen_bad
    check(f"a continued run is identical to an uninterrupted one for {tick_count} frames",
          not bad, f"{len(state_bad)} frames with different memory, {len(screen_bad)} with different screens" if bad else
          f"memory, sprites and video memory on every frame; {slivers} frame(s) had a one-line sliver of difference")
    ram = sub2.stop()
    check("CONTINUE uses the snapshot up", ram[0x16] == 0)

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
    check("a damaged snapshot is not offered", sub4.m[0xD002] & 2 == 0 and sub4.m[0xD002] & 1 == 1)


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


def main():
    stock = open(sys.argv[1], "rb").read()
    rom = open(sys.argv[2], "rb").read()
    ips = os.path.join(HERE, "LegionOfEvil-save.ips")
    global _LABELS
    profile = patcher.load_profile(stock)
    _, _LABELS = patcher.assemble_sections(profile)
    control = os.path.join(WORK, "control.gb")
    open(control, "wb").write(build_control(stock))
    rompath = os.path.join(WORK, "patched.gb")
    open(rompath, "wb").write(rom)

    check_rom(stock, rom, ips)
    check_no_save_start(rompath)
    check_save_cycle(rompath)
    check_erase(rompath)
    check_pause(rompath)
    check_continue(rompath)
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
