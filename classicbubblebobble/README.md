# Classic Bubble Bobble: Master System physics and last-round save

A patch for Classic Bubble Bobble (Game Boy Color) that makes Bub jump, fall and
shoot like he does in the Master System version, and remembers the last round
started, offering its password on the PASSWORD screen.

- Game: Classic Bubble Bobble (USA), 1 MB, MBC5
- Stock md5: `4bc8467ed91a94ba23648706b551cef5`

| Patch | What it does | ROM md5 after patching |
|---|---|---|
| `ClassicBubbleBobble-physics-save.ips` | The physics and the save. The ROM stays 1 MB, and the header says MBC5+RAM+BATTERY with 8 KB of RAM. | `57bbb625a0a6e3cd50d48d85d89e2392` |

## What was wrong

Stock Classic's jump rises slowly and almost evenly, barely moves sideways,
and hangs in the air: a jump takes 65 frames against the Master System's 48.
Walking off a ledge falls at under half the Master System's speed while
drifting twice as far. All numbers below are pixels per frame, measured in an
emulator.

| | Stock Classic | Master System | Patched |
|---|---|---|---|
| Jump height | 40 px | 42 px | 42 px |
| Frames at the top | 6 | 10 | 10 |
| Whole jump | 65 frames | about 48 | 49 |
| Jump locked to one side: holding that way / letting go / pushing back | 0.5 / 0.5 / 0.5 | 1.1 / 0.9 / 0.4 | 1.125 / 0.94 / 0.375 |
| Steering a jump straight up | 0.5, only near the top | 0.33, the whole jump | 0.31, the whole jump |
| Walking off a ledge: fall / drift | 0.5 / 1.0 | 1.25 / 0.5 | 1.25 / 0.5 |
| Walking | 1.0 | 1.0 | 1.0, as stock |
| Bubble shot speed | 1.5 | 3 | 3 |
| Bubble shot reach | 40 px | about 71 px | 40 px, as stock |
| Shortest time between shots | 28 frames | 22 frames | 28 frames, as stock |

A jump locked to one side never turns around, on the Master System or here.
The shoes still add a pixel a tick to walking.

The shot now snaps out at the Master System's speed but stops where stock's
does, and Bub fires no more often than stock. Classic's rounds are more
cramped than the Master System's (a shot has a wall within 5 tiles from 39%
of the places Bub can stand, against 19% in the Master System's round 1), and
its enemies walk and fall at about half the Master System's speed, so the
Master System's longer reach would make it an easier game rather than a
closer one. With the longer-range item a shot still goes as far as stock's,
70 px, in half the time.

