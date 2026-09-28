# Roguecraft GB internals

Research notes from building the patch, for the release with md5
`6de80f13b9ab562de2227ea5dd818275`. Addresses are `bank:$addr` (bank 0 omitted),
and ROM offset = bank × `$4000` + (addr - `$4000`). These notes also record
findings the patch doesn't use. Where a fact is less certain, it says so.

## Engine

The game is built with GB Studio 3 (GBVM scripts, C natives in bank 2).

- **Banked calls:** `ld e,bank / ld hl,fn / call $3E01`. The trampoline saves
  the current bank (HRAM `$90`), switches, calls, and restores the bank,
  preserving A and HL. At the callee: SP+0 = `$3E0B`, SP+2 = the saved bank,
  SP+4 = the caller's return address, SP+6 = the first stack argument. One-byte
  arguments are pushed as `push af / inc sp`.
- **GBVM:** the opcode table is at ROM `$0324`, one 4-byte entry per opcode
  (fn lo, fn hi, bank, argument bytes). The dispatch is in bank 0 around `$3967`;
  at `$3978`, HL = the script PC and HRAM `$90` = the script's bank, which
  makes a good trace hook. `VM_CALL_NATIVE` is `$2D` (operands: addr hi, addr lo,
  bank); its handler at `$3954` pushes THIS and calls through `$3E01`. Actor ops
  are `$30`-`$3F` (bank 4) and overlay/text ops `$40`-`$4F` (bank 18).
- **Actors:** 52-byte structs at `$C0D1 + 52·slot`. The fields:
  - `+$00` flags: bit 0 active, 1 pinned, 2 hidden, 3 disabled, 4 anim_noloop,
    5 collision, 6 movement_interrupt, 7 persistent.
  - `+$01` x and `+$03` y, both 16-bit in 1/16 px. `+$05` direction.
  - `+$0A` base tile. `+$0B` frame. `+$0C` frame_start and `+$0D` frame_end
    (end exclusive).
  - `+$0E` anim_tick mask (`$FF` = paused). `+$10` animation index.
  - `+$12`-`+$21` `animations[8]`, (start, end) pairs, end inclusive.
  - `+$22` sprite-sheet bank, `+$23` sheet pointer.
  - `+$30` next, `+$32` prev.

  The active list's tail is at `$C517`. `actors_update` (`$10F7`) walks from
  the tail by prev, calling `move_metasprite` (`$1028`) at `$144A`. At
  `$144E`, A = the number of sprites that actor used, `$C528` = the actor and
  `$C527` = its first OAM index. The game often doesn't redraw every frame
  when busy, so track each actor's latest count rather than a per-frame one.
- **The engine's hiding of actors under the window is off** in this game (the
  flag `$C52E` comes out 0 in play). The game hides actors under the mini-map
  itself; see below.
- **OAM:** double-buffered in pages `$C000` and `$DF00`. The page to DMA is in
  HRAM `$92`, and the next one is in `$DD35`.
- **VBlank:** the handler at `$1AF4` copies the WY shadow `$C93B` to WY. WX is
  `$C939 + 7` when WY < 144; otherwise the window is off.
- **STAT:** the handler at `$19D3` adds 3 to SCY every 13 lines, squashing
  16-px tile rows to 13 px. That's why room rows are 13 px apart.
- **RNG:** `$3B7E`, with the seed at `$DB7E`-`$DB7F`. Poke the seed to vary
  outcomes in tests.
- **Memory:** the stack starts at `$DF00`. In testing it never went deeper
  than `$DDB8`. The game's own data ends at `$DD36`, and nothing in the stock
  ROM names `$DD37`+. The patch uses `$DD37`-`$DD4D`.

## Saves (bank 20)

- `data_save(slot)` `20:$44E7`, peek/load `20:$471A` (slot, word offset,
  count, destination), `data_clear` `20:$46ED`.
- The save table at `20:$440F` lists 23 WRAM regions, 5166 bytes in all. Slot
  0 (the run) is at SRAM bank 0 `$A000`, and slot 1 (achievements) at SRAM
  bank 1 `$A000`. Each slot starts with the signature `07 41 FE 2B`, the bytes
  at ROM `$0560`.
