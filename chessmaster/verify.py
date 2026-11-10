#!/usr/bin/env python3
"""Check The Chessmaster crash fix in emulation.

usage: verify.py STOCK.gb PATCHED.gb

Needs `pip install pyboy pillow python-chess`. Every check plays the game from a
cold boot with ordinary button input, the way a player enters moves, and reads
the board and the menus from memory and the screen.
"""
import hashlib
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "common"))
import chess
import patch as P
from ips import apply_ips
from pyboy import PyBoy

PROFILE = next(iter(P.ROM_PROFILES.values()))
C = PROFILE["consts"]
INFINITE = 15                           # presses of A on the level line, from the first level
BOARD = 0xD100                          # 0x88 board, 16 bytes a rank, rank 8 first
CURSOR_Y, CURSOR_X = 0xC000, 0xC001     # the cursor sprite
TICK, TICK_INC = 0x26EB, 0x26F9         # the clock block's first instruction, and its inc (hl)
VBLANK_VECTOR = 0x0040
CLOCKS = (0xD585, 0xD587)
STRAYS = tuple(c + 0x200 for c in CLOCKS)   # where the stock tick lands when B is 2
# A recorded 126-ply game. Black to move after it, Chessmaster's search on
# Infinite reaches the root re-search bug and, on the stock ROM, crashes.
REORDER_GAME = (
    "e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6 f2f4 e7e5 d4f3 d8c7 f4e5 d6e5 c3d5 f6d5 e4d5 f7f6 "
    "h2h4 e5e4 d1e2 c7a5 f3d2 b8d7 e2e4 d7e5 a2a4 f8c5 c2c4 e8g8 b2b3 h7h6 c1b2 c5f2 e1d1 f8e8 d1c1 c8d7 "
    "e4f4 f2c5 h4h5 a8c8 d2e4 c5b4 f4g3 g8h8 e4c3 b4d6 g3f2 e5g4 f2d4 d6e5 d4d2 g4f2 d2f2 e5c3 f1d3 c3b2 "
    "c1b2 a5b4 g2g3 e8e5 f2f3 b4d2 d3c2 e5e3 f3d1 d2c3 b2b1 e3g3 a4a5 g3e3 d5d6 c8c5 d1c1 d7c6 h1h4 e3e5 "
    "h4f4 e5e1 c2d1 c6e4 f4e4 c3c1 b1c1 e1e4 d6d7 e4d4 d7d8q d4d8 a1a2 h8g8 d1g4 f6f5 g4f3 f5f4 f3b7 g8f7 "
    "b7a6 f4f3 a6b7 c5f5 a2f2 f7f6 f2f3 f5f3 b7f3 d8d3 f3d1 d3d6 d1c2 f6e5 c4c5 d6f6 b3b4 e5d5 c1b2 d5c4 "
    "b2a3 c4c3 c2a4 f6f1 a4b3").split()
OPENING = "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 d2d3 f8c5".split()
OUT_OF_BOOK = "a2a4 h7h5 b2b4 g7g5 c2c4".split()
failures = []


def check(ok, what):
    print(f"   {'ok  ' if ok else 'FAIL'} {what}")
    if not ok:
        failures.append(what)


