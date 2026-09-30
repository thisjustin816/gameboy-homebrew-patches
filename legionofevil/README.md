# Legion of Evil: save, pause menu and color patch

A patch for Legion of Evil (Game Boy) that adds a battery save, a pause menu
that can save a run partway through, and a color mode with double speed for the
Game Boy Color and the ModRetro Chromatic. It also fixes the player sprite
disappearing in crowds and the thin strip that shifts at the top of the screen
when the camera scrolls.

- Game: Legion of Evil Rev 1, 32 KB, no mapper (a plain ROM, no save RAM)
- Stock md5: `cd544132f9d06ca9fe4f552ddc202878`

| Patch | What it does | ROM md5 after patching |
|---|---|---|
| `LegionOfEvil-save.ips` | Everything below in one patch. The ROM grows to 64 KB and the header says MBC1+RAM+BATTERY with 8 KB of RAM and Game Boy Color compatible. | `22ea1dd198e8cc4f2791b9091df9d061` |

## What you get

- **Upgrades are saved.** The money you bank when a run ends, every purchase in
  the store, the weapon levels and the highest difficulty unlocked are written
  to battery RAM as they change, so turning the console off never loses them.
- **Title menu.** With a save, START on the title opens a menu: CONTINUE (only
  when a run is saved), NEW RUN (the store, then difficulty and weapon, as after
  a death; if a run is saved it asks first, because starting a new run throws the
  saved one away) and ERASE SAVE (asks first). NO is the default on both pages. B backs out. With
  nothing saved, START starts a run as before.
- **Pause menu.** START during a run opens PAUSED: RESUME or SAVE & QUIT.
  To abandon a run, SAVE & QUIT and pick NEW RUN; the abandoned run's money is
  not banked (dying banks it, as in the stock game). The
  stock pause is replaced by this menu and the game stands still behind it.
- **Save and quit, then continue.** SAVE & QUIT writes the whole run (enemies,
  weapons, position, level, time) and returns to the title. CONTINUE puts you
  back on the same frame. Continuing uses the saved run up, so a saved run
  can't be reloaded after you die in it.
- **Color themes.** SELECT cycles eight themes (green, gray, pocket, amber, ice,
  blood, purple, sepia) on any screen: the title, menus, the store and during a
  run. The pause menu shows "SELECT:" and the theme's name. The choice is saved
  and survives ERASE SAVE. Color hardware only.