- The stock game only writes slot 0 at game over, with the floor set to 0.
  START GAME peeks the saved floor to decide between RESUME / NEW GAME and hero
  select.
- The ROM also carries GB Studio's batteryless-save code, which saves to a
  flash cart's chip instead of SRAM (D0/D1-swapped command bytes). It's a
  cartridge option in GB Studio; this build doesn't use it, and nothing calls
  it.

## Game variables

GB Studio variable `vN` is at `$CBB7 + 2N` (16-bit):

| var | address | meaning |
|---|---|---|
| v5 | `$CBC1` | gold (HUD counter) |
| v11 / v12 | `$CBCD` / `$CBCF` | current room column / row |
| v75 | `$CC4D` | floor index 0-10 |
| v76 | `$CC4F` | hearts carried into a floor |
| v135 | `$CCC5` | 1 on the last floor |
| v151 / v152 | `$CCE5` / `$CCE7` | chests total / found (end screen) |

The floors come in a fixed order:

| index | floor |
|---|---|
| 0 | The Wilderness |
| 1 | Cave of Mild Unease |
| 2 | Get the Gold! |
| 3 | Spectral Shenanigans |
| 4 | Clucking Hell! |
| 5 | Snarky Slime Pit |
| 6 | Gauntlet of Pain |
| 7 | Yung and Beautiful |
| 8 | Hail and Kill |
| 9 | It Just Gets Darker |
| 10 | It Waits Dreaming |

Floor 10 is a single boss arena with no mini-map. The generator still builds a
normal hidden layout for it.

## Floors, rooms, entities

- **Floor start:** every floor script's first instruction is a native call to
  the floor setup at `2:$401B`, which loads the hero from the variables. The
  generator runs after that. It lives in bank 4, and its `chests_total += 1`
  is at `4:$56CE`.
- **Rooms:** each floor is a 5×5 grid of rooms, with room index = 5·row + col.
  - `$D9BD` holds the item words (25 × 16 bits; bit 1 = the chest) and `$DA08`
    the monster words. `$DA3A` is the room grid, column-major (5·col + row).
  - Taking an item clears its bit. The stock clearer at `2:$4236` subtracts the
    bit. The slot→bit table is `$DC7D`, with a ROM copy at `$3F14`.
  - `2:$4E40` onwards adds an entity's bit back into a room's item word (a
    drop?). Not investigated.
- **Cells in a room:** 10·row + col, where x = 16·col and y = 12 + 13·row.
  The mini-map covers cells 77-79, 87-89 and 97-99, the bottom-right 3×3.
- **Entity tables:** up to 19 entities per room, with the count at `$DCC9`.
  Entity 0 is the hero and entity 6 is the chest.
  - `$DC44+e` hp. 0 = absent; the chest uses 2 = shut, 1 = its gold.
  - `$DC57+2e` state word (the chest is 9).
  - `$DCA3+e` actor slot.
  - `$DCCA+e` cell.
- **Room entry:** around `2:$4300`, the game reads the room's monster and item
  words and sets each entity's hp. The chest is at `2:$44F5`-`$4507`: if bit 1
  is set, hp = 2.
- **Placement on entry:** after the hp are set, the loop at `2:$46FF`-`$47AA`
  gives every entity from 1 up a cell through `2:$4D51`, present or not.
  - The spots come from `$DCDD`, 48 cells shuffled once per floor by the floor
    setup (`2:$403C` calls `6:$5AC2`). Call it T, and r the room index.
    Monsters use T[r], T[r+1], ... up to T[24], then wrap to T[0]; items use
    T[23+r] up to T[47], then wrap to T[23]. `2:$54E7` sorts entities into
    monsters and items from their state word.
  - Each entity takes the first spot in its list whose tile is placeable
    (`2:$55BE`) and that no entity with hp > 0 holds (`2:$57AB`).
  - A taken item or a killed monster has hp 0 and claims nothing, so every
    entity after it moves up a spot. That's how the chest (entity 6) lands in
    the heart's spot once the heart (entity 3) is gone.
  - Entities not yet placed still hold their cells from the room just left,
    and those count as taken. So even with nothing taken, an item can skip a
    spot it held next door, including its own old cell.
  - Monsters come back to their list spot, not to where they walked. Opening a
    chest doesn't change its cell, so its gold is placed just as the shut
    chest would be.
