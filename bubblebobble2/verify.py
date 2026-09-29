#!/usr/bin/env python3
"""Check the Bubble Bobble Part 2 tearing fix in emulation.

usage: verify.py STOCK.gb PATCHED.gb

Runs start from a cold boot and tap through the intro into the first level,
then play with seeded random input. The comparisons that need the two ROMs in
step start from one saved emulator state, so they begin identical.
"""
import hashlib
import os
import random
import sys
import tempfile

from pyboy import PyBoy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch as P

PROFILE = next(iter(P.ROM_PROFILES.values()))
C = PROFILE["consts"]
HRAM = lambda a: 0xFF00 + a
FLAGS, PEND_Y, PEND_X = HRAM(C["FLAGS"]), HRAM(C["PEND_Y"]), HRAM(C["PEND_X"])
SCX, SCY, LCDC, LY = 0xFF43, 0xFF42, 0xFF40, 0xFF44
KEYS = ["left", "right", "up", "down", "a", "b"]
MAIN_LOOP_WAIT = 0x0215                 # the main loop's wait for the VBlank flag
VBLANK_ENTRY = 0x0220
VBLANK_EXIT = 0x0279                    # the handler's pops, after its scroll and DMA work
LATE_SITES = {0x2BB6, 0x2BB8}           # one-time SCX/SCY resets the patch leaves alone
failures = []


def check(ok, what):
    print(f"   {'ok  ' if ok else 'FAIL'} {what}")
    if not ok:
        failures.append(what)


def boot(rom):
    pb = PyBoy(rom, window="null", sound_emulated=False)
    pb.tick(300, True)
    for _ in range(12):
        pb.button("start", 4)
        pb.tick(60, True)
    for _ in range(20):
        pb.button("a", 4)
        pb.tick(60, True)
    return pb


def level_one_state(stock):
    path = os.path.join(tempfile.mkdtemp(), "level1.state")
    pb = boot(stock)
    with open(path, "wb") as f:
        pb.save_state(f)
    pb.stop(save=False)
    return path


def scroll_writes(rom_bytes):
    """ROM offsets of every ldh ($FF42), a and ldh ($FF43), a."""
    return [i for i in range(len(rom_bytes) - 1)
            if rom_bytes[i] == 0xE0 and rom_bytes[i + 1] in (0x42, 0x43)]


def play(rom, seed, frames, state=None, on_vblank=None, watch_writes=False):
    """Seeded random play. Returns per-frame screen hashes and the frames and
    sites of scroll changes that landed on a visible line."""
    pb = PyBoy(rom, window="null", sound_emulated=False) if state else boot(rom)
    if state:
        with open(state, "rb") as f:
            pb.load_state(f)
    rom_bytes = open(rom, "rb").read()
    frame = [0]
    tears = []                          # (frame, offset, line)
    if watch_writes:
        def watch(off, reg):
            def hit(_):
                if pb.memory[LY] < 144 and pb.memory[LCDC] & 0x80 \
                        and pb.register_file.A != pb.memory[reg]:
                    tears.append((frame[0], off, pb.memory[LY]))
            return hit
        for off in scroll_writes(rom_bytes):
            bank = off // 0x4000
            addr = off if bank == 0 else 0x4000 + off % 0x4000
            pb.hook_register(bank, addr, watch(off, 0xFF00 + rom_bytes[off + 1]), None)
    if on_vblank:
        pb.hook_register(0, VBLANK_ENTRY, lambda _: on_vblank(pb), None)
    rng = random.Random(seed)
    screens = []
    for f in range(frames):
        frame[0] = f
        if f % 15 == 0:
            held = rng.choice(KEYS)
        pb.button(held, 2)
        if f % 50 == 0:
            pb.button("a", 3)
        pb.tick(1, True)
        screens.append(hashlib.md5(pb.screen.image.convert("RGB").tobytes()).hexdigest()[:8])
    return screens, tears, pb