- **Punctuation.** The game's font has no `? ! . , ' &`, so the patch adds them,
  drawn in the font's style into tiles that no screen uses. The menus use them
  ("ARE YOU SURE?", "SAVE & QUIT").
- **The player stays on screen.** The hardware draws the first ten sprites on a
  scanline, in table order. The game puts the player last, so a crowd hid part of
  the player. Now the player and weapon sprites come first and the enemies
  follow in an order that shifts every frame, so a crowded line flickers
  enemies instead of hiding the same ones. Color hardware only (see the frame
  budget below).
- **No tearing strip at the top.** The game changed the scroll registers while
  the picture was being drawn, which shifted the top few lines for a frame. The
  scroll and palette writes now wait for VBlank.
- **Double speed.** On a Game Boy Color or Chromatic the game switches the CPU
  to double speed, so the logic uses at most about 60% of a frame at the worst
  moments instead of about 99%.

## Controls

| Where | Button | Does |
|---|---|---|
| Title | START | Starts a run, or opens the menu if something is saved |
| Anywhere | SELECT | Next color theme (color hardware) |
| Menus | UP, DOWN | Move the cursor |
| Menus | A or START | Choose |
| Menus | B | Back out (RESUME in the pause menu) |
| In a run | START | Pause menu |

## Frame budget

The share of a frame the game's logic and the patch's hooks use before the game
waits for VBlank, over a scripted play of one weapon and a pinned player. A frame
over 100% drops a frame (slowdown).

| Build | Median | 95th percentile | Worst |
|---|---|---|---|
| Stock | 49% | 71% | 99% |
| Patched, original Game Boy (single speed) | 52% | 69% | 86% |
| Patched, Game Boy Color or Chromatic (double speed) | 34% | 42% | 60% |

The run is 12000 frames in PyBoy, so the exact numbers move with the play; the
gap between single and double speed does not. On an original Game Boy the
patch skips the sprite reordering (it costs about 8% of a frame there) and
keeps everything else.

## Testing

`verify.py` boots the stock and patched ROMs in PyBoy, runs scripted input and
checks:

- the header, both checksums, the music-bank change and that the IPS rebuilds
  the ROM;
- START with nothing saved starts a run straight away;
- dying banks the money, the battery RAM holds the upgrades with a valid check,
  a power cycle (a new emulator on the same save file) brings them back, and a
  store purchase is written at once;
- the title menu, NO and YES on the erase page, and that the color theme
  survives an erase;
- NEW RUN with a saved run asks first: the page's text and columns, NO keeps the
  run, YES opens the store and removes the snapshot from battery RAM;
- the pause menu stops the game and offers RESUME and SAVE & QUIT, and RESUME
  carries on;
- SAVE & QUIT, a power cycle and CONTINUE give a run identical to one that was
  never interrupted: the same screens and the same game memory for 900 frames;
- a snapshot with a damaged byte is not offered;
- the stock game drops part of the player on crowded lines and the patched game
  never does (40000 frames);
- the stock game writes the scroll registers on visible lines and the patched
  game's registers never change between VBlanks;
- the six punctuation tiles are in video memory, the game's text routine maps each
  character to the right tile, and the erase and pause pages use them;
- the color palettes in palette RAM are the theme's colors through the game's own
  shades, the game-over, store and difficulty screens have the same shades in
  color and in gray, SELECT changes and saves the theme in a run, in the pause menu (which names it)
  and in the store, and an original Game
  Boy (the header's color flag cleared) stays at single speed with the game's
  palettes.

What this does not show:

- **Real hardware.** Nothing here ran on a console, a Chromatic or a flash cart.
  Double speed, the color palettes, the save on a real battery cartridge and the
  soft reset after SAVE & QUIT are emulator results only.
- **Sound.** The music keeps playing behind the menus, and CONTINUE restores the
  music player's state, but the hardware sound registers are not restored. The
  song may be quiet until its next note after CONTINUE. Sound was not compared.
- **How it feels.** The frame budget is PyBoy's count of scanlines, not a
  measurement of the game on a console.

## How it works

The stock cartridge has no mapper, but the game already writes bank numbers to
`$2000` (its music player selects a bank). Stock asks for bank 2, which a plain
ROM ignores; the patch points all seven calls at bank 1 and uses bank 2 for new
code.

| Where | What |
|---|---|
| Header | `$143` = `$80` (color compatible), `$147` = `$03` (MBC1+RAM+BATTERY), `$148` = `$01` (64 KB), `$149` = `$02` (8 KB RAM); both checksums repaired |
| Bank 0 stubs (`$0048`, `$00CE`, `$01E1`) | Small routines in bytes the game never reads that switch to bank 2, run a hook and switch back |
| Bank 2 (`$4000`) | The save, menus, pause, snapshot, sprite order and palette code (about 2 KB) |
| HRAM `$FF99` | The VBlank hook; copied from bank 2 at boot |
| Hooks | boot, the joypad read on the title and in the run loop, the store's buy routine, the game-over screen, and the frame wait at `$7AF8` |

**Save format** (battery RAM, `$A000`): the signature `LOE1`, 15 bytes of
upgrade state (`$C5C1` to `$C5CC`, `$C5CF`, `$C5DF` to `$C5E0`) and a check byte
at `$A013`; the theme and its check at `$A014`; a marker at `$A016` that is `$5A`
while a run snapshot is valid. The run snapshot starts at `$A100`: the stack
pointer, nine video registers, HRAM, the stack page, game memory (`$C000` to
`$CA1F`), both tile maps, a 16-bit sum and a build id. The build id is made from
the addresses the saved stack holds, so a snapshot made by a different build
is not offered.

**Why the snapshot is whole.** A run has no tidy save point: the game keeps the
enemy list, weapon timers and the camera in memory the code changes every
frame. The pause menu runs inside the game's own joypad read, so the snapshot
is taken at the same point in the main loop every time (the stack is always the
same depth there). CONTINUE starts a new run, which loads the tiles, then
writes the snapshot over memory on the first frame and returns into the pause
menu as if it had never left. The restore and the uninterrupted game were
compared for 900 frames in `verify.py`.

**Scroll and palettes.** The game's scroll writes (ten places) and palette
writes (six) now go to five HRAM bytes (`$FF94` to `$FF98`). The VBlank hook
copies them to the hardware and, on a color console, loads palette RAM when a
theme or shade changed. The game only sets its palettes once, at the title,
and uses only bits 4 and 5 of the sprite attributes, which is what makes the
color conversion safe.

**Double speed.** Switching needs `KEY1` and `STOP` with interrupts off, done in
the boot hook after the game has copied its OAM DMA routine. The DMA routine
counts CPU cycles, which are half as long now, so its wait is doubled (`$28` to
`$50` at `$FF87`). A soft reset checks `KEY1` and does not toggle twice.

## Applying it

Use any IPS patcher on an unmodified copy of the ROM and save the result under a
new name. The patch only applies to the stock md5 above. The save needs a
cartridge or flash cart that keeps 8 KB of battery RAM, and the save file is
named after the ROM.

## Building it

Python 3 only:

```
python3 patch.py "Legion of Evil Rev 1.gb" -o "Legion of Evil Rev 1 [Save, pause menu & color patch by thisJUSTin816 v1.0].gb" --ips LegionOfEvil-save.ips
```

`patch.py` refuses any ROM whose md5 it doesn't know, checks every byte it
replaces, and confirms nothing else jumps into the middle of a replaced
instruction. The code is `loe.asm`, assembled by `asm.py`. The tests need
`pip install pyboy pillow`:

```
python3 verify.py "Legion of Evil Rev 1.gb" "Legion of Evil Rev 1 [Save, pause menu & color patch by thisJUSTin816 v1.0].gb"
```
