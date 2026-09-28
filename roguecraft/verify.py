#!/usr/bin/env python3
"""Check the Roguecraft run-save patch in emulation.

usage: verify.py STOCK.gbc PATCHED.gbc

Every run starts from a cold boot with scripted input. The one thing this
cannot do is play a floor to its exit - see the README - so a run on floor 2
is produced the way the game itself would produce one after a resume: the
game's own data_save, called mid-run with the floor counter at 1.
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

V = lambda i: 0xCBB7 + 2 * i          # GB Studio variable i
FLOOR, CARRIED_HP = V(75), V(76)      # floor index; hearts carried into a floor
HP = 0xDC44                           # live hearts (entity 0 of the health array)
SIG = bytes.fromhex("0741fe2b")       # slot signature, from ROM $0560
SLOT0 = 0xA000                        # slot 0: signature, then the save table
SLOT0_END = 0xA004 + 5166
SAVE_BANK, SAVE_FN = 0x14, 0x44E7
HOOK_BANK = 27
STUB = 0xDD60                         # unused WRAM (past the map fix's bytes), for the stand-in save


def entry_points():
    prof = next(iter(P.ROM_PROFILES.values()))
    src = P.build_preamble(prof) + open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "roguesave.asm")).read()
    code, labels, _ = P.asm.assemble(src, org=prof["hook_org"])
    return labels["run_start"], labels["floor_start"], len(code)


RUN_START, FLOOR_START, CODE_SIZE = entry_points()
failures = []


def patched_rom(path):
    return open(path, "rb").read()[HOOK_BANK * 0x4000] != 0xFF


def check(ok, what):
    print(f"   {'ok  ' if ok else 'FAIL'} {what}")
    if not ok:
        failures.append(what)


class Game:
    """A PyBoy instance with its own battery file, so power cycles are real."""

    def __init__(self, rom, battery=None):
        self.dir = tempfile.mkdtemp()
        self.rom = os.path.join(self.dir, "game.gbc")
        shutil.copy(rom, self.rom)
        if battery is not None:
            open(self.rom + ".ram", "wb").write(battery)
        self.pb = PyBoy(self.rom, window="null", sound_emulated=False)
        self.saves = []
        self.entries = []
        self.pb.hook_register(SAVE_BANK, SAVE_FN, self._on_save, None)
        if patched_rom(rom):
            for label, addr in (("run_start", RUN_START), ("floor_start", FLOOR_START)):
                self.pb.hook_register(HOOK_BANK, addr, self._entered(label), None)

    def _entered(self, label):
        return lambda _: self.entries.append((self.pb.frame_count, label, self.pb.memory[FLOOR]))

    def _on_save(self, _):
        pb = self.pb
        self.saves.append((pb.frame_count, pb.memory[pb.register_file.SP + 6], pb.memory[FLOOR]))

    def tick(self, n):
        self.pb.tick(n, True)

    def tap(self, b, hold=6, after=30):
        self.pb.button_press(b); self.tick(hold); self.pb.button_release(b); self.tick(after)

    def slot0(self):
        m = self.pb.memory
        sig = bytes(m[0, SLOT0:SLOT0 + 4])
        var = lambda i: m[0, 0xA004 + 2 * i] | m[0, 0xA004 + 2 * i + 1] << 8
        return sig == SIG, var(75), var(76)

    def sram(self):
        return b"".join(bytes(self.pb.memory[b, 0xA000:0xBFFF]) + bytes([self.pb.memory[b, 0xBFFF]])
                        for b in range(4))

    def power_off(self):
        self.pb.stop(save=True)
        battery = open(self.rom + ".ram", "rb").read()
        shutil.rmtree(self.dir, ignore_errors=True)
        return battery

    def screen(self):
        return self.pb.screen.image.convert("RGB").tobytes()

    # ---- scripted routes --------------------------------------------------
    def to_title(self):
        self.tick(1500)

    def start_game(self):
        """START GAME: hero select, or the RESUME / NEW GAME menu."""
        self.tap("start", after=60)

    def new_game(self, hero_steps=0):
        for _ in range(hero_steps):
            self.tap("right")
        self.tap("a", after=330)        # pick the hero -> floor card
        self.tap("a", after=180)        # PRESS A -> floor 1

    def stand_in_save(self, floor, hearts, slot=0):
        """The game's own data_save(slot), run mid-floor with the given floor and
        carried hearts - for slot 0, a run as a floor exit would leave it."""
        pb = self.pb
        pb.memory[FLOOR] = floor
        pb.memory[CARRIED_HP] = hearts
        ret = pb.register_file.PC
        code = bytes([0xF5, 0xC5, 0xD5, 0xE5, 0x3E, slot, 0xF5, 0x33, 0x1E, SAVE_BANK,
                      0x21, SAVE_FN & 0xFF, SAVE_FN >> 8, 0xCD, 0x01, 0x3E, 0x33,
                      0xE1, 0xD1, 0xC1, 0xF1, 0xC3, ret & 0xFF, ret >> 8])
        for i, b in enumerate(code):
            pb.memory[STUB + i] = b
        pb.register_file.PC = STUB
        self.tick(30)


def footprint(stock, patched):
    print("1. the patch touches only what it says it does")
    a, b = open(stock, "rb").read(), open(patched, "rb").read()
    prof = P.load_profile(a)
    allowed = {P.OFF_GLOBAL_SUM, P.OFF_GLOBAL_SUM + 1}
    for s in prof["call_sites"]:
        allowed |= {s + 1, s + 2, s + 3}
    base = prof["hook_bank"] * P.BANK_SIZE
    allowed |= set(range(base, base + CODE_SIZE))
    for off, expect, _ in prof["counter_sites"]:
        allowed |= set(range(off, off + len(expect)))
    off, expect = prof["chest_spawn_site"]
    allowed |= set(range(off, off + len(expect)))
    for off, _, _ in prof["map_natives"]:
        allowed |= {off + 1, off + 2, off + 3}
    allowed |= set(range(prof["map_hide_call"], prof["map_hide_call"] + 8))
    for off, *_ in prof["version_tiles"]:
        allowed |= set(range(off, off + 16))
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    check(len(a) == len(b), "same size as stock")
    check(all(i in allowed for i in diff), f"{len(diff)} bytes differ, all inside the patch's footprint")
    check(a[0x100:0x14E] == b[0x100:0x14E], "cartridge header untouched")


def floor_one(stock, patched):
    print("2. floor 1 plays as stock, and saves nothing")
    frames = {}
    for tag, rom in (("stock", stock), ("patched", patched)):
        g = Game(rom)
        g.to_title(); g.start_game(); g.new_game()
        shots = []
        for i in range(60):
            g.pb.button_press(["right", "down", "left", "up"][(i // 15) % 4]); g.tick(10)
            g.pb.button_release(["right", "down", "left", "up"][(i // 15) % 4]); g.tick(10)
            shots.append(hashlib.md5(g.screen()).hexdigest())
        frames[tag] = (shots, [s for s in g.saves if s[1] == 0], list(g.entries), g.pb.memory[FLOOR])
        g.power_off()
    same = sum(1 for x, y in zip(frames["stock"][0], frames["patched"][0]) if x == y)
    check(same == len(frames["stock"][0]), f"{same}/{len(frames['stock'][0])} sampled frames identical to stock")
    check(not frames["patched"][1], "no slot-0 save on floor 1")
    check([e[1] for e in frames["patched"][2]] == ["run_start"], f"the first floor went through run_start ({frames['patched'][2]})")
    check(frames["patched"][3] == 0, "floor counter reads 0 on floor 1")


def make_run(patched, hearts):
    """Floor 1 of a new game, then a stand-in save of a run on floor 2."""
    g = Game(patched)
    g.to_title(); g.start_game(); g.new_game()
    g.tick(120)
    g.stand_in_save(floor=1, hearts=hearts)
    ok, fl, hp = g.slot0()
    return g.power_off(), (ok, fl, hp)


def resume(patched, battery, check_menu=True):
    g = Game(patched, battery)
    entries = g.entries
    g.to_title()
    before = len(g.saves)
    g.start_game()
    menu_saves = len(g.saves) - before
    g.tap("a", after=240)               # RESUME GAME
    g.tap("a", after=240)               # PRESS A on the floor card
    return g, entries, menu_saves


def resume_path(stock, patched):
    print("3. arriving on a floor saves the run - hearts included - and resume restores it")
    battery, (ok, fl, hp) = make_run(patched, hearts=3)
    check(ok and fl == 1 and hp == 3, f"stand-in run on floor 2 with 3 hearts (slot 0: valid={ok}, floor={fl}, hearts={hp})")
    g, entries, menu_saves = resume(patched, battery)
    check(menu_saves == 0, "START GAME's resume check writes nothing")
    check([e[1] for e in entries] == ["floor_start"], f"floor_start ran once as the floor started ({entries})")
    hook_saves = [s for s in g.saves if s[1] == 0]
    check(len(hook_saves) == 1 and hook_saves[0][2] == 1, f"it saved slot 0 on floor 2 ({hook_saves})")
    ok, fl, hp = g.slot0()
    check(ok and fl == 1 and hp == 3, f"slot 0 now holds floor 2 with 3 hearts (valid={ok}, floor={fl}, hearts={hp})")
    check(g.pb.memory[HP] == 3, f"the resumed hero has 3 hearts, not a free refill ({g.pb.memory[HP]})")
    battery2 = g.power_off()
    outside = lambda s: s[SLOT0_END - 0xA000:]      # the battery file is the four banks in order
    check(outside(battery) == outside(battery2), "nothing outside slot 0 changed (achievements intact)")
    g, entries, _ = resume(patched, battery2)
    check(g.pb.memory[FLOOR] == 1 and g.pb.memory[HP] == 3,
          f"a second power cycle resumes the same floor and hearts (floor={g.pb.memory[FLOOR]}, hearts={g.pb.memory[HP]})")
    g.power_off()
    return battery2


def quit_and_new_game(patched, battery):
    print("4. quitting keeps the run; a new game leaves it until floor 2")
    g, _, _ = resume(patched, battery)
    g.tap("start", after=40); g.tap("start", after=540)        # START x2 -> title
    ok, fl, hp = g.slot0()
    check(ok and fl == 1, f"after quitting mid-floor, slot 0 still holds floor 2 (floor={fl})")
    g.start_game()
    since = len(g.saves)                                        # (the resume above saved once)
    g.tap("down"); g.tap("a", after=60)                         # NEW GAME
    g.new_game()
    g.tick(300)
    new_saves = [s for s in g.saves[since:] if s[1] == 0]
    check(not new_saves, "a new game's first floor writes nothing")
    check(g.pb.memory[FLOOR] == 0, f"and its floor counter is back to 0, not the old run's ({g.pb.memory[FLOOR]})")
    battery = g.power_off()
    g = Game(patched, battery)
    g.to_title(); g.start_game()
    check(g.pb.memory[FLOOR] == 1, "after a power cycle the older run is still offered")
    g.power_off()


def every_floor(patched):
    print("6. every later floor's script saves its own floor")
    got = {}
    for k in range(1, 11):
        battery, _ = make_run(patched, hearts=2)
        # rewrite the stand-in's floor: resume onto floor k+1
        g = Game(patched, battery)
        g.to_title(); g.start_game(); g.new_game(); g.tick(60)
        g.stand_in_save(floor=k, hearts=2)
        battery = g.power_off()
        g, entries, _ = resume(patched, battery)
        saves = [s for s in g.saves if s[1] == 0]
        ok, fl, hp = g.slot0()
        got[k] = ([e[1] for e in entries], [s[2] for s in saves], fl)
        g.power_off()
    good = all(v == (["floor_start"], [k], k) for k, v in got.items())
    check(good, "floors 2-11 each ran floor_start and saved their own number" +
          ("" if good else f": {got}"))


def death(patched):
    print("5. dying ends the run: RESUME GAME disappears")
    battery, _ = make_run(patched, hearts=1)
    g, _, _ = resume(patched, battery)
    check(g.pb.memory[HP] == 1, f"resumed on floor 2 with one heart ({g.pb.memory[HP]})")
    random.seed(3)
    for i in range(20000):
        if i % 40 == 0:
            for d in ("up", "down", "left", "right"):
                g.pb.button_release(d)
            g.pb.button_press(random.choice(("up", "down", "left", "right")))
        g.tick(1)
        if any(s[1] == 0 and s[2] == 0 for s in g.saves):
            break
    for d in ("up", "down", "left", "right"):
        g.pb.button_release(d)
    g.tick(300)
    deaths = [s for s in g.saves if s[1] == 0 and s[2] == 0]
    check(bool(deaths), "the hero was killed and the game-over save ran")
    ok, fl, _ = g.slot0()
    check(fl == 0, f"slot 0 now reads floor 0 (valid={ok}, floor={fl})")
    battery = g.power_off()
    g = Game(patched, battery)
    g.to_title(); g.start_game()
    check(g.pb.memory[FLOOR] == 0, "after a power cycle, START GAME goes straight to hero select")
    g.power_off()


C = P.ROM_PROFILES["6de80f13b9ab562de2227ea5dd818275"]["consts"]
TOTAL, FOUND = C["CHESTS_TOTAL"], C["CHESTS_FOUND"]
COINS = V(5)                                         # the gold counter on the HUD
word = lambda m, a: m[a] | m[a + 1] << 8


def room_items(g):
    m = g.pb.memory
    k = 5 * m[C["ROOM_ROW"]] + m[C["ROOM_COL"]]
    return word(m, C["ROOM_ITEMS"] + 2 * k)


def phantom_floor(stock, patched):
    print("7. the last floor's hidden layout no longer adds to the chest total")
    for floor, what in ((10, "last floor (the boss arena)"), (1, "floor 2, an ordinary floor")):
        grew = {}
        for tag, rom in (("stock", stock), ("patched", patched)):
            g = Game(rom)
            g.to_title(); g.start_game(); g.new_game(); g.tick(90)
            g.stand_in_save(floor=floor, hearts=5)
            saved = word(g.pb.memory, TOTAL)
            battery = g.power_off()
            g = Game(rom, battery)
            g.to_title(); g.start_game(); g.tap("a", after=240); g.tap("a", after=240)
            grew[tag] = word(g.pb.memory, TOTAL) - saved
            g.power_off()
        if floor == 10:
            check(grew["stock"] > 0, f"{what}: stock adds {grew['stock']} chests nobody can reach (the bug)")
            check(grew["patched"] == 0, f"{what}: the patch adds none ({grew['patched']})")
        else:
            check(grew["patched"] == grew["stock"] > 0,
                  f"{what}: counted as stock does ({grew['stock']} -> {grew['patched']})")


def start_room(rom):
    """Floor 1's start room with its chest just above the hero's path, by the
    same inputs every time: hero at (4,4), chest at (3,3)."""
    g = Game(rom)
    g.to_title()
    g.tap("start", after=12); g.tick(60)
    g.tap("a", after=12); g.tick(90); g.tick(240)
    g.tap("a", after=12); g.tick(180)
    return g


def walk(g, moves):
    for d in moves:
        g.pb.button_press(d); g.tick(10); g.pb.button_release(d); g.tick(26)


def open_chest_and_leave(rom):
    g = start_room(rom)
    m = g.pb.memory
    ready = (m[0xC107], m[0xC109]) == (4, 4) and m[C["CHEST_HP"]] == 2 and room_items(g) & 2
    opens = []
    g.pb.hook_register(2, 0x6438, lambda _: opens.append(g.pb.frame_count), None)
    walk(g, ["left", "up", "up"]); g.tick(60)                   # open it; its gold is left lying
    gold = word(m, COINS)
    walk(g, ["down"] + ["right"] * 7); g.tick(90)               # out through the east door
    walk(g, ["left"] * 3); g.tick(90)                           # and back
    back = (m[C["ROOM_COL"]], m[C["ROOM_ROW"]])
    chest_back = m[C["CHEST_HP"]]
    walk(g, ["left"] * 5 + ["up"] * 3); g.tick(60)              # across the room, over whatever is there
    result = dict(ready=ready, back=back, chest_back=chest_back, opens=len(opens), found=word(m, FOUND),
                  hp_after=m[C["CHEST_HP"]], chest_bit=room_items(g) & 2, coins=word(m, COINS) - gold)
    g.power_off()
    return result


def reopen(stock, patched):
    print("8. an opened chest stays open, and its gold waits for you")
    s, p = open_chest_and_leave(stock), open_chest_and_leave(patched)
    check(s["ready"] and p["ready"], "the start room has its chest where the route expects")
    check(s["chest_back"] == 2 and s["opens"] == 2,
          f"stock: walk out without the gold and back, and the chest is shut again and opens twice (the bug; found={s['found']})")
    check(p["back"] == s["back"] and p["chest_back"] == 1,
          f"patched: back in the same room {p['back']}, the chest's gold is still there, not a shut chest")
    check(p["opens"] == 1 and p["found"] == 1, f"patched: it opened once and counts once (opens={p['opens']}, found={p['found']})")
    check(p["hp_after"] == 0 and p["chest_bit"] == 0 and p["coins"] > 0,
          f"patched: walking over the gold picks it up (+{p['coins']} gold) and the room's chest is done")


def gold_pickup(stock, patched):
    print("9. picking up a chest's gold leaves the room's other items alone")
    out = {}
    for tag, rom in (("stock", stock), ("patched", patched)):
        g = start_room(rom)
        before = room_items(g)
        walk(g, ["left", "up", "up", "up", "up"]); g.tick(60)   # open it, then step onto the gold
        out[tag] = (before, room_items(g), word(g.pb.memory, FOUND))
        g.power_off()
    b, a, f = out["patched"]
    check(out["stock"] == out["patched"], f"same outcome as stock: items {b:#06x} -> {a:#06x}, found {f}")
    check(a == b & ~2 and f == 1, "exactly the chest bit cleared, and the chest counted once")


MAP_CELLS = {77, 78, 79, 87, 88, 89, 97, 98, 99}   # the room cells the mini-map covers
LOCK = C["ATTACK_LOCK"]
# Floor 1, from the start room (check 8's chest, then out east) and south into
# room (2,1), where a tentacle monster stands in a cell the map covers.
TO_TENTACLE = (["left", "up", "up", 60, "down"] + ["right"] * 7 + [90]
               + ["right"] * 4 + ["down"] * 5)


def route(g, moves):
    """d-pad moves with check 8's timing; a number waits that many frames.
    Going through a door takes 60 frames more."""
    m = g.pb.memory
    for d in moves:
        if isinstance(d, int):
            g.tick(d)
            continue
        room = (m[C["ROOM_COL"]], m[C["ROOM_ROW"]])
        g.pb.button_press(d); g.tick(10); g.pb.button_release(d); g.tick(26)
        if (m[C["ROOM_COL"]], m[C["ROOM_ROW"]]) != room:
            g.tick(60)


class Drawn:
    """How many hardware sprites the engine last gave each actor. The game
    doesn't redraw its actors every frame when it is busy, so this keeps each
    one's latest count."""
    def __init__(self, g):
        self.g, self.now = g, {}
        g.pb.hook_register(0, 0x144E, self._drew, None)     # after move_metasprite

    def _drew(self, _):
        m = self.g.pb.memory
        self.now[m[0xC528] | m[0xC529] << 8] = self.g.pb.register_file.A

    def tick(self):
        self.g.tick(1)
        return self.now


