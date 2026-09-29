# Classic Bubble Bobble: Master System physics and last-round save

A patch for Classic Bubble Bobble (Game Boy Color) that makes Bub jump, fall and
shoot like he does in the Master System version, and remembers the last round
started, offering its password on the PASSWORD screen.

- Game: Classic Bubble Bobble (USA), 1 MB, MBC5
- Stock md5: `4bc8467ed91a94ba23648706b551cef5`

| Patch | What it does | ROM md5 after patching |
|---|---|---|
| `ClassicBubbleBobble-physics-save.ips` | The physics and the save. The ROM stays 1 MB, and the header says MBC5+RAM+BATTERY with 8 KB of RAM. | `2c4c0b9cc0c106051fb195e4ed3365d9` |

## What was wrong

Stock Classic's jump rises slowly and almost evenly, barely moves sideways,
and hangs in the air: a jump is off the ground for 62 frames against the
Master System's 48. Walking off a ledge falls at under half the Master
System's speed while drifting twice as far. All numbers below are pixels per
frame, measured in an emulator.

| | Stock Classic | Master System | Patched |
|---|---|---|---|
| Jump height | 40 px | 42 px | 42 px |
| Frames within 0 / 1 / 2 / 4 px of the top | 6 / 10 / 10 / 14 | 10 / 12 / 14 / 18 | 10 / 12 / 14 / 18 |
| Frames off the ground | 62 | 48 | 48 |
| Frames from the button to leaving the ground | 2 or 3 | 0 | 0 or 1 |
| Falling once below where a jump started | 0.5 | 1.25 | 1.25 |
| Jump locked to one side: holding that way / letting go / pushing back | 0.5 / 0.5 / 0.5 | 1.1 / 0.75 / 0.4 | 1.125 / 0.75 / 0.375 |
| Steering a jump straight up | 0.5, only near the top | 0.33, the whole jump | 0.31, the whole jump |
| Walking off a ledge: fall / drift | 0.5 / 1.0 | 1.25 / 0.5 | 1.25 / 0.5 |
| Walking | 1.0 | 1.0 | 1.0, as stock |
| Landing on a bubble: span that bounces | 13 px | 23 px | 23 px |
| Landing on a bubble: how far into Bub's feet it can be and still bounce him | 16 px, at any point in a jump and standing | 7 px, from 5 frames before the end of the top on and falling; not before, not standing | the same, from 4 frames before the end of the top |
| Bubble shot speed | 1.5 | 3 | 3 |
| Bubble shot reach | 40 px | about 71 px | 40 px, as stock |
| Shortest time between shots | 28 frames | 22 frames | 22 frames |

A jump locked to one side never turns around, on the Master System or here.
The shoes still add a pixel a tick to walking. The jump follows the Master
System's own arc, read every other frame, so it spends the same time near the
top. Once it is back at the height it started from, a jump off a ledge falls
at the ordinary rate, as the Master System's does.

A bounce on a bubble works the same in both: only with jump held, a full
jump, locked to whichever way is held at the bounce, or straight up if
neither is. What differed was how close Bub had to be, and how quickly he
turned around: Classic took him as landing on a bubble only within 6 px of
its middle where the Master System takes about 11, and it started the bounce
but left Bub sinking into the bubble for one more tick. The Master System's
Bub turns upwards straight away, and now Classic's does too. Only a landing
bounces: jumping up into a bubble doesn't, even with jump held, because
Classic's test counts Bub as on top of a bubble once he is level with it, and
with the faster rise and the wider test he would otherwise bounce on the way
up and gain a second jump. A bubble jumped into from below pops, as on the
Master System, or is pushed aside as on stock if Bub hits it off-centre.

How deep Bub is in the bubble also matters on the Master System, and stock
Classic ignored it. Stock bounces him off any bubble whose top is anywhere
from his feet to his head, at any point in a jump and even standing, as long
as jump is held. The Master System goes by where he is in the jump:

- Rising, in the first half of the time at the top, and standing: a bubble
  he is in pops, and one only 1-2 px into his feet is left alone, so in a
  jump it bounces him once the next phase starts.
- From 5 frames before the end of the top, falling, and walking off a ledge:
  a bubble up to 5 px into his feet bounces him. At 6-7 px it bounces him and
  he pops it rising back through it. Deeper, it pops.

The patch does the same. Classic moves Bub every other frame, so its phase
starts 4 frames before the end of the top, the nearest tick to the Master
System's 5. A landing always meets the top 7 px of a bubble first, even at
Classic's 6 px a tick, so landings bounce as before. What changes is a bubble
that drifts or rises into Bub: deep inside it pops instead of bouncing him.

Stock Classic also wasted a tick at take-off. The tick that sees the button
starts the jump but skips its first step, so Bub left the ground 2 or 3
frames after the press. The patch takes the first step on that tick, and a
jump now leaves 0 or 1 frames after the press, depending on whether the game
reads the buttons on that frame or the next.

What's left comes from the game running its logic at 30 frames a second,
which there isn't the CPU time to double: Bub moves in steps two frames
apart, and the buttons are read every other frame.

