# The Chessmaster: crash fix

A patch for The Chessmaster (Game Boy) that fixes two bugs that crash or freeze
the game while the computer is thinking. Both show up in long searches, such as
the Infinite level with Force Move.

- Game: The Chessmaster (USA) (Rev 1), 64 KB, MBC1
- Stock md5: `6b6d4a25d3c1e2890b22271c44e62dbf`
- Stock sha256: `0a44d1f127436d73fc2f64201da0e0fd40793a414e533bba0a08e02dfb51cb10`

| Patch | What it does | ROM md5 after patching |
|---|---|---|
| `Chessmaster-crashfix.ips` | Fixes the thinking clock that writes over the computer's search, and the root move order that sends the search into an illegal line. The ROM stays 64 KB, and the header is unchanged apart from the global checksum. | `56fccc534ecb8acde8c80a355066b841` |

## The bugs

**The thinking clock.** While the computer thinks after your move, the game
counts its thinking time twice a second, in the VBlank interrupt. The code adds
the side to move to the clock's address through a register pair and sets only
half of it. The other half, B, is whatever the interrupted search left there.
The search uses B as scratch for a few instructions at a time, and a tick that
lands then adds one to a byte 256 times B past the clock, in the middle of the
search's stored lines and scores. Most of those stray writes go unnoticed, some
change the move the computer plays, and some make it play a line it can't play:
it moves a piece that isn't there, its piece lists fill with squares, and the
game runs off into data. The screen fills with garbage, or the game locks up.

**The root move order.** The search keeps its root moves in a list, best first,
and stores the line it expects after each one. When a root move fails high, the
search makes that move its principal variation and searches it again. If the
second search doesn't beat the raised bound, the list is never reordered, so it
still starts with the previous best move. The next iteration searches the
principal variation first but files what it learns under the list's first
entry, so the old best move gets a line that belongs to another move. When that
move comes up, the search plays the line, and the game crashes the same way.
This one depends only on the position, so the same game crashes every time.

## What the patch changes

| Where | Stock | Patched |
|---|---|---|
| Thinking clock, bank 0 `$26EB` (14 bytes) | `ld a,($D02D)` `and $08` `jr z,+2` `ld a,$02` `ld c,a` `ld hl,$D585` `add hl,bc` | `ld a,($D02D)` `and $08` `jr nz,+0` `rrca` `rrca` `add a,$85` `ld l,a` `ld h,$D5` |
| Each search iteration, bank 2 `$41B7` | `call $41F7`, which loads the principal variation as the first line | `call fix_root_order`, which puts the variation's move first in the root list and then jumps to `$41F7` |
| Header `$014E`-`$014F` | global checksum | repaired |

The new clock code forms the address from A alone, so it reaches only the two
clocks at `$D585` and `$D587`. It takes the same cycles as the stock code on
both branches (60 and 64), so the game's timing is unchanged. It leaves B and
C as they were; the interrupt handler reads neither before it restores them.

`fix_root_order` (78 bytes) finds the root node whose move is the principal
variation's first move and moves it to the front of the list, shifting the
entries before it up one, as the search's own reorder does. When the two
already agree, which is almost always, it changes nothing, and it costs a few
hundred cycles once per iteration. It keeps every register but A and the flags,
which `$41F7` sets itself. It sits in bank 0 at `$0070`, in the run of unused
`$FF` and `$00` bytes between the interrupt vectors and the header
(`$006A`-`$00FF`), which the game never runs or reads.

## Applying it

Use any IPS patcher on an unmodified copy of the ROM, and save the result under
a new name. The patch only applies to the stock md5 above.

## Building it

Python 3 only:

```
python3 patch.py "Chessmaster, The (USA) (Rev 1).gb" -o "Chessmaster, The (USA) (Rev 1) [Crash fix patch by thisJUSTin816 v1.0].gb" --ips Chessmaster-crashfix.ips
```

`patch.py` refuses any ROM whose md5 it doesn't know, checks every byte it
replaces and that the space the routine goes into is unused, and rebuilds the
same IPS. The fixes are in `cmfix.asm`, assembled by
[`common/asm.py`](../common/asm.py).

## How it was tested

`python3 verify.py STOCK PATCHED` (needs `pip install pyboy pillow
python-chess`) plays both ROMs in PyBoy from a cold boot with ordinary button
input. All of it passes.

- **Footprint.** The patched ROM is exactly what `patch.py` builds, and the
  committed IPS turns stock into it when applied by a separate IPS reader. All
  89 bytes that differ from stock are the clock block, the routine, its call
  and the global checksum.
- **Filler.** Filling `$006A`-`$00FF` with an invalid opcode changes none of
  3614 frames of menus, move entry and thinking, nor the computer's reply. The
  control, breaking the VBlank vector, changes them.
- **The thinking clock.** With B forced to 2 at a tick, the stock game adds one
  to `$D785`, and the patched game advances its clock and leaves `$D785` alone.
  With B zero at every tick of 1800 frames of thinking, a build with only the new
  clock block matches stock in every frame's work RAM, so it does the same
  thing in the same cycles.
- **The root move order.** In a recorded 126-ply game, the stock game crashes
  while thinking about the last position on Infinite. The patched game thinks
  for the full 3600 frames, Force Move gives a legal move, and the routine has
  reordered the root list.
- **Normal play.** The Settings menu shows the same levels, a timed level
  answers four moves the same as stock, and two-player entry, handing a side to
  the computer and Force Move on Infinite all work.

The patch was also played against another engine in a match harness on
Infinite, with Force Move after 3600 frames a move. Three games that crashed or
froze on the stock ROM (two from the clock, one from the root order) complete
on the patched ROM, with the same moves as a stock run with the clock fixed
from outside. A 16-game match completed every game, with the same moves as
that run. Over its 834 computer moves, B was nonzero at 113 ticks, and every
tick of the patched clock wrote to one of the two clocks.

The emulator is not the cause. SameBoy 1.0.5, started from the same machine
state as PyBoy, runs the same search and crashes on the same frame.

Not tested on a console or flash cart.