def footprint(stock, patched):
    print("footprint")
    s, p = open(stock, "rb").read(), open(patched, "rb").read()
    check(hashlib.md5(s).hexdigest() in P.ROM_PROFILES, "the stock ROM is the release the patch is made for")
    check(P.patch(s, verbose=False) == p, "the patched ROM is exactly what patch.py builds from the stock one")
    check(len(s) == len(p) and s[0x100:0x14E] == p[0x100:0x14E],
          "same size, and the header (through its checksum) is untouched")
    changed = [i for i in range(len(s)) if s[i] != p[i]]
    code, labels = P.assemble_code(PROFILE)
    allowed = set(range(PROFILE["org_body"], PROFILE["org_body"] + len(code)))
    for vec in (PROFILE["rst_y"], PROFILE["rst_x"]):
        allowed |= set(range(vec, vec + 5))
    allowed |= {PROFILE["scroll_copy"][0] + k for k in range(3)}
    allowed |= {PROFILE["vblank_dma_call"][0] + k for k in range(3)}
    allowed |= {PROFILE["boot_call"][0] + k for k in range(3)}
    for off, *_ in PROFILE["direct_writes"]:
        allowed |= {off, off + 1}
    allowed |= {0x14E, 0x14F}
    stray = [hex(i) for i in changed if i not in allowed]
    check(not stray, f"{len(changed)} bytes differ, all at the patch's own sites (stray: {stray[:5]})")


def filler_unused(stock):
    print("the filler the code goes over")
    state = level_one_state(stock)
    raw = bytearray(open(stock, "rb").read())
    tmp = tempfile.mkdtemp()
    poisoned = os.path.join(tmp, "poisoned.gb")
    for start, end, _ in PROFILE["filler"]:
        raw[start:end] = b"\xFF" * (end - start)
    open(poisoned, "wb").write(raw)
    broken = bytearray(open(stock, "rb").read())
    broken[0x40:0x43] = b"\xFF" * 3          # the VBlank vector, which the game does use
    control = os.path.join(tmp, "broken.gb")
    open(control, "wb").write(broken)
    n = 1500
    ref, _, _ = play(stock, 1, n, state)
    got, _, _ = play(poisoned, 1, n, state)
    bad, _, _ = play(control, 1, n, state)
    check(ref == got, f"filling it with $FF changes nothing over {n} frames of play")
    check(ref != bad, "control: filling the VBlank vector with $FF does change the frames")


def tearing(stock, patched):
    print("tearing")
    state = level_one_state(stock)
    for seed in (1, 2, 3):
        _, s_t, _ = play(stock, seed, 3000, state, watch_writes=True)
        _, p_t, _ = play(patched, seed, 3000, state, watch_writes=True)
        late = [t for t in p_t if t[1] in LATE_SITES]
        check(len(s_t) > 20,
              f"seed {seed}: stock changes the scroll on a visible line {len(s_t)} times "
              f"(lines {min(t[2] for t in s_t)}-{max(t[2] for t in s_t)})")
        check(len(p_t) == len(late),
              f"seed {seed}: patched does it {len(p_t)} times, all from the one-time resets it leaves alone")


def transitions(stock, patched):
    print("the scrolling transitions")
    state = level_one_state(stock)
    # (state routine, SCY, SCX): the game's own states for scrolling to a room's
    # start position, forced by setting its state pointer at level 1's start
    scenarios = [(0x0B24, 0x70, 0x20), (0x0B5A, 0x40, 0x00), (0x0B5A, 0x00, 0x20), (0x0B7C, 0x30, 0x20),
                 (0x0BC4, 0x60, 0x20), (0x15D0, 0x30, 0x20), (0x15D0, 0x00, 0x00)]

    def run(rom, routine, scy, scx):
        pb = PyBoy(rom, window="null", sound_emulated=False)
        with open(state, "rb") as f:
            pb.load_state(f)
        rom_bytes = open(rom, "rb").read()
        torn = []
        for off in scroll_writes(rom_bytes):
            if off // 0x4000:
                continue                # the camera routine's writes are covered by the play checks
            reg = 0xFF00 + rom_bytes[off + 1]
            pb.hook_register(0, off, lambda _, reg=reg: torn.append(1) if pb.memory[LY] < 144
                             and pb.register_file.A != pb.memory[reg] else None, None)
        seen = []

        def at_vblank(_):
            m = pb.memory
            flags = m[FLAGS]
            seen.append((m[0xC103] | m[0xC104] << 8,
                         m[PEND_X] if flags & 2 else m[SCX], m[PEND_Y] if flags & 1 else m[SCY]))
        pb.hook_register(0, VBLANK_ENTRY, at_vblank, None)
        pb.tick(2, True)
        m = pb.memory
        m[0xC103], m[0xC104] = routine & 0xFF, routine >> 8
        m[SCY], m[SCX], m[C["SHADOW_Y"]], m[C["SHADOW_X"]] = scy, scx, scy, scx
        seen.clear()
        pb.tick(100, True)
        pb.stop(save=False)
        return seen, len(torn)

    for routine, scy, scx in scenarios:
        s_seen, s_torn = run(stock, routine, scy, scx)
        p_seen, p_torn = run(patched, routine, scy, scx)
        moved = len({(x, y) for _, x, y in s_seen})
        check(s_seen == p_seen and moved > 2 and s_torn > 0 and p_torn == 0,
              f"state ${routine:04X} from SCY {scy:#04x} SCX {scx:#04x}: same states and scroll every frame "
              f"as stock ({moved} scroll positions); stock tears {s_torn} times, patched {p_torn}")


