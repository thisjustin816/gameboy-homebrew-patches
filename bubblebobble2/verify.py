#!/usr/bin/env python3
"""Check the Bubble Bobble Part 2 patch in emulation.

usage: verify.py STOCK.gb PATCHED.gb

PATCHED is the patched ROM: the tearing fix and the save of the last stage.

Runs start from a cold boot and tap through the intro into the first level,
then play with seeded random input. The comparisons that need the two ROMs in
step start from one saved emulator state, so they begin identical.
"""
import hashlib
import os
import random
import shutil
import sys
import tempfile

from pyboy import PyBoy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch as P

PROFILE = next(iter(P.ROM_PROFILES.values()))
C = PROFILE["consts"]
SV = PROFILE["save"]
SC = SV["consts"]
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


def apply_ips(original, ips):
    """A plain IPS applier (data and RLE records, growing the file), independent of make_ips."""
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
    pieces, _ = P.assemble_save(PROFILE, PROFILE["org_body"] + len(code))
    for org, blob in pieces:
        at = org if org < 0x4000 else SV["bank"] * 0x4000 + org - 0x4000
        allowed |= set(range(at, at + len(blob)))
    base = SV["bank"] * 0x4000
    allowed |= set(range(base, base + SV["encoder"][1]))
    for key in ("stage_load", "pw_init", "pw_step"):
        allowed |= {SV[key][0] + k for k in range(3)}
    allowed |= set(SV["header"]) | {0x14D}
    header_ok = all(p[a] == now for a, (_, now) in SV["header"].items())
    untouched = s[0x100:0x147] == p[0x100:0x147] and s[0x14A:0x14D] == p[0x14A:0x14D]
    sum_ok = P.header_checksum(p) == p[0x14D]
    check(len(p) == SV["rom_size"] and header_ok and untouched and sum_ok,
          "256 KB, MBC1+RAM+BATTERY with 8 KB of RAM in the header, and the rest of the header intact")
    check(all(b == 0xFF for i, b in enumerate(p[len(s):], len(s)) if i not in allowed),
          "the new banks are $FF apart from the patch's own code")
    changed = [i for i in range(len(s)) if s[i] != p[i]]
    stray = [hex(i) for i in changed if i not in allowed]
    check(not stray, f"{len(changed)} stock bytes differ, all at the patch's own sites (stray: {stray[:5]})")


def filler_unused(stock):
    print("the filler the code goes over")
    state = level_one_state(stock)
    raw = bytearray(open(stock, "rb").read())
    tmp = tempfile.mkdtemp()
    poisoned = os.path.join(tmp, "poisoned.gb")
    for start, end, _ in PROFILE["filler"] + SV["filler"]:
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

    def run(self, addr, regs, before=None, lcd_on=True, after=None):
        self.pending = dict(addr=addr, regs=regs, before=before, lcd_on=lcd_on, after=after, result=None)
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
        if job["after"]:
            res["extra"] = job["after"](pb)
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


def encode_password(world, stage, extra):
    """The four symbols for a world, stage and extra bits, worked out by hand
    from the game's encoder (bank 6 $7EDC). The tests compare it with the
    game's own routine, and with what the patch saves."""
    last = (0x25 - stage) & 0xFF
    second = (stage + (last >> 2)) & 0xFF
    third = (world << 3) & 0xFF
    if extra & 0x30:
        third |= (extra & 0x30) >> 4
    first = ((stage >> 3) + world) << 2 & 0xFF
    if extra & 0xC0:
        first |= (extra & 0xC0) >> 6
    return [first, third, second, last]


def tile_of(symbol):
    """The tile the game draws for a symbol number."""
    return symbol + 0x20 if symbol < 0x1B else symbol - 0x0B


def sram_image(symbols, good=True):
    """8 KB of SRAM holding a saved password, laid out as the patch writes it."""
    img = bytearray(0x2000)
    img[0:2] = bytes([SC["SIG_1"], SC["SIG_2"]])
    img[2:6] = bytes(symbols)
    img[6] = ((sum(symbols) & 0xFF) ^ SC["SUM_XOR"]) ^ (0 if good else 1)
    return bytes(img)


def rom_copy(rom, ram=None):
    """A private copy of the ROM, with a battery file if there is one to start from."""
    path = os.path.join(tempfile.mkdtemp(), "game.gb")
    shutil.copy(rom, path)
    if ram is not None:
        open(path + ".ram", "wb").write(ram)
    return path


