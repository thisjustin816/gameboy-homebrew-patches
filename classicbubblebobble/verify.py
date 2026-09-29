#!/usr/bin/env python3
"""Check the Classic Bubble Bobble patch in emulation.

usage: verify.py STOCK.gbc PATCHED.gbc

Needs `pip install pyboy pillow`. Every run starts from a cold boot: through
the title into round 1, or into the PASSWORD screen. Rounds other than round 1
are started the way the game starts any round, with the round number changed
as the round loader reads it.
"""
import hashlib
import io
import os
import random
import shutil
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore")
from pyboy import PyBoy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch as P

PROFILE = next(iter(P.ROM_PROFILES.values()))
C = PROFILE["consts"]
SV = PROFILE["save"]
SC = SV["consts"]
STATE = 0xD301                          # Bub's state: 0 while he plays, other values while he dies
TRAPPED = 2                             # an enemy's state (STATE + 4n) once a shot has trapped it
ROUND_LOAD = (1, 0x419B)                # the round loader reads the round here
FRAME_END = 0x0B8B                      # runs once a frame on every screen
INVINCIBLE = 0xC484                     # while nonzero Bub can't be hit, as after a new life
SRAM_SIZE = 0x2000
GRID = ["BCDFGHJK", "LMNPQRST", "VWXZ1345"]
PASSWORDS = {1: "BBBB", 5: "GGBB", 10: "MBMB", 20: "GFBC", 30: "TRCC", 40: "NCDK", 50: "HFCC", 60: "SBFP"}
FLOOR_Y = 232                           # Bub standing on round 1's floor
SMS_NEAR_TOP = [10, 12, 14, 18]         # Master System frames within 0, 1, 2 and 4 px of a jump's top
failures = []


def check(ok, what):
    print(f"   {'ok  ' if ok else 'FAIL'} {what}")
    if not ok:
        failures.append(what)


def rom_copy(rom, ram=None):
    """A private copy of the ROM, with a battery file if there is one to start from."""
    path = os.path.join(tempfile.mkdtemp(), "game.gbc")
    shutil.copy(rom, path)
    if ram is not None:
        open(path + ".ram", "wb").write(ram)
    return path


def sram_image(route, rnd, good=True, sig=(0xB0, 0xB1)):
    s = ((route + rnd) & 0xFF) ^ SC["SUM_XOR"]
    body = bytes([sig[0], sig[1], route, rnd, s if good else s ^ 1])
    return body + b"\xFF" * (SRAM_SIZE - len(body))


class Game:
    def __init__(self, rom, ram=None, cgb=True, wram_garbage=()):
        self.path = rom_copy(rom, ram)
        self.pb = PyBoy(self.path, window="null", sound_emulated=False, cgb=cgb)
        self.m = self.pb.memory
        self.loads = 0
        self.force = None
        self.invincible = False
        self.pb.hook_register(*ROUND_LOAD, self._load, None)
        if wram_garbage:
            def garbage(_):
                for a in wram_garbage:
                    self.m[a] = 0xFF
            self.pb.hook_register(0, 0x0150, garbage, None)

    def _load(self, _):
        self.loads += 1
        if self.force:
            self.m[SC["ROUTE"]], self.m[SC["ROUND"]] = self.force
            self.force = None

    def tick(self, n=1):
        if not self.invincible:
            self.pb.tick(n, True)
            return
        for _ in range(n):
            self.m[INVINCIBLE] = 0x10
            self.pb.tick(1, True)

    def press(self, b, after=12):
        self.pb.button(b, 4)
        self.tick(4 + after)

    def hold(self, keys, n):
        for k in keys:
            self.pb.button_press(k)
        self.tick(n)
        for k in keys:
            self.pb.button_release(k)

    def new_game(self, force=None):
        self.force = force
        self.tick(600)
        target = self.loads + 1
        for _ in range(8):              # START through the title and menus, until a round loads
            self.pb.button("start", 4)
            self.tick(90)
            if self.loads >= target:
                break
        self.until_round(target)

    def until_round(self, target=None, limit=3000):
        target = target or self.loads + 1
        for _ in range(limit):
            if self.loads >= target:
                break
            self.tick()
        for _ in range(limit):
            if self.m[C["GROUND"]] and self.m[STATE] == 0:
                break
            self.tick()
        self.tick(30)

    def to_password(self):
        self.tick(600)
        for _ in range(3):
            self.pb.button("start", 4)
            self.tick(90)
        self.press("down", 16)
        self.press("a", 56)

    def type_word(self, word):
        """Type four letters from the grid's first letter. After the fourth the cursor is on END."""
        for n, ch in enumerate(word):
            r = next(i for i, row in enumerate(GRID) if ch in row)
            c = GRID[r].index(ch)
            for _ in range(r):
                self.press("down")
            for _ in range(c):
                self.press("right")
            self.press("a", 20)
            if n == len(word) - 1:
                break
            for _ in range(r):
                self.press("up")
            for _ in range(c):
                self.press("left")

    def pw_state(self):
        return ([self.m[SC["BUFFER"] + i] for i in range(4)] + [self.m[SC["SLOT"]], self.m[SC["ROW"]]]
                + [self.m[SC["SLOT_VRAM"] + 2 * i] for i in range(4)])

    def frames(self, n=80):
        out = []
        for _ in range(n):
            self.tick()
            out.append(hashlib.md5(self.pb.screen.image.convert("RGB").tobytes()).hexdigest()[:10])
        return out

    def sram(self, n=5):
        return bytes(self.m[0, 0xA000 + i] for i in range(n))

    def snapshot(self):
        s = io.BytesIO()
        self.pb.save_state(s)
        return s.getvalue()

    def restore(self, snap):
        self.pb.load_state(io.BytesIO(snap))

    def xy(self):
        return self.m[C["X"]], self.m[C["Y"]]

    def stop(self, save=False):
        self.pb.stop(save=save)
        return open(self.path + ".ram", "rb").read() if save else None


