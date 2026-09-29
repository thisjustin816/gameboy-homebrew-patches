#!/usr/bin/env python3
"""Check the Bubble Bobble save patch in emulation.

usage: verify.py STOCK.gb PATCHED.gb

Needs `pip install stable-retro pyboy pillow`. The game crashes in PyBoy as
soon as a round starts (stock too), so every run that plays the game uses
Gambatte, through stable-retro. PyBoy runs only the routine checks, from the
title screen, where it can call one routine and read the registers back.

stable-retro allows one emulator per process, so each Gambatte run is its own
process: this script calls itself with --worker. A power cycle is a new
process that starts with the SRAM the last one left.
"""
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch as P

PROFILE = next(iter(P.ROM_PROFILES.values()))
C = PROFILE["consts"]
GRID = ["BCDFGHJK", "LMNPQRST", "VWXZ1345"]
ENEMIES = 0xFFC3                        # enemies left in the round; 0 clears it
VBLANK_VECTOR = 0x0040
SRAM_SIZE = 0x2000
# The PASSWORD screen's state: $C900-$C920, less the frame counter ($C901), the
# key repeat counter ($C910) and SHOWN, the encoder's output, which only the
# patch fills on that screen. Then the hand and the slot marker's sprites.
PW_RAM = [a for a in range(0xC900, 0xC921) if a not in (0xC901, 0xC910) and not 0xC918 <= a < 0xC91C]
SPRITES = list(range(0xC100, 0xC120))
BUB = (slice(124, 144), slice(52, 76))  # Bub, under END: his idle animation keeps its own phase
failures = []


def check(ok, what):
    print(f"   {'ok  ' if ok else 'FAIL'} {what}")
    if not ok:
        failures.append(what)


# ---------------------------------------------------------------- Gambatte side

class Game:
    def __init__(self, rom, sram=None):
        import warnings
        warnings.filterwarnings("ignore")
        import numpy as np
        import stable_retro
        self.np = np
        self.names = stable_retro.get_system_info("GameBoy")["buttons"]
        self.em = stable_retro.RetroEmulator(rom)
        self.gd = stable_retro.data.GameData()
        self.em.configure_data(self.gd)
        if sram is not None:
            for i, v in enumerate(sram):
                self.gd.memory.assign(0xA000 + i, "|u1", v)
        self.frame = 0
        self.watch = None
        self.watched = set()

    def step(self, *buttons, n=1):
        mask = self.np.zeros(len(self.names), dtype=self.np.uint8)
        for b in buttons:
            mask[self.names.index(b)] = 1
        for _ in range(n):
            self.em.set_button_mask(mask, 0)
            self.em.step()
            self.frame += 1
            if self.watch is not None and self.frame > 20:      # after the boot clears WRAM
                self.watched.add(self.peek(self.watch))

    def peek(self, a):
        for base, block in self.gd.memory.blocks.items():
            if base <= a < base + len(block):
                return block[a - base]
        raise KeyError(hex(a))

    def poke(self, a, v):
        self.gd.memory.assign(a, "|u1", v)

    def sram(self):
        return bytes(self.gd.memory.blocks[0xA000])

    def screen(self, mask=False):
        s = self.em.get_screen().copy()
        if mask:
            s[BUB] = 0
        return hashlib.md5(s.tobytes()).hexdigest()[:12]

    def frames(self, n, mask=False):
        out = []
        for _ in range(n):
            self.step()
            out.append(self.screen(mask))
        return out

    def press(self, b, after=12):
        self.step(b, n=4)
        self.step(n=after)

    def to_menu(self):
        for _ in range(11):             # START every 60 frames reaches the menu
            self.step(n=55)
            self.step("START", n=5)
        self.step(n=55)

    def to_password(self):
        self.to_menu()
        self.step("DOWN", n=5)
        self.step(n=30)
        self.step("START", n=5)
        self.step(n=90)

    def type_word(self, word):
        for ch in word:
            r = next(i for i, row in enumerate(GRID) if ch in row)
            c = GRID[r].index(ch)
            for _ in range(r):
                self.press("DOWN")
            for _ in range(c):
                self.press("RIGHT")
            self.press("A", 20)
            for _ in range(r):
                self.press("UP")
            for _ in range(c):
                self.press("LEFT")

    def to_end(self):
        for _ in range(4):
            self.press("DOWN")

    def read(self, addrs):
        return [int(self.peek(a)) for a in addrs]

    def play(self, seed, rounds, per_round=300):
        """Seeded random play, clearing each round after per_round moves."""
        rng = random.Random(seed)
        moves = ["LEFT", "RIGHT", "A", "B", None, None]
        log = []
        for _ in range(rounds):
            for _ in range(per_round):
                b = rng.choice(moves)
                self.step(*([b] if b else []), n=6)
            log.append((int(self.peek(0xC200)), list(self.sram()[:5])))
            self.poke(ENEMIES, 0)
        self.step(n=900)
        log.append((int(self.peek(0xC200)), list(self.sram()[:5])))
        return log