class Title:
    """The title screens, driven by the game's own state pointer."""

    def __init__(self, path, hram_garbage=()):
        self.path = path
        self.pb = PyBoy(path, window="null", sound_emulated=False)
        self.loads = 0
        self.pb.hook_register(0, 0x09D7, lambda _: setattr(self, "loads", self.loads + 1), None)
        if hram_garbage:
            def garbage(_):
                for a in hram_garbage:
                    self.pb.memory[HRAM(a)] = 0xFF
            self.pb.hook_register(0, 0x0100, garbage, None)

    def state(self):
        m = self.pb.memory
        return m[0xC103] | m[0xC104] << 8

    def tick(self, n=1):
        self.pb.tick(n, True)

    def press(self, button, after=20):
        self.pb.button(button, 5)
        self.tick(5 + after)

    def to_title(self):
        while not (self.state() == 0x387F and self.pb.frame_count > 250):
            self.tick()
        self.tick(30)

    def open_password(self):
        self.to_title()
        self.press("start", after=40)
        self.press("down", after=30)
        self.press("start", after=100)
        assert self.state() == 0x2E67

    def new_game(self):
        self.to_title()
        self.press("start", after=40)
        self.press("start", after=40)
        self.until_stage()

    def accept_password_and_start(self):
        """START on the PASSWORD screen accepts it and returns to the title, which reads
        START ROUND n; START again begins that round."""
        self.press("start", after=200)
        self.press("start", after=1)
        self.until_stage()

    def until_stage(self, limit=6000):
        target = self.loads + 1
        for _ in range(limit):
            if self.loads >= target:
                break
            self.tick()
        self.tick(5)

    def buffer(self):
        return list(self.pb.memory[0xCE6C:0xCE70])

    def slots(self):
        return [self.pb.memory[0x9886 + 2 * i] for i in range(4)]

    def sram(self, n=7):
        return bytes(self.pb.memory[0, 0xA000 + i] for i in range(n))

    def type_symbols(self, numbers):
        """Type symbols by number into the PASSWORD screen, from its opening cursor."""
        for e in numbers:
            r, c = (e - 1) // 9, (e - 1) % 9
            for _ in range(r):
                self.press("down", after=12)
            for _ in range(c):
                self.press("right", after=12)
            self.press("a", after=25)
            for _ in range(r):
                self.press("up", after=12)
            for _ in range(c):
                self.press("left", after=12)

    def frames(self, n=80):
        out = []
        for _ in range(n):
            self.tick()
            out.append(hashlib.md5(self.pb.screen.image.convert("RGB").tobytes()).hexdigest()[:8])
        return out