def no_stale_overwrite(stock, patched):
    print("direct writes the patch leaves alone")
    state = level_one_state(stock)
    code, _ = P.assemble_code(PROFILE)
    rom_bytes = open(patched, "rb").read()
    org = PROFILE["org_body"]
    direct = [(off, rom_bytes[off + 1]) for off in scroll_writes(rom_bytes)
              if not org <= off < org + len(code)]
    clashes, reached = [], set()
    for seed in range(1, 7):
        pb = PyBoy(patched, window="null", sound_emulated=False)
        with open(state, "rb") as f:
            pb.load_state(f)
        for off, reg in direct:
            bank = off // 0x4000
            addr = off if bank == 0 else 0x4000 + off % 0x4000
            bit = 1 if reg == 0x42 else 2

            def hit(_, off=off, bit=bit):
                reached.add(off)
                if pb.memory[FLAGS] & bit:
                    clashes.append(off)
            pb.hook_register(bank, addr, hit, None)
        rng = random.Random(seed)
        for f in range(3000):
            if f % 15 == 0:
                held = rng.choice(KEYS)
            pb.button(held, 2)
            if f % 50 == 0:
                pb.button("a", 3)
            pb.tick(1, True)
        pb.stop(save=False)
    check(not clashes and reached,
          f"over 18000 frames, {len(reached)} of the unconverted scroll writes ran, and none landed "
          f"while a deferred value was pending (clashes: {sorted(set(clashes))[:5]})")


def power_on(stock, patched):
    print("power-on")
    tmp = tempfile.mkdtemp()
    raw = bytearray(open(patched, "rb").read())
    off, old = PROFILE["boot_call"]
    raw[off:off + 3] = old                   # a patch that leaves HRAM as it finds it
    unguarded = os.path.join(tmp, "unguarded.gb")
    open(unguarded, "wb").write(raw)

    def title_scroll(rom):
        pb = PyBoy(rom, window="null", sound_emulated=False)

        def garbage(_):                      # what a console's HRAM can hold when the game starts
            for a in (C["PEND_Y"], C["PEND_X"], C["FLAGS"]):
                pb.memory[HRAM(a)] = 0xFF
        pb.hook_register(0, 0x0100, garbage, None)
        seen = set()
        # the scroll as the VBlank handler leaves it, which is what the next frame draws with
        pb.hook_register(0, VBLANK_EXIT, lambda _: seen.add((pb.memory[SCX], pb.memory[SCY])), None)
        pb.tick(500, True)
        pb.stop(save=False)
        return seen
    want = title_scroll(stock)
    check(title_scroll(patched) == want == {(0, 0)},
          "with HRAM full of $FF when the game starts, the patched title never leaves scroll 0,0, like stock")
    check(title_scroll(unguarded) != want, "control: without the boot clear, one frame gets scroll 255,255")