def worker(job):
    g = Game(job["rom"], bytes.fromhex(job["sram"]) if job.get("sram") else None)
    kind, out = job["kind"], {}
    if kind == "open":                  # the PASSWORD screen, then A (types B) and A again
        g.to_password()
        out["frames"] = g.frames(120)
        out["ram"] = g.read(PW_RAM + [0xC918, 0xC919, 0xC91A, 0xC91B, C["PF_PENDING"]])
        g.press("A", 40)
        g.press("A", 40)
        out["frames"] += g.frames(60)
        out["after"] = g.read(PW_RAM)
    elif kind == "new_game":
        g.to_menu()
        g.step("START", n=5)
        out["frames"] = g.frames(1500)
        out["round"] = int(g.peek(0xC200))
    elif kind == "entry":               # a password on the screen, typed or pre-filled
        g.to_password()
        if job.get("word"):
            g.type_word(job["word"])
            g.to_end()
        g.step(n=400)                   # Bub walks to END when typed
        out["buffer"] = g.read(range(C["BUFFER"], C["BUFFER"] + 4))
        out["state"] = g.read(PW_RAM + SPRITES)
        out["frames"] = sorted(set(g.frames(128, mask=True)))
        start = g.em.get_state()
        out["nav"] = []
        for seq in job.get("nav", []):
            g.em.set_state(start)
            for b in seq:
                g.press(b, 40)
            g.step(n=100)
            out["nav"].append(g.read(PW_RAM + SPRITES))
        g.em.set_state(start)
        g.press("A", 150)
        out["accepted"] = g.read([0xC200, 0xC201, 0xC202, 0xC4B5])
        if job.get("start"):
            g.step("START", n=5)
            g.step(n=1500)
            out["started"] = int(g.peek(0xC200))
    elif kind == "play":                # KLL1, then rounds cleared one after another
        g.watch = job.get("watch")
        g.to_password()
        g.type_word("KLL1")
        g.to_end()
        g.press("A", 150)
        g.step("START", n=5)
        g.step(n=900)
        hashes = []
        real = g.step

        def step(*b, n=1):
            for _ in range(n):
                real(*b)
                hashes.append(g.screen())
        g.step = step
        out["log"] = g.play(job["seed"], job["rounds"])
        out["frames"] = hashes
        out["watched"] = sorted(int(v) for v in g.watched)
    out["sram"] = g.sram().hex()
    print(json.dumps(out))


def run(**job):
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--worker", json.dumps(job)],
                       capture_output=True, text=True, timeout=900)
    lines = [l for l in r.stdout.splitlines() if l.startswith("{")]
    if r.returncode or not lines:
        raise SystemExit(f"worker {job['kind']} failed:\n{r.stderr[-2000:]}")
    return json.loads(lines[-1])