Everything else about bubbles and enemies is stock, because the levels are
built around it: bubbles float at 0.25 px a frame (the Master System's 0.5),
last about 35 seconds (13), pass up through the ceiling and come back from
the floor (the Master System's wait at the ceiling), and pop after 32 px of
pushing. Enemies walk and fall at 0.5 px a frame (0.8 and 1.0). Bouncing on a
bubble already works as on the Master System: only with jump held, and now a
full 42 px jump.

### The jump height

Classic's levels, like the Master System's, put the ledges that one jump
should reach 5 tiles (40 px) apart. In the maps of 177 of the game's 180
rounds (the three routes' round 38 didn't read as a level), 5 tiles is the
most common gap up to the next ledge, and 132 rounds have ledges that can't be
reached without 5-tile jumps. There are also 6-tile gaps, and in 18
rounds a jump that reached 6 tiles would open paths the levels keep closed.

Classic only lands Bub on a ledge if the jump got him at least level with its
top, so anything from 40 to 47 px reaches the same ledges. The Master System's
jump rises 42 px and waits at the top for 10 frames, 2 px above standing
height on the next ledge. The patch does the same, where stock reached the
ledge's height exactly and left no margin.

## Remembering the last round

Every time a round loads, its route and round are written to battery-backed
SRAM. When the PASSWORD screen opens, that round's password is already in the
four slots with the cursor on END, the way the screen looks after typing the
fourth letter. A starts that round. BACK still clears letters to retype, and
EXIT goes back to the title.

- The password is for the last round started, so it is there even if the
  console was switched off partway through the round.
- A new game replaces the saved round with round 1. So does a round started
  from any password, and taking a door to another route saves that route.
- With nothing saved, or SRAM the patch didn't write, the PASSWORD screen is
  the stock screen. The save is a signature, the route, the round and a
  checksum.
- The password is made by the game's own encoder, so it is the one the stock
  game uses for that round.

The save needs a cartridge or flash cart that keeps 8 KB of battery RAM. The
save file is named after the ROM, so keep the two names in step to keep a save
across a re-patch.

## What the patch changes

| Where | Stock | Patched |
|---|---|---|
| Jump table pointer, bank 2 `$4AA8` | the stock 33-step table | the new 45-step table |
| Jump starts, bank 2 `$4A4B`, `$542A`, `$5657` | 33 steps | 45 steps |
| Sideways movement and gravity, bank 2 `$4AEF` to `$4BD2` | stock movement | `jp move`, which rejoins the stock landing check at `$4BD3` |
| Shot start and speed, bank 2 `$4C7E` to `$4C96` | 1 px ahead, 3 px a tick | 4 px ahead, 6 px a tick |
| Shot length, bank 2 `$5B29` to `$5B45` | a bubble after 14 ticks (24 with the item) | after 7 (12), sprite frames at half the counts |
| Fire check, bank 2 `$4C4C` | fires once the last shot is a bubble | `call fire_gate`, which also waits out a 14-tick cooldown |
| Round load, bank 1 `$419B` | `ld a,($C04F)` | `call save_round`, which saves the round and returns that load |
| PASSWORD screen setup, bank `$3C` `$4036` | `ld ($D683),a` | `call pf_init`, which does that store, then reads the save and runs the encoder |
| PASSWORD screen, every frame, bank `$3C` `$4196` | `ld a,($D683)` | `call pf_step`, which draws the letters once and returns that load |
| Header `$0147`, `$0149` | MBC5, no RAM | MBC5+RAM+BATTERY, 8 KB |

The game moves Bub once every two frames. `move` (bank 2 `$7E2D`) replaces
the stock sideways movement and falling. Fractions of a pixel come from an
8-tick pattern that decides which ticks get the extra pixel. The jump itself
is a table of Y steps that the game already walks through, now easing out at
the top and falling faster after it. `patch.py` checks that nothing else in
the ROM jumps into the retired code. The landing check is stock, and so are
the bubble and enemy bounces, which start the same table.

The shot starts where stock's is after its first tick and moves 6 px a tick,
so it passes through every other one of stock's positions and stops at the
same place. Bub can only fire while the shot's slot is free, and the shorter
shot frees it sooner, so `fire_gate` adds a cooldown of stock's 14 ticks. The
game's hit test for a shot is 14 px wide, so a 6 px step can't jump past an
enemy.

The physics code and table (294 bytes) sit in the zero padding at the end of
bank 2, and the save routines (200 bytes) in the zero padding at the end of
bank 0. The game never runs or reads either. `$CEC0` counts ticks for the
fractions, `$CEC2` is the shot cooldown, and `$CEC1` holds the one flag
between the two PASSWORD routines. The game never names or touches any of
them, and `pf_init` clears the flag
when there is no save, because WRAM is random at power-on on a console.

`pf_init` runs with interrupts off during the screen's setup, and puts the
live round back after running the encoder on the saved one. `pf_step` queues
the four letters through the game's own VBlank copy queue (`$0BF5`), the way
typing one does. The SRAM is enabled only while `save_round` and `pf_init`
use it.

## Applying it

Use any IPS patcher on an unmodified copy of the ROM, and save the result under
a new name. The patch only applies to the stock md5 above.

## Building it

Python 3 only:

```
python3 patch.py "Classic Bubble Bobble (USA).gbc" -o "Classic Bubble Bobble (USA) [physics, save].gbc" --ips ClassicBubbleBobble-physics-save.ips
```

`patch.py` refuses any ROM whose md5 it doesn't know, checks every byte it
replaces and that the padding it uses is empty, and rebuilds the same IPS. The
physics are `cbbphysics.asm` and the save is `cbbsave.asm`, both assembled by
`asm.py`.

## How it was tested

`python3 verify.py STOCK PATCHED` (needs `pip install pyboy pillow`) runs both
ROMs in PyBoy from a cold boot. Rounds past round 1 start the way the game
starts any round, with the round number set as the round loader reads it. All
of it passes.

- **Footprint.** The patched ROM is exactly what `patch.py` builds, and the IPS
  turns stock into it when applied by a separate IPS reader. All 514 bytes that
  differ from stock are the patch's code and table, its hooks, the shot's constants, the two
  cartridge bytes in the header and the checksums.
- **Filler.** Filling both paddings with `$FF` changes none of 2490 frames of
  password entry and play. The control, breaking the VBlank vector, changes all
  of them. The stock game never changes `$CEC0`, `$CEC1` or `$CEC2`, whether
  they start at 0 or at `$FF`.
- **Physics.** From round 1, the numbers in the table above: height, time at
  the top and length of a jump, the three speeds of a locked jump, steering,
  walking off a ledge, and walking. Both stock and patched catch the ledge 5
  tiles above the start, and neither catches the platform 6 tiles up.
- **The shot.** It stops 40 px right and 41 px left of Bub, as stock's does,
  in 13 frames against stock's 27, and 70 px with the longer-range item, in
  23 frames against 47. A second shot fires 28 frames after the first at the
  soonest, as on stock. Seeded play traps at least as many enemies as stock does (20 against 15).
- **Landing.** Over 6808 frames standing in seeded play on rounds 5 to 60, Bub
  always stands on the tile grid, and bubble and enemy bounces still start
  jumps. In DMG mode round 1 starts and a jump reaches the ledge above.
- **Routines.** `save_round`, `pf_init` (good and bad save) and `pf_step`
  (pending or not) each run on their own. They write what they should, return
  the A the instruction they replace would, keep B, C, D, E and HL, and leave
  the SRAM disabled. `pf_init` puts the live round back after the encoder.
- **No usable save is stock.** A fresh cartridge, SRAM full of `$FF`, random
  SRAM, a bad checksum, a bad signature, a route or round past the last, and
  `$FF` in the flag at power-on all open the PASSWORD screen empty, and it and
  typing on it look the same as stock.
- **Saving.** A new game saves route 1, round 1, and clearing the round saves
  round 2. Taking round 1's door saves the second route's round 2. Rounds are
  cleared by seeded play with Bub unable to be hit. The emulator writes an
  8 KB battery file.
- **Round trip.** GFBC typed on the patched game starts round 20 and saves it.
  After a power cycle GFBC is on the PASSWORD screen with the cursor on END,
  looking as it does typed on the stock game over the cursor's blink, and A
  starts round 20. The control, a build that draws the letters one tile to the
  left, fills the entry the same but looks different. EXIT from the pre-filled
  screen and then START begins round 1 and saves it.
- **Known passwords.** For BBBB, GGBB, MBMB, GFBC, TRCC, NCDK, HFCC and SBFP,
  rounds 1 to 60, the pre-filled screen shows the password and looks as it does
  typed on the stock game. For six random route and round pairs, the
  pre-filled letters and what A does match typing them on the stock game. Some
  pairs aren't rounds the game can reach, and the game turns those passwords
  down either way. The save only holds rounds the game started.

Not tested on a console or flash cart beyond the physics, which were tried on
hardware while they were tuned. The header change, an MBC5 cartridge with
battery RAM, is the part of the save most worth trying.
