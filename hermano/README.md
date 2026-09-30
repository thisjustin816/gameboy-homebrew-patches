# Hermano: battery save patch

Adds a battery-backed save to the released *Hermano* ROM. The game saves
progress during play, and **B** on the title screen resumes from it.

Neither released cartridge has anywhere to save. Their headers declare `MBC5`
with **no RAM and no battery**:

| Header byte | Stock | Meaning          |
|-------------|-------|------------------|
| `$0147`     | `$19` | MBC5             |
| `$0149`     | `$00` | 0 bytes of SRAM  |

So the patch gives the cartridge a RAM chip first, then adds code that uses it.

## Supported releases

| Release | md5 | Payload | Patch |
|---------|-----|---------|-------|
| Hermano (original) | `89465cae204767aba57c342c67624bee` | 19 bytes | `Hermano-save.ips` |
| Hermano (ModRetro, SGB enhanced) | `631a7113e6fb5fd0c876a2f19030007c` | 16 bytes | `Hermano-ModRetro-save.ips` |

Both come from the same ZGB build and draw the same title screen, so the
injected code is identical. What differs is where the engine globals and the
progress block sit, and two stock entry points. All of that is in
`ROM_PROFILES` in `patch.py`, keyed by md5, and the payload offsets are derived
from each profile's progress block. Adding another release means recovering its
addresses and adding one profile, with no change to the assembly.

`patch.py` refuses a ROM it has no profile for.

## Using it

Bring your own copy of the ROM; none is distributed here.

```
python3 patch.py Hermano.gb -o Hermano-save.gb --ips Hermano-save.ips
```

`patch.py` needs only Python 3. It stops without writing anything if the input
is not a known ROM, if the region it writes into is not free padding, or if any
code it hooks does not match what it expects.

The `.ips` files are ordinary IPS patches for any patching tool. They hold
only the injected code and the header changes, no original game data.

### Controls

| Where         | Button   | Effect                                        |
|---------------|----------|-----------------------------------------------|
| Title screen  | **B**    | Resume from the last save                     |
| Title screen  | START    | Start a new game (unchanged)                  |
| Title screen  | SELECT   | Credits (unchanged)                           |

When a valid save exists, the title screen's bottom line alternates between the
stock `SELECT:CREDITS` and **`B:CONTINUE`**, in the same typeface, size and
position. With no save the line never changes and the screen is the stock
artwork.

Each message holds for 56 frames (about 0.9 s), with the line blank for 8
frames (about 0.13 s) between them. The gap makes the change read as two
messages taking turns, not one string glitching into another. A cross-fade
isn't possible: the DMG has a single background palette for the whole screen,
so fading this line would fade the whole title illustration with it.

### Finishing the game

Beating the final stage runs the ending cutscene (about 24 s), the credits
(about 80 s) and a closing screen, then returns to the title, about 113 seconds
in all. None of that is gameplay, and the save only happens in `StateGame`, so
the save still names the last stage played. `B:CONTINUE` comes back up and
resumes at the start of the final stage, so the ending can be replayed. Nothing
unlocks, and there is no new game plus.

### Game over

Spending the last continue clears the save. The next boot starts from stage
1-1, as the game did before it could save.

The game is built to feel like a cartridge-era platformer, and losing the run
when it is over keeps the stakes the original had. The continue count is part
of the saved block, so a resumed run has the continues it had left, not a fresh
three.

The continue screen itself does **not** clear the save; only leaving the run
does. There are two ways out of that screen, and both end the run.
`CONTINUE?` is not a button prompt: the boy walks to the `NO` or the `YES`
signpost. `YES` spends a continue and goes back into the stage. `NO` ends it:
the game zeroes the continue counter on its way to `StateGameOver`, so `NO`
spends every continue left, and the save with them, even with all three still
there.

So hooking `StateGameOver` catches the end of a run, by either road.

### Starting a new game over an existing save

START does **not** destroy the save at once. The save survives the title
screen, the tutorial page and the stage banner, and is overwritten on the first
frame of play in stage 1-1. That leaves about four seconds in which a reset
still keeps the old save.

There is no separate erase option.

## What gets saved, and when

The save happens during play whenever the run's identity changes:

- **finishing a stage**: the stage-complete routine increments `level`
  (`$C11C`);
- **reaching a new world**;
- **losing or gaining a life**.