def sram_image(rnd, flags, good=True, sig=(0xB0, 0xB1)):
    s = (rnd + flags) & 0xFF ^ C["SUM_XOR"]
    body = bytes([sig[0], sig[1], rnd, flags, s if good else s ^ 1])
    return (body + b"\xFF" * (SRAM_SIZE - len(body))).hex()


def letters(tiles):
    return "".join(str(t) if t < 10 else chr(ord("A") + t - 10) for t in tiles)


# ---------------------------------------------------------------- checks

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
    code0, code3, _ = P.assemble(PROFILE)
    allowed = set(range(PROFILE["save_org"], PROFILE["save_org"] + len(code0)))
    f3 = P.file_offset(PROFILE["pf_bank"], PROFILE["pf_org"])
    allowed |= set(range(f3, f3 + len(code3)))
    for bank, address, _, _ in PROFILE["hooks"]:
        allowed |= set(range(P.file_offset(bank, address), P.file_offset(bank, address) + 3))
    allowed |= set(PROFILE["header"]) | {0x14D, 0x14E, 0x14F}
    header_ok = all(p[a] == now for a, (_, now) in PROFILE["header"].items())
    untouched = s[0x100:0x147] == p[0x100:0x147] and s[0x148] == p[0x148] and s[0x14A:0x14D] == p[0x14A:0x14D]
    check(len(p) == len(s) and header_ok and untouched and P.header_checksum(p) == p[0x14D],
          "same size, MBC1+RAM+BATTERY with 8 KB of RAM in the header, and the rest of the header intact")
    changed = [i for i in range(len(s)) if s[i] != p[i]]
    stray = [hex(i) for i in changed if i not in allowed]
    check(not stray, f"{len(changed)} stock bytes differ, all at the patch's own sites (stray: {stray[:5]})")


