# Bubble Bobble Part 2: notes on the game's internals

Found by reading the ROM (stock md5 `8bbb9ba0d72548706e4e5eba1b3a9fe1`, 128 KB,
MBC1) and tracing it in PyBoy. Addresses are for that release. The README covers
what the patch changes.

## Passwords

- A password is the world (`$C10A`), stage (`$C10B`) and extra bits (`$CE5D`)
  in four symbols at `$CE6C`-`$CE6F`. `$C10D` is `(world - 1) * 20 + stage`.
- The encoder is at bank 6 `$7EDC`, 89 bytes. The patch copies it verbatim to
  the start of bank 8.
- The password screen draws a symbol by queueing a tile at `$9886 + 2 * slot`
  through `$C111`-`$C114` and `$C102` bit 1. Slot 0 is at `$9886` because the
  game adds 3 to the slot number.
- After START accepts a password, the game returns to the title, which reads
  START ROUND n. One more START begins the stage. The password screen is not
  set up again in between.

## The patch

- `far8`, the switch to bank 8, clobbers A and F, as the game's own bank
  switches do.