def same_game(stock, patched):
    print("everything but the tearing is as stock")
    state = level_one_state(stock)
    raw = bytearray(open(patched, "rb").read())
    off, old = PROFILE["vblank_dma_call"]
    raw[off:off + 3] = old                   # a broken patch: the pending scroll never reaches the hardware
    broken = os.path.join(tempfile.mkdtemp(), "broken.gb")
    open(broken, "wb").write(raw)
    frames, min_match = 1300, 600

    def grab(rom, seed):
        got = []

        def on_vblank(pb):
            got.append((bytes(pb.memory[0xC000:0xCF00]) + bytes(pb.memory[0xD000:0xE000]),
                        bytes(pb.memory[0xFE00:0xFEA0])))
        screens, tears, _ = play(rom, seed, frames, state, on_vblank, watch_writes=True)
        return got, screens, {t[0] for t in tears}

    for seed in (1, 2, 4, 6):
        a, sa, torn = grab(stock, seed)
        b, sb, _ = grab(patched, seed)
        match = next((i for i in range(min(len(a), len(b))) if a[i] != b[i]), min(len(a), len(b)))
        check(match >= min_match,
              f"seed {seed}: the game's memory and sprites match stock at each of the first {match} VBlanks")
        near_tear = lambda i: bool({i - 1, i, i + 1} & torn)
        diff = [i for i in range(match) if sa[i] != sb[i]]
        strays = [i for i in diff if not near_tear(i)]
        check(not strays and any(f < match for f in torn),
              f"seed {seed}: over those frames, {len(diff)} pictures differ, each on or beside one of "
              f"stock's {len([f for f in torn if f < match])} torn frames (stray: {strays[:5]})")
    _, sbad, _ = grab(broken, 2)
    _, sa, torn = grab(stock, 2)
    strays = [i for i in range(min_match) if sa[i] != sbad[i] and not ({i - 1, i, i + 1} & torn)]
    check(strays,
          f"control: a patch that never applies the scroll differs from stock on {len(strays)} frames that aren't torn")


class Call:
    """Runs one routine from the main loop's wait, as if a caller had called it,
    and reads the registers as it returns."""
    REGS = ("A", "F", "B", "C", "D", "E", "HL", "SP")
    SENTINEL = 0x00F0                   # unused filler; the hook fires before it runs

    def __init__(self, rom, state):
        self.pb = PyBoy(rom, window="null", sound_emulated=False)
        with open(state, "rb") as f:
            self.pb.load_state(f)
        self.pb.tick(3, True)
        self.pending = None
        self.pb.hook_register(0, MAIN_LOOP_WAIT, self._enter, None)
        self.pb.hook_register(0, self.SENTINEL, self._leave, None)

    def run(self, addr, regs, before=None, lcd_on=True):
        self.pending = dict(addr=addr, regs=regs, before=before, lcd_on=lcd_on, result=None)
        while self.pending["result"] is None:
            self.pb.tick(1, True)
        res = self.pending["result"]
        self.pending = None
        return res

    def _enter(self, _):
        job = self.pending
        if not job or job.get("started"):
            return
        job["started"] = True
        pb, rf = self.pb, self.pb.register_file
        job["saved"] = {k: getattr(rf, k) for k in self.REGS}
        job["saved"]["PC"] = rf.PC
        job["lcdc"] = pb.memory[LCDC]
        if not job["lcd_on"]:
            pb.memory[LCDC] = job["lcdc"] & 0x7F
        if job["before"]:
            job["before"](pb)
        for k, v in job["regs"].items():
            setattr(rf, k, v)
        rf.SP -= 2
        pb.memory[rf.SP] = self.SENTINEL & 0xFF
        pb.memory[rf.SP + 1] = self.SENTINEL >> 8
        job["sp_in"] = rf.SP
        rf.PC = job["addr"]

    def _leave(self, _):
        job = self.pending
        if not job or "started" not in job or job["result"] is not None:
            return
        pb, rf = self.pb, self.pb.register_file
        res = {k: getattr(rf, k) for k in self.REGS}
        res["sp_balanced"] = rf.SP == job["sp_in"] + 2
        res["hw_scx"], res["hw_scy"] = pb.memory[SCX], pb.memory[SCY]
        res["flags"], res["pend_x"], res["pend_y"] = pb.memory[FLAGS], pb.memory[PEND_X], pb.memory[PEND_Y]
        pb.memory[LCDC] = job["lcdc"]
        for k in self.REGS:
            setattr(rf, k, job["saved"][k])
        rf.PC = job["saved"]["PC"]
        job["result"] = res