def toggle_map(rom, lock):
    """Hold B for the map over the tentacle, with the attack lock at `lock` as
    the map opens, and count the frames it stays undrawn once the map is shut."""
    g = start_room(rom)
    route(g, TO_TENTACLE)
    m = g.pb.memory
    ent = 2
    actor = C["ACTORS"] + 52 * m[C["ENTITY_ACTOR"] + ent]
    ready = (m[C["ROOM_COL"]], m[C["ROOM_ROW"]]) == (2, 1) and m[HP + ent] > 0 \
        and m[0xDCCA + ent] in MAP_CELLS
    d = Drawn(g)
    m[LOCK] = lock
    g.pb.button_press("b")
    hidden = 0
    for _ in range(30):
        hidden += d.tick().get(actor, 1) == 0
    g.pb.button_release("b")
    shut, gone, shots, left = None, 0, [], None
    for f in range(90):
        drew = d.tick()
        shots.append(hashlib.md5(g.screen()).hexdigest())
        if shut is None and m[0xFF4A] >= 136:
            shut = f
        if shut is not None and f == shut + 2:
            left = m[LOCK]
        if shut is not None and f > shut + 1 and drew.get(actor, 0) == 0:
            gone += 1
    g.power_off()
    return dict(ready=ready, hidden=hidden, gone=gone, lock_after=left, shots=shots)


