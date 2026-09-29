# Bubble Bobble: last-round save

A patch for Bubble Bobble (Game Boy) that remembers the last round started and
offers its password on the PASSWORD screen.

- Game: Bubble Bobble (USA, Europe), 128 KB, MBC1
- Stock md5: `11c49d405eef2174d9c14682204bb458`

| Patch | What it does | ROM md5 after patching |
|---|---|---|
| `BubbleBobble-save.ips` | The save. The ROM stays 128 KB, and the header says MBC1+RAM+BATTERY with 8 KB of RAM. | `b093fd9aa903453c1b30703738159a49` |

The game has no screen tearing to fix. It writes the scroll registers from
HRAM copies at the start of its VBlank handler (`$0C6F`), before the picture
starts.

## Remembering the last round

Every time a round loads, its number and the flags the game's password
carries are written to battery-backed SRAM. When the PASSWORD screen opens,
the password for that round is already in the four slots, the slot marker is
past the last letter and the hand is on END, the way they are after typing it
and moving down to END. A accepts it, and the title reads ROUND n. START then
begins that round. BACK still clears letters to retype.

- The password is for the last round started, so it is there even if the
  console was switched off partway through the round.
- A new game loads round 1, which replaces the saved round. So does a round
  started from any password.
- With nothing saved, or SRAM the patch didn't write, the PASSWORD screen is
  the stock screen. The save is a signature, the round, the flags and a
  checksum.
- The password is made by the game's own encoder, the one that shows the
  password at game over, so it is one the stock game would give for that
  round.

The save needs a cartridge or flash cart that keeps 8 KB of battery RAM. The
save file is named after the ROM, so keep the two names in step to keep a save
across a re-patch.

## What the patch changes

| Where | Stock | Patched |
|---|---|---|
| Round loader `$1848` | `ld hl,$DC80` | `call save_round`, which saves the round and returns with HL = `$DC80` |
| PASSWORD screen setup, bank 3 `$7104` | `ld (SLOT),a` | `call pf_init`, which does that store, then reads the save and runs the encoder |
| PASSWORD screen, every frame, bank 3 `$7129` | `ld a,(PW_FLAGS)` | `call pf_step`, which on the first frame fills the entry and returns that load |
| Header `$0147`, `$0149` | MBC1, no RAM | MBC1+RAM+BATTERY, 8 KB |

Every round start goes through the round loader: a new game, a password, a
round cleared, the boss rounds, and the skips ahead several rounds at once
(`$3330`), which call it once for each round they skip.

`save_round` and the SRAM switches (52 bytes) sit in bank 0, in the run of
`$FF` bytes between the interrupt vectors and the header (`$0061` to `$00FF`),
which the game never runs or reads. `pf_init` and `pf_step` (146 bytes) sit in
bank 3 at `$7800`, in the unused `$FF` run after the password code. Bank 3 is
always mapped when the PASSWORD screen runs. `pf_init` runs the encoder from
there, and the screen's setup then clears the entry, so `pf_step` fills it on
the next frame and queues the four letters through the game's own slot drawing
routine (`$7391`). It also copies the hand's grid column to `$C912`, as the
game does when the hand leaves the grid, so UP from END goes back to the
column it would after typing. `$D780` holds the one flag between the two
routines. The game never uses that part of WRAM, and the boot clears it. The
SRAM is enabled only while `save_round` and `pf_init` use it.

## Applying it

Use any IPS patcher on an unmodified copy of the ROM, and save the result under
a new name. The patch only applies to the stock md5 above.

## Building it

Python 3 only:

```
python3 patch.py "Bubble Bobble (USA, Europe).gb" -o "Bubble Bobble (USA, Europe) [save].gb" --ips BubbleBobble-save.ips
```

`patch.py` refuses any ROM whose md5 it doesn't know, checks every byte it
replaces and that the space the code goes into is unused, and rebuilds the
same IPS. The save is `bb1save.asm`, assembled by `asm.py`.

## How it was tested

`python3 verify.py STOCK PATCHED` (needs `pip install stable-retro pyboy
pillow`). The game crashes in PyBoy as soon as a round starts, the stock ROM
too: it jumps into cartridge RAM after "GO!". So every check that plays the
game runs in Gambatte, through stable-retro, from a cold boot. PyBoy runs only
the routine checks, from the title screen. All of it passes.

- **Footprint.** The patched ROM is exactly what `patch.py` builds, and the IPS
  turns stock into it when applied by a separate IPS reader. Of the 212 bytes
  that differ from stock, all are the patch's code, its three hooks, the two
  cartridge bytes in the header and the checksums.
- **Filler.** Filling both places the code goes with zeros changes none of
  6300 frames of password entry and play. The control, breaking the VBlank
  vector, changes all of them. The stock game leaves `$D780` at 0 through three
  seeded runs of play, and nothing in the ROM names an address near it.
- **Routines.** In PyBoy, each routine runs on its own. `save_round` writes the
  right five bytes, returns HL = `$DC80` and keeps every other register and
  flag. `pf_init` runs the encoder with a good save and does nothing with a bad
  checksum. `pf_step` fills the entry once and otherwise changes nothing. Both
  return the A the instruction they replace would, keep B, C, D, E and HL, and
  leave the SRAM disabled.
- **No usable save is stock.** A fresh cartridge, SRAM full of `$FF`, random
  SRAM, a bad checksum, a bad signature and a round past 100 all open the
  PASSWORD screen empty. Every frame and the screen's state match stock's, and
  so does typing on it.
- **Saving.** A new game saves round 1, `b0 b1 00 00 a5`, and its first 1500
  frames match stock's. Seeded play that clears each round (by setting the
  game's count of enemies left, `$FFC3`, to 0) keeps the save on the round
  being played, and all 8100 frames match stock's.
- **Round trip.** KLL1 typed on the patched game starts round 3 and saves it.
  After a power cycle KLL1 is on the PASSWORD screen, and A takes the game to
  round 3.
- **Looks typed.** For the known passwords VGL1, VLT1 and KLL1 and seven more
  rounds with a mix of flags, including boss rounds 25 and 100, the pre-filled
  letters are ones the stock game accepts for the same round and flags. The
  screen's state, the hand, the slot marker and four ways of moving off END
  match typing the letters on the stock game. So does every frame of the
  cursor's blink, except Bub under END: after typing he has walked there, so
  his idle animation is at another point in its cycle. The control, a build
  that doesn't copy the hand's grid column, looks the same, but UP from END
  moves the hand somewhere else.

Not tested on a console or flash cart. The header change, an MBC1 cartridge
with battery RAM, is the part most worth trying on hardware.