def routines(stock, patched):
    print("the injected routines")
    state = level_one_state(stock)
    _, labels = P.assemble_code(PROFILE)
    call = Call(patched, state)
    FLAG_PATTERN = 0xB0                 # Z, H and C set: a caller's flags must survive
    regs = dict(A=0x5A, F=FLAG_PATTERN, B=0x11, C=0x22, D=0x33, E=0x44, HL=0x5566)
    same = lambda r, keep: r["sp_balanced"] and all(r[k] == regs[k] for k in keep)
    keep = ("A", "F", "B", "C", "D", "E", "HL")

    def seed_hw(pb, flags=0):
        pb.memory[SCX], pb.memory[SCY], pb.memory[FLAGS] = 0x10, 0x20, flags

    r = call.run(PROFILE["rst_y"], regs, before=seed_hw)
    check(r["pend_y"] == 0x5A and r["flags"] == 0x01 and (r["hw_scx"], r["hw_scy"]) == (0x10, 0x20),
          "RST $08, LCD on: stores SCY and marks it pending; the hardware is untouched")
    check(same(r, keep) and r["sp_balanced"],
          "  and every register and flag comes back as it went in, with the stack balanced")
    r = call.run(PROFILE["rst_x"], regs, before=seed_hw)
    check(r["pend_x"] == 0x5A and r["flags"] == 0x02 and (r["hw_scx"], r["hw_scy"]) == (0x10, 0x20) and same(r, keep),
          "RST $10, LCD on: the same for SCX")
    r = call.run(PROFILE["rst_y"], regs, before=lambda pb: seed_hw(pb, 0x03), lcd_on=False)
    check(r["hw_scy"] == 0x5A and r["hw_scx"] == 0x10 and r["flags"] == 0x02 and same(r, keep),
          "RST $08, LCD off: writes SCY at once and drops any pending SCY")
    r = call.run(PROFILE["rst_x"], regs, before=lambda pb: seed_hw(pb, 0x03), lcd_on=False)
    check(r["hw_scx"] == 0x5A and r["hw_scy"] == 0x20 and r["flags"] == 0x01 and same(r, keep),
          "RST $10, LCD off: the same for SCX")

    def shadows(pb, flags=0):
        seed_hw(pb, flags)
        pb.memory[C["SHADOW_X"]], pb.memory[C["SHADOW_Y"]] = 0x77, 0x88

    r = call.run(labels["scroll_copy"], regs, before=shadows)
    check(r["pend_x"] == 0x77 and r["pend_y"] == 0x88 and r["flags"] == 0x03 and (r["hw_scx"], r["hw_scy"]) == (0x10, 0x20),
          "scroll copy, LCD on: both shadows pending, hardware untouched")
    check(r["A"] == 0x88 and same(r, ("F", "B", "C", "D", "E", "HL")),
          "  it returns A = the SCY shadow, as the original does, with the flags and other registers kept")
    r = call.run(labels["scroll_copy"], regs, before=lambda pb: shadows(pb, 0x03), lcd_on=False)
    check((r["hw_scx"], r["hw_scy"]) == (0x77, 0x88) and r["flags"] == 0 and r["A"] == 0x88
          and same(r, ("F", "B", "C", "D", "E", "HL")),
          "scroll copy, LCD off: writes both at once and clears both pending bits")

    for flags, want in ((0x00, (0x10, 0x20)), (0x01, (0x10, 0xA2)), (0x02, (0xA3, 0x20)), (0x03, (0xA3, 0xA2))):
        def pend(pb, flags=flags):
            seed_hw(pb, flags)
            pb.memory[PEND_X], pb.memory[PEND_Y] = 0xA3, 0xA2
        r = call.run(labels["vblank_scroll"], regs, before=pend)
        check((r["hw_scx"], r["hw_scy"]) == want and r["flags"] == 0,
              f"VBlank copy with pending bits {flags:#04x}: SCX/SCY become {want[0]:#04x}/{want[1]:#04x}, bits cleared")


def hram_untouched(stock):
    print("the HRAM the patch borrows")
    seen = set()

    def look(pb):
        seen.update((a, pb.memory[HRAM(a)]) for a in (C["PEND_Y"], C["PEND_X"], C["FLAGS"]))
    play(stock, 1, 3000, level_one_state(stock), look)
    check(seen == {(C["PEND_Y"], 0), (C["PEND_X"], 0), (C["FLAGS"], 0)},
          "the stock game never writes $FFA2-$FFA4 over 3000 frames of play")


def main():
    stock, patched = sys.argv[1], sys.argv[2]
    print(f"stock   {hashlib.md5(open(stock, 'rb').read()).hexdigest()}")
    print(f"patched {hashlib.md5(open(patched, 'rb').read()).hexdigest()}\n")
    footprint(stock, patched)
    filler_unused(stock)
    hram_untouched(stock)
    routines(stock, patched)
    tearing(stock, patched)
    transitions(stock, patched)
    no_stale_overwrite(stock, patched)
    power_on(stock, patched)
    same_game(stock, patched)
    print()
    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