def mini_map(stock, patched):
    print("10. an enemy the mini-map covered is back as soon as the map shuts")
    s, p = toggle_map(stock, 0), toggle_map(patched, 0)
    check(s["ready"] and p["ready"], "floor 1, room (2,1): the tentacle stands in a cell the map covers")
    check(s["hidden"] > 20 and p["hidden"] > 20, "with the map up, the game hides it (as stock)")
    check(s["gone"] == 0 and s["shots"] == p["shots"],
          f"no recent attack: it comes straight back, frame for frame as stock ({p['gone']})")
    # every attack sets the lock to 60; this is one 30 frames before the map shuts
    s, p = toggle_map(stock, 60), toggle_map(patched, 60)
    check(s["gone"] > 20, f"right after an attack: stock leaves it invisible for {s['gone']} frames (the bug)")
    check(p["gone"] == 0, f"patched: back as the map shuts ({p['gone']} frames)")
    check(p["lock_after"] == s["lock_after"] > 0,
          f"and the lock still runs for everything else ({s['lock_after']} -> {p['lock_after']})")


def old_save(stock, patched):
    print("11. a save file from the stock game works as it is")
    # what the stock game leaves on the cartridge: the achievements slot, and
    # a run slot reading floor 0 from its last game over
    g = Game(stock)
    g.to_title(); g.start_game(); g.new_game(); g.tick(120)
    g.stand_in_save(floor=0, hearts=0, slot=1)
    g.stand_in_save(floor=0, hearts=0, slot=0)
    battery = g.power_off()
    seen = {}
    for tag, rom in (("stock", stock), ("patched", patched)):
        g = Game(rom, battery)
        g.to_title()
        m = g.pb.memory
        variables = bytes(m[a] for a in range(0xCBB7, 0xCBB7 + 2 * 1792))
        g.start_game()
        seen[tag] = (variables, g.screen(), g.power_off())
    check(seen["stock"][0] == seen["patched"][0], "at the title, every game variable loads as it does on stock")
    check(seen["stock"][1] == seen["patched"][1], "START GAME shows the same screen as stock (hero select, no run)")
    check(seen["patched"][2] == battery, "and nothing on the cartridge changes until there's a run to save")