def saving(stock, patched):
    print("saving the last stage")
    ZERO = [0, 0, 0, 0]

    # The PASSWORD screen with nothing usable saved is the stock screen.
    ref = Title(rom_copy(stock))
    ref.open_password()
    ref_frames = set(ref.frames())
    rng = random.Random(9)
    noise = bytes(rng.randrange(256) for _ in range(0x2000))
    cases = [("a fresh cartridge", None), ("SRAM full of $FF", b"\xFF" * 0x2000),
             ("random SRAM", noise), ("a valid signature with a bad checksum", sram_image([4, 8, 10, 36], good=False))]
    for what, ram in cases:
        t = Title(rom_copy(patched, ram), hram_garbage=(SC["PF_LEFT"],))
        t.open_password()
        ok = t.buffer() == ZERO and t.pb.memory[HRAM(SC["PF_LEFT"])] == 0
        check(ok and set(t.frames()) == ref_frames,
              f"{what}: the PASSWORD screen opens empty and looks the same as stock's")

    # Starting a game saves the stage's password.
    path = rom_copy(patched)
    t = Title(path)
    t.new_game()
    m = t.pb.memory
    want = sram_image(encode_password(m[0xC10A], m[0xC10B], m[0xCE5D]))[:7]
    check((m[0xC10A], m[0xC10B]) == (1, 1) and t.sram() == want,
          f"a new game saves stage 1's password: {t.sram().hex(' ')}")
    check(m[0xA000] == 0xFF, "the game leaves the SRAM disabled afterwards")
    t.pb.stop(save=True)
    check(os.path.getsize(path + ".ram") == 0x2000, "the emulator wrote an 8 KB battery file")

    # A power cycle brings it back on the PASSWORD screen, as if typed.
    t = Title(path)
    t.open_password()
    saved = list(want[2:6])
    check(t.buffer() == saved and t.slots() == [tile_of(x) for x in saved],
          f"after a power cycle the PASSWORD screen has {saved} in its buffer and tiles {[hex(x) for x in t.slots()]} drawn")
    prefilled = set(t.frames())
    typed = Title(rom_copy(stock))
    typed.open_password()
    typed.type_symbols(saved)
    check(typed.buffer() == t.buffer() and typed.slots() == t.slots() and set(typed.frames()) == prefilled,
          "and it looks exactly like typing those symbols on the stock game, cursor blink included")

    # Control: the same comparison catches a build that draws the symbols at the wrong address.
    md5 = hashlib.md5(open(stock, "rb").read()).hexdigest()
    good_low = P.ROM_PROFILES[md5]["save"]["consts"]["SLOT_LOW"]
    P.ROM_PROFILES[md5]["save"]["consts"]["SLOT_LOW"] = good_low - 6
    try:
        broken = P.patch(open(stock, "rb").read(), verbose=False)
    finally:
        P.ROM_PROFILES[md5]["save"]["consts"]["SLOT_LOW"] = good_low
    bad_path = os.path.join(tempfile.mkdtemp(), "broken.gb")
    open(bad_path, "wb").write(broken)
    open(bad_path + ".ram", "wb").write(sram_image(saved))
    b = Title(bad_path)
    b.open_password()
    check(b.buffer() == saved and b.slots() != typed.slots(),
          "control: a build that draws slot 0 at $9880 fills the buffer but puts the symbols in the wrong place")

    # Any slot can still be retyped.
    t.press("a", after=25)
    check(t.buffer() == saved[:3] + [1] and t.slots()[3] == tile_of(1) and t.slots()[:3] == [tile_of(x) for x in saved[:3]],
          "pressing A retypes the last slot and leaves the others")

    # A later stage, entered through the game's own password check, is what gets remembered.
    path = rom_copy(patched)
    t = Title(path)
    t.open_password()
    for i, v in enumerate(encode_password(2, 19, 0x20)):
        t.pb.memory[0xCE6C + i] = v
    t.accept_password_and_start()
    m = t.pb.memory
    check(m[0xC10D] == 39, f"typing world 2, stage 19's password starts stage {m[0xC10D]} (the test gave 39)")
    want = sram_image(encode_password(m[0xC10A], m[0xC10B], m[0xCE5D]))[:7]
    check(t.sram() == want, f"stage 39's password is saved: {t.sram().hex(' ')}")
    t.pb.stop(save=True)
    t = Title(path)
    t.open_password()
    check(t.buffer() == list(want[2:6]), "after a power cycle it is offered on the PASSWORD screen")
    t.accept_password_and_start()
    check(t.pb.memory[0xC10D] == 39, "and START on that screen continues from stage 39")

    # The copied encoder is the game's.
    state = level_one_state(stock)
    call = Call(patched, state)
    rng = random.Random(4)
    same = []
    for _ in range(40):
        world, stage = rng.randint(1, 6), rng.randint(1, 20)
        extra = rng.choice([0x00, 0x10, 0x20, 0x30, 0x40, 0x80, 0xC0, 0x50, 0xB0])

        def inputs(pb, world=world, stage=stage, extra=extra):
            pb.memory[0xC10A], pb.memory[0xC10B], pb.memory[0xCE5D] = world, stage, extra

        def out(pb):
            return list(pb.memory[0xCE6C:0xCE70])

        def in_bank(bank):
            def before(pb):
                inputs(pb)
                pb.memory[0x2100] = bank

            def after(pb):
                pb.memory[0x2100] = pb.memory[SC["BANK_NOW"]]
                return out(pb)
            return before, after
        b6, a6 = in_bank(6)
        b8, a8 = in_bank(SV["bank"])
        game = call.run(0x7EDC, {}, before=b6, after=a6)["extra"]
        copy = call.run(0x4000, {}, before=b8, after=a8)["extra"]
        same.append(game == copy == encode_password(world, stage, extra))
    check(all(same), f"the copied encoder, the game's own and the hand-worked one agree on {len(same)} stages")

    # The new routines keep the caller's registers and flags; far8 keeps the bank.
    _, labels = P.assemble_save(PROFILE, PROFILE["org_body"] + len(P.assemble_code(PROFILE)[0]))
    regs = dict(A=0x5A, F=0xB0, B=0x11, C=0x22, D=0x33, E=0x44, HL=0x5566)

    def snapshot(pb):
        return dict(buffer=list(pb.memory[0xCE6C:0xCE70]), flags=pb.memory[0xC102],
                    queue=list(pb.memory[0xC111:0xC115]), left=pb.memory[HRAM(SC["PF_LEFT"])],
                    cursor=pb.memory[0xC211], sram=bytes(pb.memory[0, 0xA000 + i] for i in range(7)),
                    cpu_sram=pb.memory[0xA000], bank=pb.memory[SC["BANK_NOW"]],
                    mapped=bytes(pb.memory[0x4000:0x4008]))

    def routine(name, before=None):
        """Run one bank 8 routine directly, with bank 8 mapped as far8 would have it."""
        def start(pb):
            pb.memory[0x2100] = SV["bank"]
            if before:
                before(pb)

        def after(pb):
            got = snapshot(pb)
            pb.memory[0x2100] = pb.memory[SC["BANK_NOW"]]
            return got
        r = call.run(labels[name], regs, before=start, after=after)
        kept = r["sp_balanced"] and all(r[k] == regs[k] for k in regs)
        return kept, r["extra"]

    good = sram_image([4, 8, 10, 36])

    def seed_sram(image):
        def before(pb):
            for i, v in enumerate(image[:8]):
                pb.memory[0, 0xA000 + i] = v
            pb.memory[0xC102] = 0
            for i in range(4):
                pb.memory[0xCE6C + i] = 0
        return before
    kept, x = routine("pf_begin", seed_sram(good))
    check(kept and x["buffer"] == [4, 8, 10, 36] and x["left"] == 4 and x["cursor"] == SC["CURSOR_END"] and x["cpu_sram"] == 0xFF,
          "pf_begin with a saved password fills the buffer and cursor, and leaves the SRAM disabled; registers and flags kept")
    kept, x = routine("pf_begin", seed_sram(sram_image([4, 8, 10, 36], good=False)))
    check(kept and x["buffer"] == [0, 0, 0, 0] and x["left"] == 0,
          "pf_begin with a bad checksum leaves the buffer empty and draws nothing")

    def step_from(left, busy=0):
        def before(pb):
            for i, v in enumerate([4, 8, 10, 36]):
                pb.memory[0xCE6C + i] = v
            pb.memory[HRAM(SC["PF_LEFT"])] = left
            pb.memory[0xC102] = busy
            pb.memory[0xC111:0xC115] = [0, 0, 0, 0]
        return before
    kept, x = routine("pf_step", step_from(4))
    check(kept and x["queue"] == [SC["SLOT_HIGH"], SC["SLOT_LOW"], 0, tile_of(4)] and x["flags"] == 2 and x["left"] == 3,
          "pf_step draws slot 0 through the game's tile queue: address $9886, tile for symbol 4")
    kept, x = routine("pf_step", step_from(1))
    check(kept and x["queue"] == [SC["SLOT_HIGH"], SC["SLOT_LOW"] + 6, 0, tile_of(36)] and x["left"] == 0,
          "pf_step draws slot 3 last: address $988C, tile for symbol 36")
    kept, x = routine("pf_step", step_from(3, busy=2))
    check(kept and x["left"] == 3 and x["flags"] == 2 and x["queue"] == [0, 0, 0, 0],
          "pf_step waits while the game's tile queue is busy")
    kept, x = routine("pf_step", step_from(0))
    check(kept and x["flags"] == 0 and x["queue"] == [0, 0, 0, 0], "pf_step with nothing to draw does nothing")

    def stage_ready(pb):
        pb.memory[0xC10A], pb.memory[0xC10B], pb.memory[0xCE5D] = 3, 7, 0x10
    kept, x = routine("save_stage", stage_ready)
    want = sram_image(encode_password(3, 7, 0x10))[:7]
    check(kept and x["sram"] == want and x["cpu_sram"] == 0xFF,
          f"save_stage writes the world 3, stage 7 password ({x['sram'].hex(' ')}) and disables the SRAM")

    # far8 puts the bank back, and t_save leaves A as the instruction it replaced did.
    for name, target in (("far8", labels["pf_step"]), ("t_save", None)):
        was = {}

        def start(pb):
            was.update(snapshot(pb))
            pb.memory[0xC10A] = 3
            pb.memory[0xC10B], pb.memory[0xCE5D] = 7, 0x10
            pb.memory[HRAM(SC["PF_LEFT"])] = 0
        addr = SV["far8_org"] if name == "far8" else SV["t_save_org"]
        r = call.run(addr, dict(regs, HL=target or 0), before=start, after=snapshot)
        x = r["extra"]
        if name == "far8":
            check(r["sp_balanced"] and x["bank"] == was["bank"] and x["mapped"] == was["mapped"],
                  "far8 runs the routine and puts CE73 and the mapped bank back")
        else:
            check(r["sp_balanced"] and r["A"] == 3 and x["bank"] == was["bank"] and x["mapped"] == was["mapped"]
                  and x["sram"] == sram_image(encode_password(3, 7, 0x10))[:7],
                  "the stage-load trampoline saves the stage, leaves A = the world as the replaced instruction did, and keeps the bank")


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
    saving(stock, patched)
    print()
    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