class Game:
    """One cold-booted Chessmaster, driven with button presses."""

    def __init__(self, rom, level=INFINITE):
        self.pb = PyBoy(rom, window="null", cgb=False, sound_emulated=False)
        self.pb.set_emulation_speed(0)
        self.board = chess.Board()
        self.frames = []                # (board bytes, screen line 3) after each tick, for comparisons
        self.record = False
        self.tick(600)
        self.press("start")
        self.menu("Actions")
        self.press("a")
        assert "2" in self.line(5), self.line(5)            # two players: every move entered by hand
        self.menu("Settings")
        self.press("down")
        for _ in range(level):
            self.press("a")
        self.level = self.line(6)
        self.press("down")
        self.press("a")
        assert "Off" in self.line(7), self.line(7)          # Deep Thinking off
        self.press("select")

    def tick(self, n=1):
        for _ in range(n):
            self.pb.tick(1, False)
            if self.record:
                self.frames.append((bytes(self.pb.memory[0xC000:0xE000]), self.line(3)))

    def press(self, key, n=10, after=60):
        self.pb.button_press(key)
        self.tick(n)
        self.pb.button_release(key)
        self.tick(after)

    def line(self, row):
        def char(v):
            if 1 <= v <= 26:
                return chr(v + 64)
            if 81 <= v <= 106:
                return chr(v - 16)
            if 107 <= v <= 132:
                return chr(v - 10)
            if 133 <= v <= 142:
                return chr(v - 85)
            return " "
        return "".join(char(x) for x in self.pb.tilemap_background[0:20, row]).strip()

    def menu_name(self):
        text = self.line(3)
        return text if text in ("Actions", "Settings") else ""

    def menu(self, name):
        for _ in range(6):
            if self.menu_name() == name:
                return
            self.press("select")
        raise AssertionError(("menu", name, self.menu_name()))

    def placement(self):
        b = chess.Board(None)
        types = [chess.PAWN, chess.KING, chess.KNIGHT, chess.ROOK, chess.BISHOP, chess.QUEEN]
        for row in range(8):
            for f in range(8):
                p = self.pb.memory[BOARD + row * 16 + f]
                if p:
                    if (p & 7) >= len(types):
                        return None
                    b.set_piece_at(chess.square(f, 7 - row), chess.Piece(types[p & 7], bool(p & 16)))
        return b.board_fen()

    def cursor(self, square):
        for at, target, neg, pos in ((CURSOR_X, 24 + 16 * chess.square_file(square), "left", "right"),
                                     (CURSOR_Y, 32 + 16 * (7 - chess.square_rank(square)), "up", "down")):
            for _ in range(4):
                delta = target - self.pb.memory[at]
                if not delta:
                    break
                self.press(pos if delta > 0 else neg, abs(delta), 3)

    def human(self, uci):
        move = chess.Move.from_uci(uci)
        assert move in self.board.legal_moves, (self.board.fen(), uci)
        self.cursor(move.from_square)
        self.press("a", after=20)
        self.cursor(move.to_square)
        self.press("a", after=1)
        if move.promotion:              # starts at queen; A cycles Q, R, B, N and SELECT accepts
            self.tick(120)
            for _ in range([chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT].index(move.promotion)):
                self.press("a")
            self.press("select", after=1)
        self.board.push(move)
        for _ in range(600):
            if self.placement() == self.board.board_fen():
                break
            self.tick()
        else:
            raise AssertionError(("move not shown", uci))
        self.tick(20)

    def one_player(self, computer_white):
        """Hand the side to move to the computer, as the menus do; it starts thinking if it is to move."""
        self.menu("Actions")
        self.press("a")
        self.press("a")
        assert "1" in self.line(5), self.line(5)
        if computer_white:
            self.press("down")
            self.press("a", after=1)
        else:
            self.menu("Settings")
            self.press("select", after=1)

    def crashed(self):
        pc, sp = self.pb.register_file.PC, self.pb.register_file.SP
        return pc >= 0x8000 or pc in (0x38, 0x39) or not 0xDE00 <= sp <= 0xDFFF

    def reply(self, frames, force_at=None):
        """Wait for the computer's move, sending Force Move at force_at. The move, or None if it crashes first."""
        expected = {}
        for m in self.board.legal_moves:
            q = self.board.copy()
            q.push(m)
            expected[q.board_fen()] = m
        stable, found = 0, None
        for i in range(frames):
            self.tick()
            if self.crashed():
                return None
            place = self.placement()
            if place in expected:
                stable, found = (stable + 1, found) if expected[place] == found else (1, expected[place])
                if stable >= 20:
                    if self.menu_name():
                        self.press("select")
                    self.board.push(found)
                    self.tick(40)
                    return found
            else:
                stable, found = 0, None
            if force_at is not None and i == force_at:
                for _ in range(6):
                    if self.menu_name() == "Actions" or self.placement() in expected:
                        break
                    self.press("select")
                if self.placement() not in expected:
                    self.press("down")
                    self.press("down")
                    self.press("a", after=1)
        return None

    def stop(self):
        self.pb.stop(save=False)