GLYPHS = {"v": ["...", "#.#", "#.#", "#.#", ".#."], "1": ["##.", ".#.", ".#.", ".#.", "###"],
          ".": [".", ".", ".", ".", "#"], "0": ["###", "#.#", "#.#", "#.#", "###"],
          "+": ["...", ".#.", "###", ".#.", "..."]}
TEXT_X, TEXT_Y, TEXT_W = 133, 136, 25     # the version's box on the title: x 133-157, y 136-142


def picture(text):
    """The version as the title draws it: 3x5 glyphs a pixel apart, with an
    empty row above and below, padded to the box's width."""
    rows = [" ".join(g) for g in zip(*(GLYPHS[ch] for ch in text))]
    rows = [r.replace(" ", ".").ljust(TEXT_W, ".") for r in rows]
    return ["." * TEXT_W] + rows + ["." * TEXT_W]


def title_version(stock, patched):
    print("12. the title screen reads v1.000+, and is otherwise stock")
    shots = {}
    for tag, rom in (("stock", stock), ("patched", patched)):
        g = Game(rom)
        g.to_title()
        shots[tag] = g.pb.screen.image.convert("RGB")
        g.power_off()
    s, p = shots["stock"], shots["patched"]
    text, back = s.getpixel((137, 141)), s.getpixel((136, 139))   # the 1's foot, and the gap before it
    in_box = lambda x, y: TEXT_X <= x < TEXT_X + TEXT_W and TEXT_Y <= y < TEXT_Y + 7

    def reads(img):
        return ["".join("#" if img.getpixel((x, y)) == text else "." if img.getpixel((x, y)) == back else "?"
                        for x in range(TEXT_X, TEXT_X + TEXT_W)) for y in range(TEXT_Y, TEXT_Y + 7)]
    check(reads(s) == picture("v1.0000"), "stock reads v1.0000 in the corner (the picture this check expects)")
    got = reads(p)
    check(got == picture("v1.000+"), "patched reads v1.000+, text on the stock background:\n" +
          "\n".join(f"          {r}" for r in got))
    same = all(s.getpixel((x, y)) == p.getpixel((x, y))
               for y in range(144) for x in range(160) if not in_box(x, y))
    check(same, "every other pixel of the title matches stock")


def main():
    stock, patched = sys.argv[1], sys.argv[2]
    print(f"stock   {hashlib.md5(open(stock, 'rb').read()).hexdigest()}")
    print(f"patched {hashlib.md5(open(patched, 'rb').read()).hexdigest()}\n")
    footprint(stock, patched)
    floor_one(stock, patched)
    battery = resume_path(stock, patched)
    quit_and_new_game(patched, battery)
    death(patched)
    every_floor(patched)
    phantom_floor(stock, patched)
    reopen(stock, patched)
    gold_pickup(stock, patched)
    mini_map(stock, patched)
    old_save(stock, patched)
    title_version(stock, patched)
    print()
    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
