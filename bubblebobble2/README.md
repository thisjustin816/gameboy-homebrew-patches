# Bubble Bobble Part 2: tearing fix and last-stage save

A patch for Bubble Bobble Part 2 (Game Boy) that stops the screen from tearing
while the camera scrolls, and remembers the last stage started, offering its
password on the PASSWORD screen.

- Game: Bubble Bobble Part 2 (USA, Europe), 128 KB, MBC1
- Stock md5: `8bbb9ba0d72548706e4e5eba1b3a9fe1`

| Patch | What it does | ROM md5 after patching |
|---|---|---|
| `BubbleBobble2-tearfix-save.ips` | The tearing fix and the save. The ROM grows to 256 KB and the header says MBC1+RAM+BATTERY with 8 KB of RAM. | `f2ef3b62b6859cc89bbb8494bb4057b2` |

## What was wrong

The game runs its logic right after each VBlank and writes the scroll
registers (SCX, SCY) whenever the logic reaches them. That is usually 40 to 85
lines into the picture. The lines above the write are drawn with the old
scroll and the rest with the new one, so the picture steps by a pixel or two
across the screen whenever the camera moves. In the run below, frame 350 of a
seeded playthrough, SCY changes from 128 to 127 on line 66.

Stock scroll changes that landed on a visible line, over 3000 frames of seeded
random play from the start of level 1:

| Seed | Stock | Patched |
|---|---|---|
| 1 | 49 | 1 |
| 2 | 362 | 0 |
| 3 | 58 | 1 |

The one or two left on the patched side are a one-time reset of the scroll to
0,0 when the game changes state. It lands on a single early line of one frame.
The patch leaves it alone (see below).

## What the patch changes

Every per-frame scroll write now waits for VBlank. The new value goes into a
spare HRAM byte with a pending bit, and the VBlank handler copies it to the
hardware just before its sprite DMA, so a whole frame is drawn with one scroll.
A scroll change shows up one frame later than it did on the bottom half of
stock's torn frame.

| Where | Stock | Patched |
|---|---|---|
| Camera scroll copy (bank 1 `$4129`), every frame | writes SCX and SCY | stores both as pending |
| Scroll-home state `$15D0` (`$1639`, `$1648`) | writes SCY and SCX | `RST $08` and `RST $10` store them as pending |
| Scroll states at `$0B62`, `$0BC8`, `$0BD4` | writes SCY and SCX | the same |
| VBlank handler `$023F` | calls the OAM DMA | applies pending scroll, then runs the DMA |
| Boot `$0156` | calls the WRAM clear | clears the pending bits, then runs the WRAM clear |

While the LCD is off there is no VBlank to wait for, so a write goes straight
to the hardware and cancels any pending value for that axis.

The code sits in bank 0 in the two RST vectors and the run of junk bytes
between the joypad vector and the header (`$0068` to `$00FF`). The game never
runs or reads either. It borrows HRAM `$FFA2` to `$FFA4`, which the game never
touches. HRAM is random at power-on on a console, so the boot clears the flag
byte first.

The one-time scroll resets at state changes (`$2BB6`, `$29D5`, `$2AF0`,
`$18BEB` and others) and the scroll-rounding writes (`$15D4`, `$0A6A`) are left
as stock. Some of them read the register back in the same frame, so deferring
them would change behavior.

## Remembering the last stage

Every time a stage loads, the game's password for that stage is written to
battery-backed SRAM. When the PASSWORD screen opens, those four symbols are
already in the slots, drawn the way the game draws typed ones. START accepts
them, the title reads START ROUND n, and START again begins that stage. Any
slot can still be retyped first with A.

- The password is for the last stage started, so it is there even if the
  console was switched off partway through the stage.
- Starting a new game loads stage 1, which replaces the saved stage.
- With nothing saved, or SRAM the patch didn't write, the PASSWORD screen is
  the stock screen. The save is a signature, the four symbols and a checksum.
- The START and PASSWORD menu and the stock password entry are unchanged. The
  password itself is built by the game's own encoder, so the symbols are ones
  the stock game would show for that stage.

The save needs a cartridge or flash cart that keeps 8 KB of battery RAM. The
save file is named after the ROM, so keep the two names in step to keep a save
across a re-patch.

How it works: the game's encoder (bank 6 `$7EDC`) is copied unchanged to the
start of a new bank 8, followed by three new routines. `save_stage` runs from a
hook in the stage-load routine (`$09D7`). `pf_begin` runs when the PASSWORD
screen finishes setting up (`$35E3`), copies the saved symbols into the game's
entry buffer at `$CE6C` and moves the cursor to where it sits after four
symbols. `pf_step` runs each frame of the entry handler (`$35E7`) and draws one
symbol per frame through the game's own VBlank tile queue. Small trampolines in
the junk bytes of the RST `$18` to `$30` vectors, and after the tearing fix's
code, switch to bank 8 the way the game does (`$CE73` always names the mapped
bank). The SRAM is enabled only while `save_stage` and `pf_begin` use it.