def footprint(stock, patched):
    print("footprint")
    s, p = open(stock, "rb").read(), open(patched, "rb").read()
    check(hashlib.md5(s).hexdigest() in P.ROM_PROFILES, "the stock ROM is the release the patch is made for")
    check(P.patch(s, verbose=False) == p, "the patched ROM is exactly what patch.py builds from the stock one")
    ips = P.make_ips(s, p)
    committed = open(os.path.join(P.HERE, "Chessmaster-crashfix.ips"), "rb").read()
    check(ips == committed and apply_ips(s, committed) == p,
          f"the committed {len(committed)}-byte IPS is what patch.py writes, and it turns the stock ROM into the patched one")
    tick, order, _ = P.assemble(PROFILE)
    allowed = set(range(PROFILE["tick_org"], PROFILE["tick_org"] + len(tick)))
    allowed |= set(range(PROFILE["order_org"], PROFILE["order_org"] + len(order)))
    for bank, address, _, _ in PROFILE["hooks"]:
        allowed |= set(range(P.file_offset(bank, address), P.file_offset(bank, address) + 3))
    allowed |= {0x14E, 0x14F}
    changed = [i for i in range(len(s)) if s[i] != p[i]]
    stray = [hex(i) for i in changed if i not in allowed]
    check(len(p) == len(s) and s[0x100:0x14E] == p[0x100:0x14E] and P.global_checksum(p) == (p[0x14E] << 8 | p[0x14F]),
          "same size, the header untouched, and the global checksum repaired")
    check(not stray, f"{len(changed)} stock bytes differ, all at the patch's own sites (stray: {stray[:5]})")


def session(rom, frames=600):
    """Two-player entry of an opening, then the computer thinks on Infinite for a while: every frame's work RAM
    and menu line, and the computer's reply after Force Move."""
    g = Game(rom)
    g.record = True
    for u in OPENING:
        g.human(u)
    g.one_player(computer_white=True)
    reply = g.reply(frames + 1200, force_at=frames)
    out = g.frames, reply
    g.stop()
    return out