The shot now snaps out at the Master System's speed but stops where stock's
does. Bub can fire every 22 frames, as on the Master System, where stock
waits 28. Classic's rounds are more cramped than the Master System's (a shot
has a wall within 5 tiles from 39% of the places Bub can stand, against 19% in
the Master System's round 1), and its enemies walk and fall at about half the
Master System's speed, so the Master System's longer reach would make it an
easier game rather than a closer one. With the longer-range item a shot
still goes as far as stock's, 70 px, in half the time.

Everything else about bubbles and enemies is stock, because the levels are
built around it: bubbles float at 0.25 px a frame (the Master System's 0.5),
last about 35 seconds (13), pass up through the ceiling and come back from
the floor (the Master System's wait at the ceiling), and pop after 32 px of
pushing. Enemies walk and fall at 0.5 px a frame (0.8 and 1.0).

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
| Jump table pointer, bank 2 `$4AA8` | the stock 33-step table | the new 26-step table |
| Jump start, bank 2 `$4A4B` | 33 steps | 26 steps |
| Take-off, bank 2 `$4A64`, `$4A6B`, `$4A7A` | skips the jump's first step | goes through it |
| Bounces, bank 2 `$542A`, `$5657` | start a 33-step jump | `call bounce_start`, which starts the 26-step jump with its first step taken |
| Bounce tests, bank 2 `$5421`, `$564E` | bounce if jump is held, else pop | `jp bg_bubble`, `jp bg_enemy`: the Master System's rule by depth and phase, which can also leave the bubble, or bounce and pop it |
| Sideways movement and gravity, bank 2 `$4AEF` to `$4BD2` | stock movement | `jp move`, which rejoins the stock landing check at `$4BD3` |
| Shot start and speed, bank 2 `$4C7E` to `$4C96` | 1 px ahead, 3 px a tick | 4 px ahead, 6 px a tick |
| Shot length, bank 2 `$5B29` to `$5B45` | a bubble after 14 ticks (24 with the item) | after 7 (12), sprite frames at half the counts |
| Bubble contact, bank 2 `$6815`, `$6819` | touching within 6 px either side | within 11 |
| Fire check, bank 2 `$4C4C` | fires once the last shot is a bubble | `call fire_gate`, which also waits out an 11-tick cooldown |
| Round load, bank 1 `$419B` | `ld a,($C04F)` | `call save_round`, which saves the round and returns that load |
| PASSWORD screen setup, bank `$3C` `$4036` | `ld ($D683),a` | `call pf_init`, which does that store, then reads the save and runs the encoder |
| PASSWORD screen, every frame, bank `$3C` `$4196` | `ld a,($D683)` | `call pf_step`, which draws the letters once and returns that load |
| Header `$0147`, `$0149` | MBC5, no RAM | MBC5+RAM+BATTERY, 8 KB |

The game moves Bub once every two frames. `move` (bank 2 `$7E1A`) replaces
the stock sideways movement and falling. Fractions of a pixel come from an
8-tick pattern that decides which ticks get the extra pixel. The jump itself
is a table of Y steps that the game already walks through, now the Master
System's arc. `patch.py` checks that nothing else in
the ROM jumps into the retired code. The landing check is stock, and so are
the bubble and enemy bounces, which start the same table.

The shot starts where stock's is after its first tick and moves 6 px a tick,
so it passes through every other one of stock's positions and stops at the
same place. Bub can only fire while the shot's slot is free, and the shorter
shot frees it sooner, so `fire_gate` adds a cooldown of 11 ticks, the Master
System's 22 frames (stock waits 14 ticks). The game's hit test for a shot is
14 px wide, so a 6 px step can't jump past an enemy.

The contact test between Bub and a bubble (`$67DD`) is used for empty
bubbles and ones with an enemy inside, and nothing else. It sorts a touch
into above, below and either side, and the patch only widens how far to
either side counts. Its height is stock's: Bub counts as above a bubble for
16 px, and he moves at most 6.5 px a tick relative to one, so he can't pass
through without touching.

The physics code and table (388 bytes) sit in the zero padding at the end of
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
python3 patch.py "Classic Bubble Bobble (USA).gbc" -o "Classic Bubble Bobble (USA) [SMS physics & save patch by thisJUSTin816 v1.0].gbc" --ips ClassicBubbleBobble-physics-save.ips
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
  turns stock into it when applied by a separate IPS reader. All 626 bytes that
  differ from stock are the patch's code and table, its hooks, the shot's constants, the two
  cartridge bytes in the header and the checksums.
- **Filler.** Filling both paddings with `$FF` changes none of 2490 frames of
  password entry and play. The control, breaking the VBlank vector, changes all
  of them. The stock game never changes `$CEC0`, `$CEC1` or `$CEC2`, whether
  they start at 0 or at `$FF`.
- **Physics.** From round 1, the numbers in the table above: height, time at
  the top and length of a jump, how soon it leaves the ground, the time near
  the top, falling after a jump off a ledge, the three speeds of a locked
  jump, steering, walking off a ledge, and walking. Both stock and patched
  catch the ledge 5 tiles above the start, and neither catches the platform 6
  tiles up.
- **The shot.** It stops 40 px right and 41 px left of Bub, as stock's does,
  in 13 frames against stock's 27, and 70 px with the longer-range item, in
  23 frames against 47. A second shot fires 22 frames after the first at the
  soonest, as on the Master System (stock 28). Seeded play traps at least as
  many enemies as stock does.
- **Bubbles.** With a bubble held in place and Bub dropped over it with jump
  held, he bounces anywhere in a 23 px span, where stock bounces in 13, and
  he is higher at the end of the tick that touches it, where stock's Bub is
  still sinking. Jumping up into one with jump held rises the usual 42 px and
  never bounces off it. With a bubble put 1-16 px into his feet, it pops or
  is left at the top's first half and standing, and coming down it bounces
  him at up to 5 px, bounces and pops at 6-7 and pops deeper, as on the Master
  System; stock bounces at every depth in all three.
- **Landing.** Over 6889 frames standing in seeded play on rounds 5 to 60, Bub
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