def play(g, seed, frames, record=None):
    rng = random.Random(seed)
    keys = ["left", "right", "a", "b", None]
    held = []
    for f in range(frames):
        if f % 9 == 0:
            held = [k for k in (rng.choice(keys), rng.choice(keys)) if k]
        for k in held:
            g.pb.button_press(k)
        g.tick()
        for k in held:
            g.pb.button_release(k)
        if record:
            record(g)


# ---------------------------------------------------------------- the ROM

def apply_ips(original, ips):
    """A plain IPS applier (data and RLE records), independent of make_ips."""
    assert ips[:5] == b"PATCH"
    out, i = bytearray(original), 5
    while ips[i:i + 3] != b"EOF":
        offset = int.from_bytes(ips[i:i + 3], "big")
        size = int.from_bytes(ips[i + 3:i + 5], "big")
        i += 5
        if size == 0:
            size = int.from_bytes(ips[i:i + 2], "big")
            data = bytes([ips[i + 2]]) * size
            i += 3
        else:
            data = ips[i:i + size]
            i += size
        if len(out) < offset + size:
            out.extend(b"\x00" * (offset + size - len(out)))
        out[offset:offset + size] = data
    return bytes(out)


def footprint(stock, patched):
    print("footprint")
    s, p = open(stock, "rb").read(), open(patched, "rb").read()
    check(hashlib.md5(s).hexdigest() in P.ROM_PROFILES, "the stock ROM is the release the patch is made for")
    check(P.patch(s, verbose=False) == p, "the patched ROM is exactly what patch.py builds from the stock one")
    ips = P.make_ips(s, p)
    check(apply_ips(s, ips) == p, f"the {len(ips)}-byte IPS patch turns the stock ROM into the patched one")
    code, _ = P.assemble_code(PROFILE)
    at = P.file_offset(PROFILE, PROFILE["phys_org"])
    allowed = set(range(at, at + len(code)))
    allowed |= {P.file_offset(PROFILE, PROFILE["table_ptr"][0]) + k for k in range(3)}
    allowed |= {P.file_offset(PROFILE, a) + 1 for a in PROFILE["jump_starts"]}
    allowed |= {P.file_offset(PROFILE, a) + k for a in PROFILE["bounce_starts"] for k in range(5)}
    allowed |= {P.file_offset(PROFILE, PROFILE["retired"][0]) + k for k in range(3)}
    for off, _, new in PROFILE["shot"] + PROFILE["bubbles"] + PROFILE["takeoff"]:
        allowed |= {P.file_offset(PROFILE, off) + k for k in range(len(bytes.fromhex(new)))}
    allowed |= {P.file_offset(PROFILE, PROFILE["fire_gate"][0]) + k for k in range(4)}
    save, _ = P.assemble_save(PROFILE)
    allowed |= set(range(SV["org"], SV["org"] + len(save)))
    for bank, address, _, _ in SV["hooks"]:
        f = bank * P.BANK_SIZE + address - P.BANK_SIZE if bank else address
        allowed |= set(range(f, f + 3))
    allowed |= set(SV["header"]) | {0x14D, 0x14E, 0x14F}
    header_ok = all(p[a] == now for a, (_, now) in SV["header"].items())
    untouched = s[0x100:0x147] == p[0x100:0x147] and s[0x148] == p[0x148] and s[0x14A:0x14D] == p[0x14A:0x14D]
    check(len(p) == len(s) and header_ok and untouched and P.header_checksum(p) == p[0x14D],
          "same size, MBC5+RAM+BATTERY with 8 KB of RAM in the header, and the rest of the header intact")
    changed = [i for i in range(len(s)) if s[i] != p[i]]
    stray = [hex(i) for i in changed if i not in allowed]
    check(not stray, f"{len(changed)} stock bytes differ, all at the patch's own sites (stray: {stray[:5]})")