def filler_unused(stock, tmp):
    print("the filler the root order routine goes over")
    s = bytearray(open(stock, "rb").read())
    lo, hi = PROFILE["order_padding"]
    filled = bytearray(s)
    filled[lo:hi] = bytes([0xD3]) * (hi - lo)       # an invalid opcode: running it locks the CPU
    control = bytearray(s)
    control[VBLANK_VECTOR] = 0xD9                   # reti: the VBlank handler never runs
    paths = {}
    for name, data in (("filled", filled), ("control", control)):
        paths[name] = os.path.join(tmp, name + ".gb")
        open(paths[name], "wb").write(bytes(data))
    ref, ref_move = session(stock)
    got, got_move = session(paths["filled"])
    check(got == ref and got_move == ref_move,
          f"filling ${lo:04X}-${hi - 1:04X} with $D3 changes none of {len(ref)} frames of menus, move entry and "
          f"thinking, nor the reply ({ref_move})")
    try:
        ctl, _ = session(paths["control"])
        diff = sum(a != b for a, b in zip(ref, ctl)) + abs(len(ref) - len(ctl))
    except AssertionError:
        diff = len(ref)
    check(diff > len(ref) // 4, f"control: breaking the VBlank vector changes {diff} of them")


def thinking_after_a_move(rom):
    """The computer plays Black on Infinite and thinks after a move of White's, out of its opening book, with its
    clock running. A turn handed over from the menu does not run the clock."""
    g = Game(rom)
    for u in OUT_OF_BOOK[:-1]:
        g.human(u)
    g.one_player(computer_white=False)
    g.human(OUT_OF_BOOK[-1])
    return g


def clock_tick(stock, patched):
    print("the thinking clock")
    for name, rom in (("stock", stock), ("patched", patched)):
        g = thinking_after_a_move(rom)
        seen = []

        def start(_):
            if not seen:
                g.pb.register_file.B = 2        # as when the tick interrupts code that holds 2 in B

        def inc(_):
            seen.append(g.pb.register_file.HL)
        g.pb.hook_register(0, TICK, start, None)
        g.pb.hook_register(0, TICK_INC, inc, None)
        watched = (*STRAYS, *CLOCKS)
        before = [g.pb.memory[a] for a in watched]
        for _ in range(120):
            if seen:
                break
            g.tick()
        if not seen:
            check(False, f"{name}: the clock ticks while the computer thinks")
            g.stop()
            continue
        g.tick()
        moved = [a for a, x, y in zip(watched, before, [g.pb.memory[a] for a in watched]) if x != y]
        if name == "stock":
            check(seen[0] in STRAYS and moved == [seen[0]],
                  f"control: on the stock ROM, a tick with B = 2 increments ${seen[0]:04X} instead of a clock")
        else:
            check(seen[0] in CLOCKS and moved == [seen[0]],
                  f"patched, a tick with B = 2 advances the clock at ${seen[0]:04X} and leaves "
                  f"${STRAYS[0]:04X} and ${STRAYS[1]:04X} alone")
        g.stop()

    # With B zero, as at almost every tick, the stock and patched blocks must do the same thing in the same cycles.
    s = bytearray(open(stock, "rb").read())
    tick, _, _ = P.assemble(PROFILE)
    tick_only = bytearray(s)
    tick_only[PROFILE["tick_org"]:PROFILE["tick_org"] + len(tick)] = tick
    runs = {}
    for name, data in (("stock", bytes(s)), ("tick only", bytes(tick_only))):
        path = os.path.join(tempfile.mkdtemp(), "rom.gb")
        open(path, "wb").write(data)
        g = thinking_after_a_move(path)
        bs = []
        g.pb.hook_register(0, TICK, lambda _: bs.append(g.pb.register_file.B), None)
        g.record = True
        g.tick(1800)
        runs[name] = (g.frames, bs)
        g.stop()
    ticks = len(runs["stock"][1])
    check(runs["stock"][0] == runs["tick only"][0] and not any(runs["stock"][1]),
          f"with B zero at all {ticks} ticks of 1800 frames of thinking, the tick block alone changes no frame's "
          "work RAM: same result, same cycles")


def root_order(stock, patched):
    print("the root move order")
    for name, rom in (("stock", stock), ("patched", patched)):
        g = Game(rom)
        for u in REORDER_GAME:
            g.human(u)
        reorders = []
        if name == "patched":
            entry = {}

            def on_entry(_):
                entry["first"] = g.pb.memory[C["ROOT_ORDER"]]

            def on_line(_):
                if "first" in entry and g.pb.memory[C["ROOT_ORDER"]] != entry.pop("first"):
                    reorders.append(g.pb.frame_count)
            g.pb.hook_register(0, PROFILE["order_org"], on_entry, None)
            g.pb.hook_register(2, C["ITER_LINE"], on_line, None)
        g.one_player(computer_white=False)
        move = g.reply(3600 + 1200, force_at=3600)
        if name == "stock":
            check(move is None, "control: on the stock ROM, Chessmaster crashes while thinking about the "
                  "recorded game's last position")
        else:
            check(move is not None and len(reorders) >= 1,
                  f"patched, it thinks for the full 3600 frames, Force Move gives {move}, and the routine "
                  f"put the right move first at {len(reorders)} iteration start(s)")
        g.stop()


def normal_play(stock, patched):
    print("normal play")
    labels = {}
    for name, rom in (("stock", stock), ("patched", patched)):
        g = Game(rom, level=0)
        g.menu("Settings")
        g.press("down")
        seen = []
        for _ in range(16):
            seen.append(g.line(6))
            g.press("a")
        labels[name] = seen
        g.stop()
    check(labels["stock"] == labels["patched"] and "Infinite" in " ".join(labels["patched"]),
          f"the Settings menu shows the same {len(labels['patched'])} levels, Infinite among them")
    moves = {}
    for name, rom in (("stock", stock), ("patched", patched)):
        g = Game(rom, level=1)
        g.one_player(computer_white=False)
        got = []
        for u in ("e2e4", "g1f3", "f1c4", "d2d3"):
            if g.board.is_game_over() or u not in [m.uci() for m in g.board.legal_moves]:
                break
            g.human(u)
            m = g.reply(3600)
            got.append(m.uci() if m else None)
        moves[name] = got
        g.stop()
    check(moves["stock"] == moves["patched"] and None not in moves["patched"],
          f"on a timed level the computer answers on its own, the same four moves as stock: {moves['patched']}")
    s, _ = session(stock, 300)
    p, _ = session(patched, 300)
    check(len(p) > 0 and p[-1][1] not in ("Actions", "Settings") and s[-1][1] not in ("Actions", "Settings"),
          "two-player entry, one-player handover and Force Move on Infinite work and close the menu")


def main():
    stock, patched = sys.argv[1], sys.argv[2]
    print(f"stock   {hashlib.md5(open(stock, 'rb').read()).hexdigest()}")
    print(f"patched {hashlib.md5(open(patched, 'rb').read()).hexdigest()}\n")
    tmp = tempfile.mkdtemp()
    footprint(stock, patched)
    filler_unused(stock, tmp)
    clock_tick(stock, patched)
    root_order(stock, patched)
    normal_play(stock, patched)
    print()
    if failures:
        for f in failures:
            print("FAIL:", f)
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