- **Opening a chest:** around `2:$6380`-`$646F`. The game loads animation set
  `$21` (gold), calls `6:$6FAC` with tile `$19` (the open-chest graphic),
  adds 50 to v5, and adds 1 to chests found (`2:$644A`). Picking the gold up
  later adds another 50.

## Animation and the mini-map

- **Loading animation sets:** `$179B` (A = sheet bank, DE = sheet, stack: set
  index, destination) copies a sheet's set into `actor+$12`.
  `7:$45F8(actor, start, end+1)` sets the frames.
- **Sprite sheets** are structs:
  - n_metasprites (2 bytes), 1 byte;
  - pointers to the metasprites, animations and animation lookup;
  - bounds (4 bytes);
  - far pointers to the tileset and the CGB tileset.

  On the entity sheets checked, set 1 (usually also sets 2 and 5) is a single
  empty frame. Known sheets:
  - `15:65E8` the hero;
  - `14:7FEB` the tentacle monster (Gluthulhu);
  - `15:5D3D` the small-monster sheet (chickens and others);
  - `17:7CE3` the chest;
  - `15:71BC` the attack effect.
- **The refresh:** `2:$5972(entity, flag)` picks and loads an entity's set from
  its state and hp. It runs for every entity every other frame, and from the
  map close. With flag 0 it skips an entity when any of these holds:
  - its hp is 0;
  - the map is open (`$DD1C` = 1);
  - the attack lock `$DD1D` is running (enemies only, not the hero);
  - `$DD1E` is set (the hero only; set at `2:$53C3` in some hero state);
  - it's entity `$12` on the last floor.
- **The attack lock:** the attack routine around `2:$6A90` loads an animation
  set, sets `$DD1D` = 60, and compares a random number with `$CCDB` (probably
  the hit roll). `$DD1D` counts down once per game tick at `2:$72D0`, about
  every 2.4 frames, so the lock lasts about 2 seconds.
- **The mini-map** is a script in bank 25 around `$6034`-`$60A0`:
  1. `VM_CALL_NATIVE 2:$5876` (map open). Every living entity in a map cell is
     given the empty set via `2:$5903`.
  2. `VM_OVERLAY_MOVE_TO` (WX 119; WY 96 open, 136 closed).
  3. `VM_CALL_NATIVE 2:$58E3` (map close). It refreshes every entity, but the
     attack lock blocks enemies, which was the vanishing-enemy bug.
- **Enemy turns:** they happen while the map is open. An enemy that attacks
  under the map gets its attack set, so it's drawn over the map.

## Title screen

- **Registers:** LCDC is `$C7`, so the BG uses map `$9800` with `$8800`
  signed tile data, and the window is off. The title is up about 1500 frames
  after a cold boot. Only sprites move on it, and none reach the bottom-right
  corner.
- **The background struct** is at `1A:$405F`: 20×19 cells (row 18 is
  off-screen), then the DMG tileset `0A:$5804`, CGB tileset `0B:$5E56`,
  tilemap `17:$61B1` and attribute map `17:$6035`. The title scene at
  `19:$5420` points to it.
- **Tilesets** are a 16-bit tile count and then uncompressed 2bpp tiles.
  - The VRAM bank 0 set holds 181 tiles, the bank 1 set 180. Entries up to
    `$7F` are the tile index.
  - The rest are loaded to end at index `$BF`, so for the bank 0 set,
    entry = index - 11 for `$8B`-`$BF`; for bank 1, index - 12 for
    `$8C`-`$BF`.
- **The version** is drawn into the image at row 17, columns 16-19, in
  palette 3 (color 1 is the text), over dithered artwork.
  - The glyphs are 3×5 with a 1-pixel gap, at x 133-157, y 137-141.
  - The cells alternate VRAM banks: tile `$BC` in bank 0, then `$BD` in bank
    1, `$BD` in bank 0 and `$BE` in bank 1. Each is used by that one cell
    only, and no later screen loads them.
  - Almost no tile in the image is shared: only the plain color-3 tile `$09`
    in bank 1 is.

