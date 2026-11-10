# The Chessmaster: notes

What is known about the game's internals, for the crash fix and anyone who
works on it next. Addresses are for The Chessmaster (USA) (Rev 1), md5
`6b6d4a25d3c1e2890b22271c44e62dbf`. The search runs in bank 2. Only the VBlank
interrupt is enabled while it thinks, and the timer is off.

## Board and pieces

- `$D100`: the board, 0x88 style, 16 bytes a rank with rank 8 first. The low
  three bits are the piece (pawn, king, knight, rook, bishop, queen from 0),
  bit 4 is White. Columns 8-15 of each rank (`$D108` + square) hold each
  piece's index in its side's piece list.
- `$D0C0` and `$D0D0`: the two piece lists, one square each, `$FF` for a
  captured piece and `$F7` past the end. Making a move from an empty square
  reads index 0 of a list, which is a square, and uses it as a piece type to
  index a six-entry jump table at bank 2 `$6762`. That is how a bad line ends
  up running VRAM or data.
- `$C000`/`$C001`: the cursor sprite's Y and X.

## The search

- `$D014`: the ply being searched, 1 at the root. Nearly every per-ply table
  is indexed with `add hl,bc` and C = ply, so the search relies on B being
  zero. The evaluation keeps a scratch value in B at bank 2 `$6DE3`.
- `$D013`: the iteration depth. `$41A6`-`$41F4` is the iteration loop, and
  `$41F7` loads the principal variation into the first line to search
  (`$D51D` from-squares and `$D527` to-squares, `$D015` moves left).
- `$D703`: the principal variation, a triangular table with rows at the offsets
  in bank 2 `$55A6` and lengths at `$D501` + ply. `$55B0` updates it. At the
  root, the same routine moves the new best root move to the front of the root
  list (`$5612`).
- `$D700` root moves, `$DACC` the root list (node numbers, best first),
  `$D701` the root moves left in this iteration. Each node has a move at
  `$D75F` and `$D7EC` + node and a stored line chained through `$D879` +
  node. `$5675` stores the searched line under the current root node, which
  `$577B` takes from the list.
- `$4968`: a root move that fails high. It sets the principal variation to that
  move alone and searches it again (`inc ($D701)`). Only a re-search that
  beats the raised bound reaches `$55B0` and its reorder. That is the root
  order bug the patch fixes.
- Stored lines are replayed at the root without a legality check
  (`$4C35`-`$4C79`), which turns either bug into a crash.

## The thinking clock

- `$C7DC` is 1 while the computer thinks after a human move (`$1D3B`). The
  VBlank handler then calls `$26DC` every frame, which counts frames in
  `$DB41` and every 30 frames advances one of the two 16-bit clocks at `$D585`
  and `$D587`, chosen by bit 3 of `$D02D`. The stock code forms the address
  with `add hl,bc` and never sets B.
- A turn handed to the computer from the menu, for example after entering a
  position in two-player mode, does not set `$C7DC`, so its clock never runs.
  That is why a crash that came from this bug did not come back when the same
  game was re-entered by hand.
- On Infinite the search does not read the clock (bank 2 `$7230`, which does,
  never runs), so the patched tick changes nothing the search sees.

## Testing notes

- The search on Infinite is deterministic for a position and the state the game
  carries, so a crash recurs at the same frame however long the game waits before
  the move that starts it. Crashes from the clock bug depend on exact cycle
  timing and come and go with small changes to the game that led up to them.
- An invalid opcode locks the console. PyBoy 2.8.1's handler for one does not
  advance the clock, so `tick()` never returns: run long PyBoy sessions with
  a timeout.
- A PyBoy hook placed on the operand byte of an instruction replaces that byte
  and breaks the instruction. Hook only instruction starts; with the patch,
  `$26F8` is inside `ld h,$D5`.
- SameBoy 1.0.5 started from a PyBoy state copied into it (work RAM, HRAM,
  VRAM, OAM, I/O, registers and bank, at the start of line 0) runs the same
  search as PyBoy, frame for frame, and crashes on the same frame. Its input
  timing differs, so the two drift apart after a button press.