def filler_unused(stock, tmp):
    print("the filler the code goes over")
    s = bytearray(open(stock, "rb").read())
    zeroed = bytearray(s)
    for bank, (lo, hi) in ((0, PROFILE["save_padding"]), (PROFILE["pf_bank"], PROFILE["pf_padding"])):
        zeroed[P.file_offset(bank, lo):P.file_offset(bank, hi)] = bytes(hi - lo)
    control = bytearray(s)
    control[VBLANK_VECTOR] = 0xC9       # ret: the VBlank handler never runs
    paths = {}
    for name, data in (("zeroed", zeroed), ("control", control)):
        paths[name] = os.path.join(tmp, name + ".gb")
        open(paths[name], "wb").write(bytes(data))
    ref = run(kind="play", rom=stock, seed=1, rounds=3)["frames"]
    z = run(kind="play", rom=paths["zeroed"], seed=1, rounds=3)["frames"]
    c = run(kind="play", rom=paths["control"], seed=1, rounds=3)["frames"]
    check(z == ref, f"zeroing bank 0 ${PROFILE['save_padding'][0]:04X}-${PROFILE['save_padding'][1] - 1:04X} and "
          f"bank 3 ${PROFILE['pf_padding'][0]:04X}-${PROFILE['pf_padding'][1] - 1:04X} changes none of "
          f"{len(ref)} frames of password entry and play")
    diff = sum(a != b for a, b in zip(ref, c))
    check(diff > len(ref) // 2, f"control: breaking the VBlank vector changes {diff} of them")


def wram_unused(stock):
    print("the WRAM byte the patch borrows")
    seen = set()
    for seed in (1, 2, 3):
        seen |= set(run(kind="play", rom=stock, seed=seed, rounds=4, watch=C["PF_PENDING"])["watched"])
    check(seen == {0}, f"the stock game leaves ${C['PF_PENDING']:04X} at 0 through three runs of play (saw {sorted(seen)})")


def no_save(stock, patched):
    print("with nothing usable saved")
    ref = run(kind="open", rom=stock)
    rng = random.Random(9)
    noise = bytes(rng.randrange(256) for _ in range(SRAM_SIZE)).hex()
    cases = [("a fresh cartridge", None), ("SRAM full of $FF", "ff" * SRAM_SIZE), ("random SRAM", noise),
             ("a valid signature with a bad checksum", sram_image(1, 0, good=False)),
             ("a bad signature", sram_image(1, 0, sig=(0xB0, 0xB2))),
             (f"round {C['ROUNDS'] + 1}, past the last", sram_image(C["ROUNDS"], 0))]
    for what, sram in cases:
        r = run(kind="open", rom=patched, sram=sram)
        check(r["frames"] == ref["frames"] and r["ram"] == ref["ram"] and r["after"] == ref["after"],
              f"{what}: the PASSWORD screen opens empty and every frame and its state match stock's, typing included")


def saving(stock, patched, tmp):
    print("saving the round")
    ref = run(kind="new_game", rom=stock)
    r = run(kind="new_game", rom=patched)
    check(r["sram"][:10] == "b0b10000a5", f"a new game saves round 1 with no flags: {r['sram'][:10]}")
    check(r["frames"] == ref["frames"], f"and its first {len(ref['frames'])} frames match stock's")
    ref = run(kind="play", rom=stock, seed=4, rounds=4)
    r = run(kind="play", rom=patched, seed=4, rounds=4)
    follows = all(s[:3] == [0xB0, 0xB1, rnd] for rnd, s in r["log"])
    rounds = sorted({rnd + 1 for rnd, _ in r["log"]})
    check(follows and len(rounds) > 2, "after each round cleared, the save holds the round being played: "
          + ", ".join(map(str, rounds)))
    check(r["frames"] == ref["frames"] and [x[0] for x in r["log"]] == [x[0] for x in ref["log"]],
          f"typing a password and clearing {len(r['log']) - 1} rounds looks the same as stock over "
          f"{len(ref['frames'])} frames")

    r = run(kind="entry", rom=patched, word="KLL1", start=True)
    check(r["started"] == 2 and r["sram"][:10] == sram_image(2, 0)[:10],
          f"KLL1 typed on the patched game starts round 3 and saves it: {r['sram'][:10]}")
    after = run(kind="entry", rom=patched, sram=r["sram"])
    check(letters(after["buffer"]) == "KLL1" and after["accepted"][0] == 2,
          "after a power cycle KLL1 is on the PASSWORD screen, and A takes it to round 3")


NAV = [["UP", "UP", "UP", "A"], ["UP", "RIGHT", "A", "UP", "UP", "A"],
       ["LEFT", "UP", "UP", "UP", "RIGHT", "A", "DOWN", "DOWN", "A"], ["UP", "RIGHT", "RIGHT", "A"]]


def looks_typed(stock, patched, tmp):
    print("the pre-filled PASSWORD screen")
    rng = random.Random(5)
    cases = [(1, 0, "VGL1"), (0, 8, "VLT1"), (2, 0, "KLL1")]
    cases += [(rnd, rng.choice([0, 0, 4, 8, 12]), None) for rnd in (7, 24, 48, 73, 98, 99, rng.randrange(100))]
    for rnd, flags, want in cases:
        pre = run(kind="entry", rom=patched, sram=sram_image(rnd, flags), nav=NAV)
        word = letters(pre["buffer"])
        typed = run(kind="entry", rom=stock, word=word, nav=NAV)
        known = f" (the known password {want})" if want else ""
        check((want is None or word == want) and pre["accepted"] == typed["accepted"] and typed["accepted"][0] == rnd,
              f"round {rnd + 1}, flags {flags}: {word}{known}, which the stock game takes as round "
              f"{typed['accepted'][0] + 1} with the same flags")
        check(pre["state"] == typed["state"] and pre["frames"] == typed["frames"] and pre["nav"] == typed["nav"],
              "  and the screen, hand, marker and moving away from END match typing it on the stock game")

    source = open(os.path.join(P.HERE, "bb1save.asm")).read()
    cut = "    ld a,(HAND_X)               ; the grid column to go back to, as the game keeps\n" \
          "    ld (HAND_COL),a             ; it when the hand leaves the grid\n"
    assert cut in source
    broken = P.patch(open(stock, "rb").read(), verbose=False, source=source.replace(cut, ""))
    path = os.path.join(tmp, "control.gb")
    open(path, "wb").write(broken)
    pre = run(kind="entry", rom=path, sram=sram_image(1, 0), nav=NAV)
    typed = run(kind="entry", rom=stock, word="VGL1", nav=NAV)
    check(pre["frames"] == typed["frames"] and pre["nav"] != typed["nav"],
          "control: a build that leaves the hand's grid column unset looks the same but moves off from END differently")


class Call:
    """Runs one routine in PyBoy from the game's frame wait on the title
    screen, as if a caller had called it, and reads the registers back."""
    REGS = ("A", "F", "B", "C", "D", "E", "HL", "SP")
    WAIT = 0x0465                       # the game's wait-for-frames routine
    SENTINEL = 0x00F0                   # unused filler; the hook fires before it runs

    def __init__(self, rom):
        from pyboy import PyBoy
        self.pb = PyBoy(rom, window="null", sound_emulated=False)
        self.pb.tick(700, True)
        self.rom = open(rom, "rb").read()
        self.pending = None
        self.pb.hook_register(0, self.WAIT, self._enter, None)
        self.pb.hook_register(0, self.SENTINEL, self._leave, None)

    def run(self, addr, regs, bank=None, before=None):
        self.pending = dict(addr=addr, regs=regs, bank=bank, before=before, result=None)
        while self.pending["result"] is None:
            self.pb.tick(1, True)
        res, self.pending = self.pending["result"], None
        return res

    def mapped(self):
        now = bytes(self.pb.memory[0x4000:0x4040])
        return next(b for b in range(len(self.rom) // 0x4000) if self.rom[b * 0x4000:b * 0x4000 + 0x40] == now)

    def _enter(self, _):
        job = self.pending
        if not job or job.get("started"):
            return
        job["started"] = True
        pb, rf = self.pb, self.pb.register_file
        job["saved"] = {k: getattr(rf, k) for k in self.REGS}
        job["saved"]["PC"] = rf.PC
        job["was_bank"] = self.mapped()
        if job["bank"] is not None:
            pb.memory[0x2100] = job["bank"]
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
        res["sram_off"] = pb.memory[0xA000] == 0xFF and pb.memory[0xA004] == 0xFF
        pb.memory[0x0000] = 0x0A
        res["sram"] = list(pb.memory[0xA000:0xA005])
        pb.memory[0x0000] = 0x00
        res["mem"] = {a: pb.memory[a] for a in list(range(0xC900, 0xC920)) + SPRITES + [C["PF_PENDING"]]}
        pb.memory[0x2100] = job["was_bank"]
        for k in self.REGS:
            setattr(rf, k, job["saved"][k])
        rf.PC = job["saved"]["PC"]
        job["result"] = res


def routines(patched):
    print("the routines on their own (PyBoy)")
    _, _, labels = P.assemble(PROFILE)
    call = Call(patched)
    regs = dict(A=0x5A, F=0xB0, B=0x11, C=0x22, D=0x33, E=0x44, HL=0x5566)
    kept = lambda r, keys: r["sp_balanced"] and all(r[k] == regs[k] for k in keys)

    def game_round(pb):
        pb.memory[C["ROUND"]], pb.memory[C["FLAGS_A"]], pb.memory[C["FLAGS_B"]] = 41, 0x04, 0x08

    r = call.run(labels["save_round"], regs, before=game_round)
    check(r["sram"] == [0xB0, 0xB1, 41, 0x0C, (41 + 0x0C) ^ C["SUM_XOR"]] and r["sram_off"],
          f"save_round writes {bytes(r['sram']).hex(' ')} and leaves the SRAM disabled")
    check(r["HL"] == C["LOADER_HL"] and kept(r, ("A", "F", "B", "C", "D", "E")),
          f"  and returns HL = ${C['LOADER_HL']:04X}, as the instruction it replaces, with every other register and flag kept")

    def saved(image):
        def put(pb):
            pb.memory[0x0000] = 0x0A
            for i, v in enumerate(bytes.fromhex(image[:10])):
                pb.memory[0xA000 + i] = v
            pb.memory[0x0000] = 0x00
            pb.memory[C["SLOT"]] = 0x77
            pb.memory[C["PF_PENDING"]] = 0x55
            for i in range(4):
                pb.memory[C["SHOWN"] + i] = 0xEE
        return put

    z = dict(regs, A=0)
    r = call.run(labels["pf_init"], z, bank=3, before=saved(sram_image(1, 0)))
    shown = [r["mem"][C["SHOWN"] + i] for i in range(4)]
    check(letters(shown) == "VGL1" and r["mem"][C["PF_PENDING"]] == 1 and r["mem"][C["SLOT"]] == 0 and r["sram_off"],
          "pf_init with round 2 saved: SLOT = 0 as stock, VGL1 from the game's encoder, pending set, SRAM disabled")
    check(r["A"] == 0 and r["sp_balanced"] and all(r[k] == z[k] for k in ("B", "C", "D", "E", "HL")),
          "  and returns A = 0 with B, C, D, E and HL kept")
    r = call.run(labels["pf_init"], z, bank=3, before=saved(sram_image(1, 0, good=False)))
    check(r["mem"][C["PF_PENDING"]] == 0 and [r["mem"][C["SHOWN"] + i] for i in range(4)] == [0xEE] * 4
          and r["mem"][C["SLOT"]] == 0 and r["A"] == 0 and r["sram_off"],
          "pf_init with a bad checksum: clears pending, leaves SHOWN alone, SRAM disabled")

    def pending(flag):
        def put(pb):
            pb.memory[C["PF_PENDING"]] = flag
            pb.memory[C["PW_FLAGS"]] = 0x42
            for i, v in enumerate((31, 16, 21, 1)):
                pb.memory[C["SHOWN"] + i] = v
                pb.memory[C["BUFFER"] + i] = 0
            pb.memory[C["SLOT"]] = 0
        return put

    r = call.run(labels["pf_step"], regs, bank=3, before=pending(0))
    check(r["A"] == 0x42 and kept(r, ("B", "C", "D", "E", "HL")) and r["mem"][C["SLOT"]] == 0
          and [r["mem"][C["BUFFER"] + i] for i in range(4)] == [0] * 4,
          "pf_step with nothing pending: returns A = PW_FLAGS and changes nothing")
    r = call.run(labels["pf_step"], regs, bank=3, before=pending(1))
    m = r["mem"]
    check([m[C["BUFFER"] + i] for i in range(4)] == [31, 16, 21, 1] and m[C["SLOT"]] == 3
          and m[C["PF_PENDING"]] == 0 and m[C["MENU"]] == C["MENU_END"]
          and (m[C["HAND_Y"]], m[C["HAND_X"]], m[C["HAND_X2"]]) == (C["HAND_END_Y"], C["HAND_END_X"], C["HAND_END_X"] + 8),
          "pf_step pending: fills the buffer, SLOT = 3, the hand on END, pending cleared")
    check(r["A"] == 0x42 and kept(r, ("B", "C", "D", "E", "HL")),
          "  and returns A = PW_FLAGS with B, C, D, E and HL kept")
    call.pb.stop(save=False)


def main():
    if sys.argv[1:2] == ["--worker"]:
        worker(json.loads(sys.argv[2]))
        return
    stock, patched = sys.argv[1], sys.argv[2]
    print(f"stock   {hashlib.md5(open(stock, 'rb').read()).hexdigest()}")
    print(f"patched {hashlib.md5(open(patched, 'rb').read()).hexdigest()}\n")
    tmp = tempfile.mkdtemp()
    footprint(stock, patched)
    filler_unused(stock, tmp)
    wram_unused(stock)
    routines(patched)
    no_save(stock, patched)
    saving(stock, patched, tmp)
    looks_typed(stock, patched, tmp)
    print()
    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