def scripted(rom, seed=1, wram_garbage=()):
    """Password entry, then a new game and seeded play: the frames, and the borrowed WRAM each frame."""
    frames, seen = [], set()

    def rec(g):
        frames.append(hashlib.md5(g.pb.screen.image.convert("RGB").tobytes()).hexdigest()[:10])
        seen.update((a, g.m[a]) for a in PROFILE["wram"])
    g = Game(rom, wram_garbage=wram_garbage)
    g.to_password()
    frames += g.frames(60)
    g.type_word("GFBC")
    frames += g.frames(30)
    g.stop()
    g = Game(rom, wram_garbage=wram_garbage)
    g.new_game()
    play(g, seed, 2400, rec)
    g.stop()
    return frames, seen


def filler_unused(stock, tmp):
    print("the space and WRAM the patch borrows")
    s = bytearray(open(stock, "rb").read())
    filled = bytearray(s)
    lo, hi = PROFILE["padding"]
    filled[P.file_offset(PROFILE, lo):P.file_offset(PROFILE, hi)] = b"\xFF" * (hi - lo)
    lo0, hi0 = SV["padding"]
    filled[lo0:hi0] = b"\xFF" * (hi0 - lo0)
    control = bytearray(s)
    control[0x40] = 0xD9                # reti: the VBlank handler never runs
    paths = {}
    for name, data in (("filled", filled), ("control", control)):
        paths[name] = os.path.join(tmp, name + ".gbc")
        open(paths[name], "wb").write(bytes(data))
    ref, seen = scripted(stock)
    f, _ = scripted(paths["filled"])
    c, _ = scripted(paths["control"])
    check(f == ref, f"filling bank 2 ${lo:04X}-${hi - 1:04X} and bank 0 ${lo0:04X}-${hi0 - 1:04X} with $FF "
          f"changes none of {len(ref)} frames of password entry and play")
    diff = sum(a != b for a, b in zip(ref, c))
    check(diff > len(ref) // 2, f"control: breaking the VBlank vector changes {diff} of them")
    _, garbage = scripted(stock, wram_garbage=PROFILE["wram"])
    check(len(seen) == len(PROFILE["wram"]) and len(garbage) == len(PROFILE["wram"]),
          "the stock game never changes " + " or ".join(f"${a:04X}" for a in PROFILE["wram"])
          + ", starting from 0 or from $FF")


# ---------------------------------------------------------------- physics

class Round1:
    """Round 1 from a cold boot, with Bub standing at the start (x 32, on the floor)."""

    def __init__(self, rom):
        self.g = Game(rom)
        self.g.new_game()
        self.g.invincible = True        # the enemies would otherwise catch him partway through
        self.start = self.g.snapshot()

    def walk_to(self, x):
        g = self.g
        g.restore(self.start)
        key = "right" if x > g.xy()[0] else "left"
        g.pb.button_press(key)
        while (g.xy()[0] < x) if key == "right" else (g.xy()[0] > x):
            g.tick()
        g.pb.button_release(key)
        g.tick(20)

    def jump(self, takeoff, after, frames=110):
        """A with the keys in takeoff for 3 frames, then the keys in after. Returns (x, y, grounded) each frame."""
        g, out = self.g, []
        for i in range(frames):
            keys = ["a"] + takeoff if i < 3 else after
            for k in keys:
                g.pb.button_press(k)
            g.tick()
            for k in keys:
                g.pb.button_release(k)
            out.append((g.m[C["X"]], g.m[C["Y"]], g.m[C["GROUND"]]))
        return out


def arc_stats(trace, y0):
    ys = [t[1] for t in trace]
    top = min(ys)
    left = next(i for i, t in enumerate(trace) if t[1] != y0)
    back = next((i for i in range(left + 1, len(trace)) if trace[i][2] and trace[i][1] == trace[-1][1]), None)
    return y0 - top, ys.count(top), (back - left + 1) if back else None, y0 - trace[-1][1]


def speed(trace, frames=16):
    """Sideways px per frame over the first 8 ticks in the air, before the arc
    reaches the ends of round 1's platforms, which stop Bub like a wall."""
    left = next(i for i, t in enumerate(trace) if not t[2])
    return round((trace[left + frames][0] - trace[left][0]) / frames, 3)


def physics(stock, patched):
    print("physics (px per frame, from round 1)")
    got = {}
    for name, rom in (("stock", stock), ("patched", patched)):
        r = Round1(rom)
        g = r.g
        x0, y0 = g.xy()
        res = {"start": (x0, y0)}
        res["ledge5"] = arc_stats(r.jump([], []), y0)[3]            # the 5-tile ledge above the start
        r.walk_to(128)                                               # under the centre platform, 6 tiles up
        res["ledge6"] = arc_stats(r.jump([], []), y0)[3]
        r.walk_to(88)                                                # nothing above for 11 tiles
        res["open"] = arc_stats(r.jump([], []), y0)
        res["hold"] = speed(r.jump(["right"], ["right"]))
        r.walk_to(88)
        res["release"] = speed(r.jump(["right"], []))
        r.walk_to(88)
        res["against"] = speed(r.jump(["right"], ["left"]))
        r.walk_to(88)
        res["steer"] = speed(r.jump([], ["right"]))
        g.restore(r.start)                                           # walking along the floor
        g.tick(5)
        xa = g.xy()[0]
        g.hold(["right"], 30)
        res["walk"] = round((g.xy()[0] - xa) / 30, 3)
        res["takeoff"] = []
        for phase in (0, 1):                                         # frames from the press to leaving the ground
            r.walk_to(88)
            g.tick(phase)
            t = r.jump([], [], 12)
            res["takeoff"].append(next(i for i, (_, y, _) in enumerate(t) if y < y0))
        r.walk_to(88)
        arc = [y0 - y for _, y, _ in r.jump([], [])]
        res["near_top"] = [sum(1 for h in arc if h >= max(arc) - k) for k in (0, 1, 2, 4)]
        g.restore(r.start)                                           # onto the ledge, then jump off it
        r.jump([], [])
        g.hold(["right"], 10)
        ya = g.xy()[1]
        t = r.jump(["right"], ["right"], 80)
        ys = [y for _, y, _ in t]
        res["below_start"] = [ys[i + 2] - ys[i] for i in range(len(ys) - 2) if ys[i] > ya + 4 and ys[i + 2] < FLOOR_Y][:8]
        g.restore(r.start)                                           # up onto the ledge, then off its edge
        r.jump([], [])
        g.pb.button_press("right")
        while g.m[C["GROUND"]]:
            g.tick()
        xa, ya = g.xy()
        g.tick(16)
        xb, yb = g.xy()
        g.pb.button_release("right")
        res["walkoff"] = (round((yb - ya) / 16, 3), round((xb - xa) / 16, 3))
        g.stop()
        got[name] = res
    s, p = got["stock"], got["patched"]
    rise, apex, air, _ = p["open"]
    check(rise == 42 and apex == 10 and 44 <= air <= 52,
          f"a jump rises {rise} px (stock {s['open'][0]}), stays at the top {apex} frames (stock {s['open'][1]}) "
          f"and lasts {air} frames (stock {s['open'][2]}), as on the Master System (42, 10, about 48)")
    check(p["ledge5"] == 40 and s["ledge5"] == 40 and p["ledge6"] == 0 and s["ledge6"] == 0,
          "both catch the ledge 5 tiles up and neither catches the platform 6 tiles up, "
          "so the patched jump reaches the same ledges as stock")
    check(max(p["takeoff"]) <= 1 and min(s["takeoff"]) >= 2,
          f"a jump leaves the ground {min(p['takeoff'])} or {max(p['takeoff'])} frames after the press, "
          f"by when the game reads it (stock {min(s['takeoff'])} or {max(s['takeoff'])}, Master System 0)")
    check(p["near_top"] == SMS_NEAR_TOP,
          f"frames within 0, 1, 2 and 4 px of the top: {p['near_top']}, as the Master System's {SMS_NEAR_TOP} "
          f"(stock {s['near_top']})")
    fall = sum(p["below_start"]) / (2 * len(p["below_start"])) if p["below_start"] else None
    check(fall == 1.25, f"jumping off a ledge, Bub falls {fall} px a frame once he is below where he started, "
          f"as on the Master System")
    check(abs(p["hold"] - 1.125) < 0.1 and abs(p["release"] - 0.75) < 0.1 and abs(p["against"] - 0.375) < 0.1,
          f"a jump locked to one side moves {p['hold']} holding that way, {p['release']} letting go and "
          f"{p['against']} pushing back (stock {s['hold']}, {s['release']}, {s['against']})")
    check(abs(p["steer"] - 0.31) < 0.1, f"a jump straight up steers at {p['steer']} (stock {s['steer']})")
    check(p["walkoff"][0] > 1.1 and abs(p["walkoff"][1] - 0.5) < 0.1,
          f"walking off a ledge falls {p['walkoff'][0]} and drifts {p['walkoff'][1]} (stock {s['walkoff'][0]}, {s['walkoff'][1]})")
    check(p["walk"] == s["walk"], f"walking is stock speed, {p['walk']}")


def shot_trace(g, facing, item=False):
    """Fire from where Bub stands; the frames the shot moves and where it becomes a bubble, relative to Bub."""
    if item:
        g.m[C["RANGE_ITEM"]] = 1
    bx = g.xy()[0]
    moving, start = 0, None
    for i in range(100):
        if i < 4:
            g.pb.button_press("b")
        g.tick()
        if i < 4:
            g.pb.button_release("b")
        if g.m[C["SHOT"]]:
            moving += 1
        elif moving and g.m[C["BUBBLE_STATE"]]:
            return moving, g.m[C["BUBBLE_X"]] - bx
    return moving, None


def shot(stock, patched):
    print("the shot")
    got = {}
    for name, rom in (("stock", stock), ("patched", patched)):
        r = Round1(rom)
        g = r.g
        g.invincible = False            # it would stop Bub firing
        res = {}
        for item in (False, True):
            g.restore(r.start)
            res[("right", item)] = shot_trace(g, "right", item)
            g.restore(r.start)
            g.hold(["right"], 40)
            g.hold(["left"], 2)
            g.tick(10)
            res[("left", item)] = shot_trace(g, "left", item)
        for gap in range(16, 40, 2):    # the soonest a second press fires a second shot
            g.restore(r.start)
            for i in range(gap + 40):
                on = i < 4 or gap <= i < gap + 4
                if on:
                    g.pb.button_press("b")
                g.tick()
                if on:
                    g.pb.button_release("b")
            if sum(1 for j in range(14) if g.m[C["BUBBLE_STATE"] + 2 * j]) >= 2:
                res["rate"] = gap
                break
        g.stop()
        got[name] = res
    s, p = got["stock"], got["patched"]
    for item in (False, True):
        what = "with the longer-range item" if item else "normally"
        same = all(p[(d, item)][1] == s[(d, item)][1] for d in ("right", "left"))
        half = all(abs(p[(d, item)][0] * 2 - s[(d, item)][0]) <= 2 for d in ("right", "left") if s[(d, item)][1] is not None)
        check(same and half, f"{what}, the shot ends {p[('right', item)][1]} px right and {-p[('left', item)][1]} px left "
              f"of Bub, as stock, after {p[('right', item)][0]} frames against stock's {s[('right', item)][0]}")
    check(p.get("rate") == 2 * C["COOL_TICKS"] == 22 and s.get("rate") == 28,
          f"a second shot fires {p.get('rate')} frames after the first at the soonest, as on the Master System "
          f"(stock {s.get('rate')})")


def captures(rom):
    total = 0
    for seed in range(1, 7):
        g = Game(rom)
        g.new_game()
        prev = None

        def rec(g):
            nonlocal prev, total
            st = [g.m[STATE + 4 * k] for k in range(1, 8)]
            if prev:
                total += sum(1 for a, b in zip(prev, st) if b == TRAPPED and a != TRAPPED)
            prev = st
        play(g, seed, 3000, rec)
        g.stop()
    return total


def trapping(stock, patched):
    print("trapping enemies")
    s, p = captures(stock), captures(patched)
    check(p >= s * 0.7 and p > 0, f"seeded play traps {p} enemies in 18000 frames (stock {s})")


def bubble_window(rom):
    """The horizontal offsets at which Bub, falling with jump held, bounces on a bubble held in place."""
    g = Game(rom)
    g.new_game()
    g.hold(["right"], 56)
    g.tick(10)
    for i in range(4):
        g.pb.button_press("b")
        g.tick()
        g.pb.button_release("b")
    g.tick(40)
    bx, by = g.m[C["BUBBLE_X"]], g.m[C["BUBBLE_Y"]]
    base = g.snapshot()
    hits = [0]
    for a in PROFILE["bounce_starts"]:
        g.pb.hook_register(PROFILE["bank"], a, lambda _: hits.__setitem__(0, hits[0] + 1), None)
    g.invincible = True
    got, turn = [], []
    for dx in range(-24, 25):
        g.restore(base)
        hits[0] = 0
        for i in range(90):
            g.m[C["BUBBLE_Y"]] = by
            if i == 34:                 # partway down a jump, over the bubble
                g.m[C["X"]], g.m[C["Y"]] = (bx + dx) & 0xFF, by - 24
            for k in ["a"]:
                g.pb.button_press(k)
            g.tick()
            g.pb.button_release("a")
            if hits[0] and i > 34:
                got.append(dx)
                turn.append(g.m[C["Y"]] < before)   # higher at the end of the tick that touched it
                break
            before = g.m[C["Y"]]
    g.stop()
    return got, turn


def bouncing(stock, patched):
    print("landing on bubbles")
    (s, s_turn), (p, p_turn) = bubble_window(stock), bubble_window(patched)
    check(all(p_turn) and not any(s_turn),
          "a bounce carries Bub upwards on the tick he touches the bubble, where stock sinks for one more")
    check(len(p) == 23 and p == list(range(p[0], p[0] + 23)) and len(s) == 13,
          f"Bub bounces anywhere in a {len(p)} px span over a bubble, as on the Master System (stock {len(s)} px)")


def landings(stock, patched):
    print("landing and bouncing in play")
    for name, rom in (("stock", stock), ("patched", patched)):
        grounded = off = bounces = 0
        for rnd in (5, 10, 20, 30, 40, 50, 60):
            for seed in (1, 2):
                g = Game(rom)
                count = [0]
                for a in PROFILE["bounce_starts"]:
                    g.pb.hook_register(PROFILE["bank"], a, lambda _: count.__setitem__(0, count[0] + 1), None)
                g.new_game(force=(0, rnd - 1))

                def rec(g):
                    nonlocal grounded, off
                    standing = g.m[C["GROUND"]] and not g.m[C["JUMP"]]      # a jump's first tick can end mid-frame
                    if standing and g.m[STATE] == 0 and g.xy() != (255, 255):   # (255, 255): dying
                        grounded += 1
                        off += g.m[C["Y"]] & 7 != 0
                play(g, seed, 1500, rec)
                bounces += count[0]
                g.stop()
        if name == "patched":
            check(off == 0, f"over {grounded} frames standing, in rounds 5 to 60, Bub always stands on the tile grid")
            check(bounces > 0, f"bubble and enemy bounces still start jumps: {bounces} (stock {stock_bounces})")
        stock_bounces = bounces


def dmg_mode(patched):
    print("on an original Game Boy")
    g = Game(patched, cgb=False)
    g.new_game()
    x, y = g.xy()
    r = Round1.__new__(Round1)
    r.g, r.start = g, g.snapshot()
    rise = arc_stats(r.jump([], []), y)[3]
    g.stop()
    check(y == FLOOR_Y and rise == 40, "in DMG mode round 1 starts, and a jump reaches the ledge above")


# ---------------------------------------------------------------- the save

def pw_open(rom, ram=None, wram_garbage=()):
    g = Game(rom, ram, wram_garbage=wram_garbage)
    g.to_password()
    out = g.frames(80) + [str(g.pw_state())]
    g.press("a", 30)                    # types the first letter
    out += g.frames(40) + [str(g.pw_state())]
    g.stop()
    return out


def no_save(stock, patched):
    print("with nothing usable saved")
    ref = pw_open(stock)
    rng = random.Random(9)
    noise = bytes(rng.randrange(256) for _ in range(SRAM_SIZE))
    cases = [("a fresh cartridge", None), ("SRAM full of $FF", b"\xFF" * SRAM_SIZE), ("random SRAM", noise),
             ("a valid signature with a bad checksum", sram_image(0, 19, good=False)),
             ("a bad signature", sram_image(0, 19, sig=(0xB0, 0xB2))),
             ("route 4, past the last", sram_image(3, 0)), ("round 61, past the last", sram_image(0, 60))]
    for what, ram in cases:
        check(pw_open(patched, ram) == ref,
              f"{what}: the PASSWORD screen opens empty, and it and typing on it look the same as stock")
    check(pw_open(patched, wram_garbage=(SC["PF_PENDING"],)) == ref,
          "the same with $FF in the pending flag at power-on, as a console's WRAM can hold")


def clear_round(g, seed, limit=20000):
    """Seeded play, blowing bubbles and moving, with Bub unable to be hit, until the next round loads."""
    rng = random.Random(seed)
    target, held = g.loads + 1, []
    g.invincible = True
    for f in range(limit):
        if f % 6 == 0:
            held = [k for k in (rng.choice(["left", "right", None]), rng.choice(["b", "b", "a", None])) if k]
        for k in held:
            g.pb.button_press(k)
        g.tick()
        for k in held:
            g.pb.button_release(k)
        if g.loads >= target:
            break
    g.invincible = False
    g.until_round(target)


def saving(stock, patched):
    print("saving the round")
    g = Game(patched)
    g.new_game()
    check(g.sram() == bytes.fromhex("b0b10000a5") and g.m[0xA000] == 0xFF,
          f"a new game saves route 1, round 1: {g.sram().hex(' ')}, and the SRAM is left disabled")
    clear_round(g, 1)
    route = g.m[SC["ROUTE"]]
    check(g.m[SC["ROUND"]] == 1 and g.sram() == sram_image(route, 1)[:5],
          f"clearing it saves round 2 of the route it goes on to: {g.sram().hex(' ')}")
    ram = g.stop(save=True)
    check(len(ram) == SRAM_SIZE, "the emulator writes an 8 KB battery file")
    for seed in range(2, 12):           # seeded play that happens to take round 1's door
        g = Game(patched)
        g.new_game()
        clear_round(g, seed)
        route = g.m[SC["ROUTE"]]
        saved = g.sram()
        g.stop()
        if route:
            break
    check(route == 1 and saved == sram_image(1, 1)[:5],
          f"taking round 1's door to the second route saves that route's round 2: {saved.hex(' ')} (seed {seed})")

    # a password typed, a power cycle, and the password back
    g = Game(patched)
    g.to_password()
    g.type_word("GFBC")
    g.press("a", 60)
    g.until_round()
    route, rnd = g.m[SC["ROUTE"]], g.m[SC["ROUND"]]
    ram = g.stop(save=True)
    check(ram[:5] == sram_image(route, rnd)[:5] and rnd == 19,
          f"GFBC typed on the patched game starts round {rnd + 1} and saves it: {ram[:5].hex(' ')}")
    g = Game(patched, ram)
    g.to_password()
    pre_state, pre = g.pw_state(), set(g.frames(128))
    g.press("a", 60)
    g.until_round()
    after = (g.m[SC["ROUTE"]], g.m[SC["ROUND"]])
    g.stop()
    t = Game(stock)
    t.to_password()
    t.type_word("GFBC")
    typed_state, typed = t.pw_state(), set(t.frames(128))
    t.stop()
    check(pre_state == typed_state and pre == typed,
          "after a power cycle GFBC is in the four slots, drawn, with the cursor on END, and the screen "
          "over the cursor's blink matches typing it on the stock game")
    check(after == (route, rnd), f"and A on END starts round {after[1] + 1} again")
    consts = SV["consts"]
    consts["SLOT_VRAM"] -= 1
    try:
        broken = P.patch(open(stock, "rb").read(), verbose=False)
    finally:
        consts["SLOT_VRAM"] += 1
    path = os.path.join(tempfile.mkdtemp(), "control.gbc")
    open(path, "wb").write(broken)
    c = Game(path, ram)
    c.to_password()
    c_state, c_frames = c.pw_state(), set(c.frames(128))
    c.stop()
    check(c_state[:6] == typed_state[:6] and c_frames != typed,
          "control: a build that draws the letters one tile to the left fills the entry the same but looks different")

    # EXIT, then a new game
    g = Game(patched, ram)
    g.to_password()
    for b in ("up", "right", "right"):
        g.press(b, 20)
    g.press("a", 90)
    target = g.loads + 1
    for _ in range(4):
        g.pb.button("start", 4)
        g.tick(90)
        if g.loads >= target:
            break
    g.until_round(target)
    check(g.m[SC["ROUND"]] == 0 and g.sram() == sram_image(0, 0)[:5],
          "EXIT from the pre-filled screen, then START, begins round 1 and saves that")
    g.stop()


def looks_typed(stock, patched):
    print("the pre-filled PASSWORD screen against the known passwords")
    for rnd, word in PASSWORDS.items():
        t = Game(stock)
        t.to_password()
        t.type_word(word)
        typed_state, typed = t.pw_state(), set(t.frames(128))
        t.press("a", 60)
        t.until_round()
        want = (t.m[SC["ROUTE"]], t.m[SC["ROUND"]])
        t.stop()
        g = Game(patched, sram_image(*want))
        g.to_password()
        ok = g.pw_state() == typed_state and set(g.frames(128)) == typed
        g.stop()
        check(ok and want[1] == rnd - 1,
              f"round {rnd}: the pre-filled screen is {word}, and looks as it does typed on the stock game")
    # The letter tiles: A is $90 and the rest of the alphabet follows; the digits are read off the game.
    t = Game(stock)
    t.to_password()
    t.type_word("1345")
    tiles = {chr(ord("A") + i): 0x90 + i for i in range(26)}
    tiles.update(zip("1345", t.pw_state()[:4]))
    t.stop()
    letter = {v: k for k, v in tiles.items()}

    def outcome(g):
        target = g.loads + 1
        g.press("a", 60)
        for _ in range(900):
            if g.loads >= target:
                break
            g.tick()
        return (g.loads >= target, g.m[SC["ROUTE"]], g.m[SC["ROUND"]]) if g.loads >= target else (False,)

    rng = random.Random(3)
    for route, rnd in [(rng.randrange(3), rng.randrange(60)) for _ in range(6)]:
        g = Game(patched, sram_image(route, rnd))
        g.to_password()
        pre_state = g.pw_state()
        word = "".join(letter.get(x, "?") for x in pre_state[:4])
        pre = outcome(g)
        g.stop()
        t = Game(stock)
        t.to_password()
        t.type_word(word)
        typed_state = t.pw_state()
        typed = outcome(t)
        t.stop()
        what = f"starts route {route + 1}, round {rnd + 1}" if pre == (True, route, rnd) else "is turned down, as it is typed"
        check(pre_state == typed_state and pre == typed and (pre == (True, route, rnd) or not pre[0]),
              f"route {route + 1}, round {rnd + 1} saved: {word} is pre-filled as typed, and A on END {what}")


# ---------------------------------------------------------------- routines

class Call:
    """Runs one routine from the frame end on the title screen, as if a caller
    had called it, and reads the registers as it returns."""
    REGS = ("A", "F", "B", "C", "D", "E", "HL", "SP")
    SENTINEL = 0x3FF0                   # zero padding at the end of bank 0; the hook fires before it runs

    def __init__(self, rom):
        self.g = Game(rom)
        self.g.tick(700)
        self.pb, self.m = self.g.pb, self.g.m
        self.pending = None
        self.pb.hook_register(0, FRAME_END, self._enter, None)
        self.pb.hook_register(0, self.SENTINEL, self._leave, None)

    def run(self, addr, regs, bank=None, before=None):
        self.pending = dict(addr=addr, regs=regs, bank=bank, before=before, result=None)
        while self.pending["result"] is None:
            self.pb.tick(1, True)
        res, self.pending = self.pending["result"], None
        return res

    def _map(self, bank):
        self.m[0x2000] = bank
        self.m[0x3000] = 0
        self.m[SC["BANK_NOW"]] = bank

    def _enter(self, _):
        job = self.pending
        if not job or job.get("started"):
            return
        job["started"] = True
        rf = self.pb.register_file
        job["saved"] = {k: getattr(rf, k) for k in self.REGS}
        job["saved"]["PC"] = rf.PC
        job["was_bank"] = self.m[SC["BANK_NOW"]]
        if job["bank"] is not None:
            self._map(job["bank"])
        if job["before"]:
            job["before"](self.m)
        for k, v in job["regs"].items():
            setattr(rf, k, v)
        rf.SP -= 2
        self.m[rf.SP] = self.SENTINEL & 0xFF
        self.m[rf.SP + 1] = self.SENTINEL >> 8
        job["sp_in"] = rf.SP
        rf.PC = job["addr"]

    def _leave(self, _):
        job = self.pending
        if not job or "started" not in job or job["result"] is not None:
            return
        rf = self.pb.register_file
        res = {k: getattr(rf, k) for k in self.REGS}
        res["sp_balanced"] = rf.SP == job["sp_in"] + 2
        res["sram_off"] = self.m[0xA000] == 0xFF
        res["sram"] = list(self.m[0, 0xA000 + i] for i in range(5))
        res["mem"] = {a: self.m[a] for a in (SC["ROUTE"], SC["ROUND"], SC["SLOT"], SC["ROW"], SC["PF_PENDING"])
                      + tuple(SC["BUFFER"] + i for i in range(4))}
        self._map(job["was_bank"])
        for k in self.REGS:
            setattr(rf, k, job["saved"][k])
        rf.PC = job["saved"]["PC"]
        job["result"] = res


def routines(patched):
    print("the save routines on their own")
    _, labels = P.assemble_save(PROFILE)
    call = Call(patched)
    regs = dict(A=0x5A, F=0xB0, B=0x11, C=0x22, D=0x33, E=0x44, HL=0x5566)
    kept = lambda r, keys: r["sp_balanced"] and all(r[k] == regs[k] for k in keys)

    def live(route, rnd):
        def put(m):
            m[SC["ROUTE"]], m[SC["ROUND"]] = route, rnd
        return put

    r = call.run(labels["save_round"], regs, before=live(2, 45))
    check(r["sram"] == list(sram_image(2, 45)[:5]) and r["sram_off"],
          f"save_round writes {bytes(r['sram']).hex(' ')} and leaves the SRAM disabled")
    check(r["A"] == 45 and kept(r, ("B", "C", "D", "E", "HL")),
          "  and returns A = ROUND, as the load it replaces, with B, C, D, E and HL kept")

    def saved(image, route=0, rnd=4):
        def put(m):
            m[0x0000] = 0x0A
            for i, v in enumerate(image[:5]):
                m[0xA000 + i] = v
            m[0x0000] = 0x00
            m[SC["ROUTE"]], m[SC["ROUND"]] = route, rnd
            m[SC["PF_PENDING"]] = 0x55
            for i in range(4):
                m[SC["BUFFER"] + i] = 0xEE
        return put

    z = dict(regs, A=0)
    r = call.run(labels["pf_init"], z, bank=0x3C, before=saved(sram_image(1, 19)))
    mm = r["mem"]
    check(mm[SC["SLOT"]] == 3 and mm[SC["ROW"]] == SC["ROW_END"] and mm[SC["PF_PENDING"]] == 1
          and all(mm[SC["BUFFER"] + i] != 0xEE for i in range(4)) and r["sram_off"],
          "pf_init with a good save: the encoder fills the four letters, the cursor on END, pending set, SRAM disabled")
    check((mm[SC["ROUTE"]], mm[SC["ROUND"]]) == (0, 4) and r["sp_balanced"]
          and all(r[k] == z[k] for k in ("B", "C", "D", "E", "HL")),
          "  and it puts the live round back, with B, C, D, E and HL kept")
    r = call.run(labels["pf_init"], z, bank=0x3C, before=saved(sram_image(1, 19, good=False)))
    mm = r["mem"]
    check(mm[SC["PF_PENDING"]] == 0 and mm[SC["SLOT"]] == 0 and all(mm[SC["BUFFER"] + i] == 0xEE for i in range(4))
          and r["sram_off"], "pf_init with a bad checksum: SLOT = 0 as stock, pending cleared, the letters left alone")

    def pending(flag):
        def put(m):
            m[SC["PF_PENDING"]] = flag
            m[SC["SLOT"]] = 3
        return put

    r = call.run(labels["pf_step"], regs, bank=0x3C, before=pending(0))
    check(r["A"] == 3 and kept(r, ("B", "C", "D", "E", "HL")) and r["mem"][SC["PF_PENDING"]] == 0,
          "pf_step with nothing pending returns A = SLOT with B, C, D, E and HL kept")
    r = call.run(labels["pf_step"], regs, bank=0x3C, before=pending(1))
    check(r["A"] == 3 and kept(r, ("B", "C", "D", "E", "HL")) and r["mem"][SC["PF_PENDING"]] == 0,
          "pf_step pending: clears pending, returns A = SLOT with B, C, D, E and HL kept "
          "(the screen checks below cover the drawing)")
    call.g.stop()


def main():
    stock, patched = sys.argv[1], sys.argv[2]
    print(f"stock   {hashlib.md5(open(stock, 'rb').read()).hexdigest()}")
    print(f"patched {hashlib.md5(open(patched, 'rb').read()).hexdigest()}\n")
    tmp = tempfile.mkdtemp()
    footprint(stock, patched)
    filler_unused(stock, tmp)
    physics(stock, patched)
    shot(stock, patched)
    bouncing(stock, patched)
    trapping(stock, patched)
    landings(stock, patched)
    dmg_mode(patched)
    routines(patched)
    no_save(stock, patched)
    saving(stock, patched)
    looks_typed(stock, patched)
    print()
    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