## Applying it

Use any IPS patcher on an unmodified copy of the ROM, and save the result under
a new name. The patch only applies to the stock md5 above.

## Building it

Python 3 only:

```
python3 patch.py "Bubble Bobble Part 2 (USA, Europe).gb" -o "Bubble Bobble Part 2 (USA, Europe) [tearfix, save].gb" --ips BubbleBobble2-tearfix-save.ips
```

`patch.py` refuses any ROM whose md5 it doesn't know, checks every byte it
replaces, confirms nothing else jumps into the retired scroll routine, and
rebuilds the same IPS. The tearing fix is `bb2scroll.asm` and the save is
`bb2save.asm`, both assembled by `asm.py`.

## How it was tested

`python3 verify.py STOCK PATCHED` (needs `pip install pyboy pillow`) runs both
ROMs in PyBoy headless, from a cold boot or from one saved state at the start
of level 1. All of it passes.

- **Footprint.** The patched ROM is exactly what `patch.py` builds, and the IPS
  turns stock into it when applied by a separate IPS reader. It differs from
  stock only at the patch's own bytes. The header changes only in
  its three cartridge bytes and both checksums, and the new banks are `$FF`
  apart from the patch's code.
- **Filler.** Filling the RST vectors and the junk area with `$FF` changes
  nothing over 1500 frames of play. The control, filling the VBlank vector,
  does change the frames. The stock game never writes `$FFA2` to `$FFA4`.
- **Routines.** Each routine runs on its own with a known register and flag
  pattern. `RST $08`, `RST $10` and the scroll copy (LCD on and off) store or
  write the right values, and hand back every register and flag and the stack
  unchanged; the scroll copy returns A as the SCY shadow, as the original did.
  The VBlank copy is checked for all four combinations of pending bits.
- **Tearing.** Stock changes the scroll on a visible line 49, 362 and 58 times
  over three seeds. The patched ROM does it 1, 0 and 1 times, all from the
  one-time resets.
- **Transitions.** The five states above were forced by setting the game's
  state pointer in seven scenarios. In each, stock and patched walk through the
  same states and the same scroll values every frame. Stock tears 56 to 116
  times per 100 frames and the patched ROM never does.
- **Everything else is stock.** From the same starting state, the game's memory
  (outside the stack page) and its sprites are identical at each VBlank for the
  first 681 to 1300 frames on four seeds. Over those frames, every picture
  that differs is on or next to a frame stock tore. A control patch that never
  applies the scroll differs from stock on 90 other frames.
- **No stale overwrite.** Over 18000 frames, none of the direct scroll writes
  left in place ran while a deferred value was pending, which would have let
  VBlank overwrite it with an old value.
- **Power-on.** With `$FF` in the borrowed HRAM bytes when the game starts,
  the patched title never leaves scroll 0,0. Without the boot clear, one frame
  gets 255,255.

The save checks:

- **No usable save is stock.** A fresh cartridge, SRAM full of `$FF`, random
  SRAM, and a valid signature with a bad checksum all open the PASSWORD screen
  empty, and every frame matches stock's, with random HRAM at power-on.
- **Saving.** A new game writes stage 1's password, `b0 b2 04 08 0a 24 9f`,
  which matches a hand-worked encoder. The game leaves the SRAM disabled, and
  the emulator writes an 8 KB battery file.
- **Round trip.** A password for world 2, stage 19 typed into the game starts
  stage 39, and that stage's password is saved. After a power cycle it is in
  the PASSWORD screen's buffer, and START on that screen continues from stage
  39.
- **Looks typed.** After a power cycle the buffer, the four tiles and every
  frame over the cursor's blink cycle match typing the same symbols by hand on
  the stock game. The control, a build that draws slot 0 at `$9880` instead of
  `$9886`, fills the buffer but puts the symbols in the wrong place. Pressing
  A retypes the last slot and leaves the others.
- **The copied encoder.** The game's own encoder, the copy in bank 8 and a
  hand-worked one agree on 40 random worlds, stages and extra bits.
- **Routines.** `pf_begin`, `pf_step` (drawing slot 0, drawing slot 3, waiting
  on a busy tile queue, nothing to draw) and `save_stage` each run on their own
  and keep every register, flag and the stack. `far8` and the stage-load
  trampoline put the mapped bank and `$CE73` back.

Runs drift apart after roughly 700 to 1500 frames in busy scenes. The patch
adds a few dozen cycles to a frame, so a logic pass that ended just inside a
frame can end just outside it, or the other way around. From then on the two
ROMs are a frame out of step. Stock already drops frames in busy scenes
(the logic runs long on about 0.3 to 6.6 percent of frames in the seeded runs),
and the count is the same with the patch on the runs that stay in step.

Not tested on a console or flash cart. The header change, an
MBC1 cartridge with battery RAM, is the part most worth trying on hardware.
