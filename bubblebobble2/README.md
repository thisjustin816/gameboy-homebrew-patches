# Bubble Bobble Part 2: tearing fix

A patch for Bubble Bobble Part 2 (Game Boy) that stops the screen from tearing
while the camera scrolls.

- Game: Bubble Bobble Part 2 (USA, Europe), 128 KB, MBC1
- Stock md5: `8bbb9ba0d72548706e4e5eba1b3a9fe1`
- Patch: `BubbleBobble2-tearfix.ips`, which gives a ROM with md5 `3e09810f16fe0f962109fff0863a3bd4`
- The patch edits the ROM header's global checksum bytes and nothing else in
  the header.

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

## Applying it

Use any IPS patcher on an unmodified copy of the ROM, and save the result under
a new name. The patch only applies to the md5 above.

## Building it

Python 3 only:

```
python3 patch.py "Bubble Bobble Part 2 (USA, Europe).gb" -o "Bubble Bobble Part 2 (USA, Europe) [tearfix].gb" --ips BubbleBobble2-tearfix.ips
```

`patch.py` refuses any ROM whose md5 it doesn't know, checks every byte it
replaces, confirms nothing else jumps into the retired scroll routine, and
rebuilds the same IPS. The source is `bb2scroll.asm`, assembled by `asm.py`.

## How it was tested

`python3 verify.py STOCK PATCHED` (needs `pip install pyboy pillow`) runs both
ROMs in PyBoy headless, from a cold boot or from one saved state at the start
of level 1. All of it passes.

- **Footprint.** The patched ROM is exactly what `patch.py` builds. It differs
  from stock only at the patch's own bytes, and the header is intact.
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

Runs drift apart after roughly 700 to 1500 frames in busy scenes. The patch
adds a few dozen cycles to a frame, so a logic pass that ended just inside a
frame can end just outside it, or the other way around. From then on the two
ROMs are a frame out of step. Stock already drops frames in busy scenes
(the logic runs long on about 0.3 to 6.6 percent of frames in the seeded runs),
and the count is the same with the patch on the runs that stay in step.

Not tested on a console or flash cart.