It never saves a run whose lives are already at zero, and spending the last
continue clears the save, as above.

**Resuming always starts the saved stage from the beginning.** The game has
mid-stage checkpoints: `StateGame`'s START spawns the player at
`x_checkpoint`/`y_checkpoint` (`$C12F`/`$C131`), or at the stage's default
entry point when they are zero. Those four bytes are left out of the save.
`StateMenu`'s START has already zeroed them by the time a load runs, so the
restored run takes the stage's default entry point.

Otherwise the saved block is exactly the set of variables that `StateMenu`'s
START function sets for a new game. That set is, by construction, the complete
definition of a run: world, stage, lives, keys and bombs. Engine globals in the
same WRAM region, such as the music fade counter at `$C10F`, are excluded.

### SRAM layout

```
$A000  magic "HRMSV"          5 bytes
$A005  format version         2
$A006  payload length         19 (16 on the ModRetro release)
$A007  payload checksum       8-bit additive
$A008  payload                19 bytes (16)
```

A load is rejected unless the magic, version, length and checksum all agree,
so a blank or corrupted chip leaves the game untouched. Cartridge RAM stays
disabled except during the brief save and load, so a crash or a stray write
cannot damage the block.

A checksum only shows the block is intact, not that it names a stage the game
has, so the stored run is range-checked as well:

| Field | Max | Why |
|-------|-----|-----|
| world (`$C126`) | 6 | the ending fires when the world reaches 6 |
| stage (`$C11C`) | 2 | three stages per world |
| special stage (`$C118`) | 3 | its index is `19 + (n-1)` |
| underworld (`$C110`) | 7 | its index is `15 + (n-1)` |

`StateGame`'s START looks a stage up in a 22-entry table (bank `$1C`, `$7F8E`),
indexed by `world * 3 + stage` or by 15 or 19 plus one of the special-stage
selectors. Past the end of it the game loads garbage: world 7 exists as far as
the code is concerned and renders as corrupt tiles. No normal play reaches it,
since the ending triggers at world 6, but a save naming one is treated as no
save at all: no prompt, and B does nothing.

## How it hooks in

The patch overwrites **no original code or data**. On the original release its
whole footprint is:

| Range             | Size | What                                              |
|-------------------|------|---------------------------------------------------|
| `$0147`, `$0149`  | 2    | cartridge type MBC5+RAM+BATTERY, 8 KB of SRAM     |
| `$014D`-`$014F`   | 3    | recomputed header and global checksums            |
| `$3500`-`$371F`   | 544  | injected code and tiles, in what was `$FF` padding |
| `$6F25`, `$6F28`  | 2    | `startFuncs[StateMenu]` to `hook_menu_start`      |
| `$6F2D`, `$6F30`  | 2    | `updateFuncs[StateMenu]` to `hook_menu_update`    |
| `$6F50`, `$6F53`  | 2    | `startFuncs[StateGameOver]` to `hook_gameover_start` |
| `$6F6E`, `$6F71`  | 2    | `updateFuncs[StateGame]` to `hook_game_update`    |

ZGB's `InitStates` builds its state function tables in WRAM at run time.
Rewriting four of the pointer immediates sends individual state functions to
wrappers in bank 0, each of which calls the stock function first and then adds
its own behavior. Bank 0 is always mapped, so the wrappers are reachable
whatever the game has paged in, and the dispatcher has already paged in the
state's own bank, so the stock function is reachable with a plain call.

The tail of bank 0 (`$3489`-`$3FFF`) is `$FF` linker padding in the stock ROM,
and the code goes there. `patch.py` checks that it is still padding before
writing.

### Why the update dispatch, mostly

The obvious hook is ZGB's state START dispatch at `$0BCB`, one call site that
catches every state transition. It works, but at a cost: the START path runs
with the display off and ends in `DISPLAY_ON`, so adding anything there shifts
the raster phase. The game's `LCD_isr` toggles sprite visibility mid-frame to
hide sprites under the HUD window, and a shifted phase moves that toggle by a
scanline. Over a fixed 2432-frame input run, that showed up as a 1-4 scanline
difference on 12-13 frames. A bare `call`/`ret` there gives the same 12 frames,
so the cost comes from touching that path at all, not from the work done in it.

The update dispatch has no such problem: the update loop is synchronized to
VBlank, so the extra work is absorbed. The two hooks that matter during play
are there and cost nothing measurable.

