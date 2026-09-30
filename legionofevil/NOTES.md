# Legion of Evil: notes on the game's internals

Found by reading the ROM (stock md5 `cd544132f9d06ca9fe4f552ddc202878`, 32 KB, no
mapper) and tracing it in PyBoy. Addresses are for that release. Uncertain
facts are marked.

## Shape of the game

A survivors-style game: a run plays until you die, money from the run is banked
(capped at 9999), and upgrades bought in the store carry into later runs. Built
with GBDK-2020 and the gbt_player music driver (the C code is SDCC output, which
is why it is long and inline). The music driver's bank argument is 2 in stock;
the ROM has no bank 2 (see README).

Screen flow: title, run, game over, store, difficulty, starting weapon, run.
START advances through the last four.

## Memory

| Address | What |
|---|---|
| `$C0A0` | the A register the console booted with (`$11` on a Game Boy Color) |
| `$C0A3` | VBlank frame counter (16 bit, incremented by the interrupt) |
| `$C0CB`, `$C0CC` | maximum and current HP |
| `$C0D9` | logic counter; steps by about 5 a frame (uncertain why) |
| `$C090`-`$C09F` | shadow OAM: the player's four sprites |
| `$C080`-`$C08F` | shadow OAM: the weapon's four sprites |
| `$C000`-`$C07F` | shadow OAM: enemies, two slots each, only the even one used |
| `$C56E`-`$C5B1` | the music player's state |
| `$C5B5` | a menu or screen is showing (the main loop skips run logic) |
| `$C5B6` | the stock pause flag (START toggles it) |
| `$C5C1`-`$C5C6` | store stats: health, speed, armor, xp bonus, hp regen, gold (order uncertain) |
| `$C5C7`-`$C5CC` | weapon levels 0-3: sword, chainsaw, molotov, shuriken, boomerang, bowling |
| `$C5CF` | highest difficulty unlocked, 0-3 |
| `$C5D9`-`$C5DE` | screen-change flags: `$C5D9` and `$C5DA` are the level-up and boss-loot screens (which is which is uncertain), then game over (`$C5DB`), store (`$C5DC`), weapon (`$C5DD`), difficulty (`$C5DE`) |
| `$C5DF`-`$C5E0` | banked money |
| `$C5E5`-`$C5E6` | money collected in the run |
| `$C7D0`-`$C7D3` | HUD redraw flags |

Setting `$C5DB` to 1 is what a fatal hit does. The game-over code (`$1975`)
banks the run's money, so it is also a clean way to end a run in a test.

## Code

| Address | What |
|---|---|
| `$0100`, `$0150` | entry; `$0150` reloads A and B from `$C0A0`/`$C0A1` and runs the start-up again (a soft reset) |
| `$0182` | copies the OAM DMA routine to `$FF80` (`$28` is its wait count) |
| `$009C` | VBlank handler: counter, `call $FF80` at `$00A4`, then sets `$FF91` |
| `$56B7` | title; its loop waits for START at `$57B9`-`$57CE` |
| `$57D0`-`$58B1` | run start-up; `$58B5` is the main loop's frame wait, `$58BB` its joypad read |
| `$5929`-`$5989` | dispatch of the screen-change flags |
| `$5A0C` | the stock pause (toggles `$C5B6`, swaps the music) |
| `$1975`, `$1E5A`, `$189A`, `$2378` | game over, store, difficulty, weapon screens |
| `$22CF` | the store's buy routine; it ends by redrawing the store (`$1E5A`) |
| `$37C1` | the screen-change transitions (game over to store to difficulty to weapon to run) |
| `$3A83` | camera and player sprites; writes the scroll registers four times |
| `$51C4` | enemy loop (half the enemies each frame, `$C5B2` picks the half) |
| `$4984` | weapon loop |
| `$7AF8` | wait for VBlank |
| `$7B08` | turn the LCD off (waits for line `$91` first) |
| `$7BB2` | joypad read; E = buttons with START `$80`, SELECT `$40`, B `$20`, A `$10`, DOWN `$08`, UP `$04`, LEFT `$02`, RIGHT `$01` |
| `$7A72`, `$7A7A` | set one BG or window tile |
| `$7B8E` | set a rectangle of tiles from a table |
| `$70F3` | music update; `$70E1` stop; `$7013` start a song |
| `$7DB6` | defaults table copied to `$C5B2` at boot (`$7FEB`) |

## Video

- 8x8 sprites, LCDC `$E3` in a run: window map `$9C00`, BG map `$9800`, tile data
  at `$8800` with signed indices. The window (WY `$80`) carries the HUD rows.
- The font for menus is in VRAM during a run: A-Z at tiles `$55`-`$6E`, 0 at `$6F`,
  1-9 at `$70`-`$78`, `:` `$79`, `-` `$7C`, `+` `$7D`, the diamond cursor `$7E`,
  blank `$7F`. There is no `&`, `?` or `>`.
- Tile graphics never change during a run, so a snapshot does not need them.
- The palettes are written once, at the title: BGP and OBP0 `$E1`, OBP1 `$6C`.
  Sprite attributes only use bits 4 (OBP1, the damage flash) and 5 (X flip).
- Sprites per line: the stock game draws the player last in the table, so a
  crowd (more than ten sprites on a line) drops the player. About 0.5% of frames
  overflow in a long scripted run.
- The stock game writes its BG map while the picture is drawn, and scrolls with
  direct writes to SCX and SCY (`$3BA4`, `$3BBF`, `$3BD6`, `$3BF1`), a few of
  which land on visible lines.

## Timing

In a long scripted run the logic takes about 49% of a frame at the median, 71% at
the 95th percentile and up to 99% at the worst moments (PyBoy, one weapon). The
game's OAM DMA wait counts CPU cycles, so it has to double when the CPU does.

## HRAM and WRAM the patch uses

- HRAM: `$FF94`-`$FF98` shadows for SCX, SCY, BGP, OBP0 and OBP1; `$FF99` onward
  is the VBlank hook. The game uses `$FF80`-`$FF8B` (DMA routine) and `$FF90`-`$FF92`.
- WRAM: everything from `$D000` up is free (a run never touches it). The patch
  keeps its variables at `$D000`-`$D018`, the window-map backup at `$D100`, the
  palette buffer at `$D200` and the sprite table the DMA reads at `$DA00`.
