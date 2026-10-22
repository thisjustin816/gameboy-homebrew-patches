# Classic Bubble Bobble: notes on the game's internals

Found by reading the ROM (stock md5 `4bc8467ed91a94ba23648706b551cef5`, 1 MB,
MBC5) and tracing it in PyBoy, with the Master System version measured in an
emulator for comparison. Addresses are for that release. Addresses from `$4000`
up are in bank 2 unless a bank is named. The README covers what the patch
changes and has the table of jump, walk-off and shot speeds for stock, the
Master System and the patch.

## Bub's movement

- The game runs its logic every other frame, so Bub moves at 30 Hz. Both
  frames of a tick already run 55-90% full, which leaves no time to run the
  logic at 60 Hz.
- The jump is a table walk. `$C47D` counts down through the table (0 when not
  jumping), `$C47E` locks the direction held at take-off (0 none, 1 left,
  2 right), and `$C47C` is set when Bub stood on something at the end of the
  last tick. Three places set the jump's length: the jump start at `$4A4B` and
  the bounces at `$542A` and `$5657`.
- Take-off: in stock, the start branches at `$4A64`, `$4A6B` and `$4A7A` go to
  `$4AC3`, past the table step at `$4A7C`, so Bub first moves a tick later. The
  patch sends them to `$4A7C`.
- Outside a jump, gravity is 2.5 px a tick. The patch's jump table ends at the
  start height, so this gravity takes over from there, as it does after a jump
  on the Master System.
- `move` replaces `$4AEF`-`$4BD2` and rejoins the stock landing check at
  `$4BD3`. That check snaps Y with `and $F8`, which is safe for steps up to
  7 px. Fractions of a pixel use 8-tick bit masks against the tick counter at
  `$CEC0`.
- The collision map is at `$C053`, 32 tiles wide, bit 7 solid, read by
  `$0AB1`. Round 38 on every route doesn't read as a normal map there.

## Bubbles, shots and enemies

- The shot's state is `$D536`, 0 while the slot is free, and `$D537` counts
  its ticks. Its y and x are `$D506`/`$D507`. The fire check at `$4C4C` only
  needs `$D536` free.
- Floating bubbles: y and x pairs from `$D508`, states from `$D538`, velocities
  `$D556`/`$D557`. The mover is `$600E`.
- Enemy states are `$D301 + 4n`, 2 when trapped.
- `$C484` is the respawn invincibility the death routine `$0AD2` checks. While
  it is nonzero, Bub can't be hit and can't fire.
- The contact test `$67DD` checks Bub against empty bubbles and trapped enemies
  only. It counts Bub as on top of a bubble whose Y is 0-15 px below his, so
  stock bounces him (jump held) at any depth, at any point in a jump and even
  standing. Bubbles above his top (a negative Y difference) get stock's push or
  pop by side, where the Master System pops them.
- `bg_bubble`/`bg_enemy` at `$5421`/`$564E` apply the Master System's depth
  rule from JUMP 13 on (4 frames before the end of the top, the nearest tick),
  then go on at the stock pop, bounce or next-object code. Trapped enemies get
  the same rule as bubbles, unmeasured on the Master System.
- With the faster rise and no depth rule, a held jump bounces on a bubble on
  its way up and reaches 92 px.

## Master System measurements

Measured in round 1 from the Master System version's RAM in an emulator, in
pixels per frame. Bub's y is `$CE81` and his x `$CE82`. A bubble held in place
has Y `$D341`, x `$D342` and state `$D340` (140 floating, 129 popping).

- The jump rises 42 px in about 19 frames.
- Bubble depth, as the Y difference between the bubble and Bub: until frame 24
  of a jump (5 frames before the end of the top) and while standing, a bubble
  at 0-13 pops and one at 14-15 is left. From then on, falling and after
  walking off a ledge, it bounces him at 11-15, bounces him and pops at 9-10
  (he rises back through it) and pops below 9. Without jump held it pops at any
  overlap.
- A bubble lasts about 2100 frames in Classic and 802 on the Master System.
- The patched game matches the Master System here: walking, stopping, turning
  and firing respond 0-1 frames after the press (buttons are read every other
  frame), holding jump or fire doesn't repeat, stepping off a ledge falls when
  the back edge clears it, and play drops no extra frames.
- The Master System's round passwords don't take effect in the emulator, so
  only round 1 was measured there. SMS Power's Cheats page has the encoder in
  its password generator. The PASSWORD grid is
  `ABCDEFGH IJKLMNOP QRSTUVWX YZ345679`, button 2 selects, and the game reads
  input only at some moments, so retry until the cursor (`$C867` row, `$C8A7`
  column) moves.

## The save

- The route is `$C04E` and the round `$C04F`. The round load at bank 1 `$419B`
  reads `$C04F`.
- The encoder `$154E` turns the route and round into four letter tiles. It
  reads the live round, so `pf_init` swaps the saved one in and puts the live
  one back.
- A pre-filled screen has SLOT 3 and ROW 4 (END). `pf_step` queues the tiles
  through `$0BF5` to `$9887 + 2n` for slot n.
- MBC5 RAM: write `$0A` to `$0000`-`$1FFF` to enable it, and bank `0` to
  `$4000`.

## Testing

- Cold boot to round 1 in PyBoy: tick 600 frames, then START every 90 frames
  only until the round loads, because a further START pauses the game.
- Cold boot to the PASSWORD screen: tick 600, START three times 90 frames
  apart, DOWN, A. After typing the fourth letter, leave the cursor alone: moving
  it takes it off END.
- Any round: type BBBB and write `$C04E`/`$C04F` from a hook at bank 1 `$419B`.
- Enemies kill Bub partway through measurements. Holding `$C484` nonzero every
  frame keeps him alive without changing movement.
- No single WRAM byte clears a round. Seeded play blowing bubbles with Bub
  invincible clears round 1 in 3000-10000 frames. Seed 3 takes the door to
  route 2.
- The frame end `$0B8B` runs once a frame on every screen, which is where
  routine checks start. `$3FF0`, unused zero padding at the end of bank 0, is
  the return sentinel.
- In PyBoy a tick can straddle a frame, so a frame sampled mid-tick can show a
  jump's first step with the grounded flag still set. Tests that look at
  standing frames skip frames with a jump running.
- Round 1's platform ends act as walls near the top of an arc, so measure
  sideways speed over the first 16 frames in the air.