`hook_menu_start` is the one exception. It needs the display-off window to
write VRAM, and it only runs when entering the title screen, under the fade-in.
Hooking that single slot, not the whole dispatch, brings the count down from
12-13 frames to **4**, each an isolated frame that resyncs on the next.
`verify.py` checks for exactly that, since a bare equality check would not tell
raster phase apart from a real change in behavior.

### Drawing the prompt

The title screen is a dense full-screen illustration. Measured tile column by
tile column, no row on it has room for another line of text, so the prompt
shares the line that reads `SELECT:CREDITS`, taking turns with it every 64
frames.

It is set in the game's own 3x5 proportional typeface, taken pixel for pixel
from those tiles: `C`, `E`, `T`, `I` and the colon are the game's letterforms,
and `B`, `O`, `N` and `U`, which the stock string lacks, are drawn to match.
Glyphs are 3 px wide on a 4 px pitch, beside the 1 px `:` and `I` the game
uses.

The stock letters drop a corner pixel wherever a stroke curves: `C` cuts its
two open corners, and `D` and `R` cut the corners on their round side. `B`
stays 3 px, since the stock `D` is built the same way and is 3 px. `O` and `U`
are 4 px, because cutting both corners of a 3 px row would leave a single
pixel, and `N` is 4 px so its diagonal has somewhere to go.

The stock line is in background tiles `$8C`-`$93` (row 15, columns 6-13), and
those are never modified. The prompt gets eight new tiles at `$89C0` (tile
`$9C` under the screen's signed BG addressing), at the start of 1600 bytes of
VRAM that is zero here and clear of every sprite tile the screen uses (those
stop at `$87FF`), plus a ninth holding only the line's background, for the
pause between messages. Switching is then eight tilemap bytes, so the original
art stays intact and switching back is exact.

The tile data is written by `hook_menu_start`, where `main()` holds the display
off for the whole state START path and `Start_StateMenu` never touches LCDC.
All 144 of those writes happen with the LCD off, so they need no timing care.
Only the tilemap changes per frame, and only while the title art is up: the
tutorial page reuses `StateMenu` and redraws the whole background, so it is
left alone.

### Writing the tilemap at the right moment

The eight tilemap cells have to change between two frames, never during one.
`hook_menu_update` runs at **LY 17-31**, in the middle of active display,
because the stock menu update and `SpriteManagerUpdate` run first. There the
PPU ignores VRAM writes while it fetches pixels. Since the hook runs at the
same point every frame, the *same* cells would be dropped every frame, leaving
a line stuck half `B:CONTINUE` and half `SELECT:CREDITS`.

So the write waits for `LY` to reach 144-150 and does all eight there, with
interrupts masked so a timer interrupt cannot stretch the burst past the end of
VBlank. The window stops at 150, not 153, because entering at 151 or later
leaves too little of VBlank for eight writes. With the LCD off the wait is
skipped: VRAM is free then, and `LY` would never advance.

Comparing rendered frames does not catch this, and PyBoy does not model the
restriction, so `verify.py` checks it directly by hooking the write and reading
`LY` and `LCDC`. On the patched ROM 0.2% of writes land outside a safe window,
all on frames around a screen transition, where the next frame corrects a
dropped write.

Telling whether the run has changed would normally take a byte of scratch RAM,
which has no safe place here. The hook compares against the copy in SRAM, so an
unchanged frame costs a handful of instructions and no write.

## Files

| File            | Purpose                                                |
|-----------------|--------------------------------------------------------|
| `patch.py`      | applies the patch; writes a ROM and optionally an IPS  |
| `savepatch.asm` | the injected code, commented                           |
| `asm.py`        | small LR35902 assembler (label resolution, two passes) |
| `verify.py`     | emulator test harness (needs `pyboy`, `pillow`)        |

```
python3 verify.py Hermano.gb Hermano-save.gb
```

It checks:

- rendering against the stock ROM;
- that progress reaches SRAM and survives a power cycle;
- that the prompt takes its turn only when a valid save is behind it;
- that a load does not bring back a mid-stage checkpoint;
- that blank, truncated and corrupted saves are all rejected.

## Testing

Tested under emulation (PyBoy) only, not on hardware. The header change is the
standard way to declare a save-capable MBC5 cartridge, so flash carts should
allocate and keep the save file as usual.