## Room layouts

- Layouts are ASCII text in bank 4, two decimal digits per cell, 10×10 cells.
  Ids 0-49 are in ten blocks of five (the block table is at `$DD21`, starting
  `4:$56EE`); ids `$62` and up start at `4:$7CC4`. `4:$7E68` parses one into
  `$DAE9`, and the room's column-major grid at `$DA85` is filled from that, at
  times transposed or mirrored. `$DA53` holds each room's layout id.
- **A stock slip in layout 7** (`4:$5CB1`): a 3×3 shrine picture in its corner
  has its top-left cell as void (`01`) and the cell next to it as floor (`10`),
  where layouts 8 and 13 have `18 40`. It turns up on floor 1 in most seeds,
  drawn identically by stock and the patch. Not changed.

## Title menu and the resume menu

- **The title's actors:** slots 1 and 3 are the title art (sprites down to
  y 82), 2 the menu (START GAME to CREDITS, 18 sprites, sheet `0A:$7FEC`), 4
  the chicken (y 121-131), 5 and 6 the torches (y 89-111).
- **The menu's highlight** is a tile swap, not a palette: every sprite uses
  OBJ palette 4, and the selected entry's sprites take their tiles from VRAM
  bank 1 (yellow) instead of bank 0 (white). Each entry has a 16-frame
  animation: a shimmer (frames 2-7), then rest. Its 81 metasprites are one
  blank frame and 5 × 16. The tiles load at `$22`: 48 in bank 0, 46 in bank 1.
- **Input** runs a short script per press: down is `17:$7A71`, which moves
  variable `$23` (the selected entry) and sets actor 2's animation. A runs
  `16:$6723`, which switches on `$23`.
- **The resume menu** (`16:$67A9`-`$67F7`, after START GAME peeks the saved
  floor): a palette load, `VM_LOAD_TEXT` (`16:$67B4`), `VM_OVERLAY_CLEAR`
  (20 × 4 tiles, `$67D6`), `VM_OVERLAY_MOVE_TO` y 14 = WY 112 (`$67DD`),
  display, wait, then `VM_CHOICE` (`$67E7`) into `$23` with B allowed. After
  it, the box moves out (`$67F8`) and a `VM_SWITCH` on `$23` goes to `$6813`
  (B: fade, reload the title), `$6849` (RESUME GAME) or `$6850` (NEW GAME).
- **The box's tiles** use attribute `$87` (palette 7, BG priority), meant to
  hide the sprites under them. The patch hides those actors as well, so
  nothing depends on how a device handles that priority.
- **GBVM operands**, from the opcode table and the handlers: each op's
  argument bytes are pushed in order, so 16-bit operands are stored high byte
  first, and the macro order is reversed. `VM_CALL_FAR` `$0A` hi lo bank;
  `VM_RET_FAR` `$0B` n; `VM_PUSH_CONST` `$01` hi lo; `VM_POP` `$02` n;
  `VM_SET_CONST` `$14` value, index; `VM_ACTOR_SET_FLAGS` `$3F` mask, flags,
  actor. A negative index is on the VM stack, `$FFFF` its top. VM flag `$02`
  sets the actor struct's hidden bit (checked in emulation).

## Leads not followed up

- **The chicken that vanished at a MISS with the map shut**, seen once in play.
  Not reproduced. A hero miss on the chicken and the chicken's
  own attack both left it visible in testing. One guess: its animation table
  was still the map's empty set from a toggle about a second earlier. Walking
  keeps the current set, so a later `actor_set_dir`-style change would blank it.
- **Useful test techniques:**
  - Hook `$144E` to see what each actor actually drew.
  - Hook `$3978` to trace VM opcodes.
  - Walk a fixed d-pad route: press 10 frames and wait 26; add 60 frames after
    going through a door. Replays are deterministic from a cold boot.
  - `verify.py` has examples of all of these.
