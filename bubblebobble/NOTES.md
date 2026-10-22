# Bubble Bobble: notes on the game's internals

Found by reading the ROM (stock md5 `11c49d405eef2174d9c14682204bb458`, 128 KB,
MBC1) and tracing it in Gambatte and PyBoy. Addresses are for that release, in
bank 0 unless a bank is named. The README covers what the patch changes.

## Video

- The game doesn't tear. Its VBlank handler (`$0C6F`) writes SCX and SCY from
  HRAM `$FF94`/`$FF95` first thing.

## Rounds

- Every round start goes through the round loader `$1848`: a new game, a
  password, a clear (`$0708` then `$1327`), the boss rounds (`$3891` to
  `$3B71`) and the multi-round skips (`$3330`). The save hooks its first
  instruction.
- `$C200` is the round minus 1.
- `$FFC3` is the count of enemies left. Setting it to 0 clears the round, which
  is how `verify.py` gets through rounds.

## Passwords

- The encoder at bank 3 `$7650` takes D = round - 1 (`$C200`) and
  E = `$C4B5 | $C202`, as the game-over password at bank 1 `$60C5` does, and
  writes four tiles to `$C918`.
- Tiles are digits 0-9, then A = 10 up to Z.
- Known passwords: VLT1 (round 1, flags 8), VGL1 (round 2), KLL1 (round 3).
- The PASSWORD screen's setup (bank 3 `$70D0`-`$7128`) clears the entry after
  the store at `$7104`, so a pre-filled entry has to be written on the screen's
  first frame (`$7129`).
- `$C912` holds the hand's grid X while the hand is below the grid, and UP from
  the bottom rows reads it back. A pre-fill has to set it to the hand's starting
  X. Without that, UP twice from END puts the hand off-screen and types T.

## Free space

- Bank 0 `$0061`-`$00FF` and bank 3 `$771B`-`$7EFF` are runs of `$FF` the game
  never reads.
- `$CD06`-`$D821` stays zero through play, and the boot clears WRAM. The patch
  keeps its pending flag at `$D780`.

## Testing

- The PyBoy crash at the start of a round is a jump into cartridge RAM at
  `$B90C` after "GO!". Power-on RAM makes no difference. The game runs in
  Gambatte.
- Cold boot to the menu in Gambatte: START every 60 frames for 11 presses. From
  there, DOWN then START opens PASSWORD. Four DOWNs from the grid's home reach
  END.
