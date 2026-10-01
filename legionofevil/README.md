# Legion of Evil: save, color and rumble patch

A patch for Legion of Evil (Game Boy) that adds a battery save, a pause menu
that can save a run partway through, and a color mode with double speed for the
Game Boy Color and the ModRetro Chromatic. It also fixes the player sprite
disappearing in crowds and the thin strip that shifts at the top of the screen
when the camera scrolls.

- Game: Legion of Evil (Rev 1), 32 KB, no mapper (a plain ROM, no save RAM)
- Stock md5: `cd544132f9d06ca9fe4f552ddc202878`

| Patch | What it does | ROM md5 after patching |
|---|---|---|
| `LegionOfEvil-save.ips` | Everything below in one patch. The ROM grows to 64 KB and the header says MBC5+RUMBLE+RAM+BATTERY with 8 KB of RAM and Game Boy Color compatible. | `57d2cf87768f7f8be5c389103d9f59ce` |

## Versions

- **v1.2:** the rumble motor runs solid for 6 frames from each hit, long enough for a motor to spin up, and for a third of a second when a boss comes in. The header says MBC5+RUMBLE+RAM+BATTERY, so the motor is bit 3 of the RAM bank register. The game maps bank 1 before its start-up runs, so a flash cart whose mapper powers up on another bank no longer hangs on a white screen. A run saved by v1.1 is not offered; upgrades and money carry over.
- **v1.1:** nothing of the title, its wipe or the run shows between the title menu and the store or a continued run, and SAVE & QUIT keeps the run hidden and restarts as at power-on. Menu pages go on screen in one step with their cursor. A run saved on one kind of console now continues on the other, with its sprites, and without a black screen after the next SAVE & QUIT. A run saved by v1.0 is not offered; upgrades and money carry over.
- **v1.0:** the first release.

## Changes

- **Upgrades are saved.** The money banked when a run ends, every purchase in
  the store, the weapon levels and the highest difficulty unlocked are written
  to battery RAM as they change, so turning the console off never loses them.
- **Title menu.** With a save, START on the title opens a menu: CONTINUE (only
  when a run is saved), NEW RUN (the store, then difficulty and weapon, as after
  a death; if a run is saved it asks first, because starting a new run throws the
  saved one away) and ERASE SAVE (asks first). NO is the default on both pages. B backs out. With
  nothing saved, START starts a run as before.
- **Pause menu.** START during a run opens PAUSED: RESUME or SAVE & QUIT.
  To abandon a run, SAVE & QUIT and pick NEW RUN; the abandoned run's money is
  not banked (dying banks it, as in the stock game). The game stands still
  behind the menu. It replaces the stock pause, which froze the run with nothing
  on screen and could go off by itself when START was held from the title into
  the run; now START in play only opens the menu.
- **Save and quit, then continue.** SAVE & QUIT writes the whole run (enemies,
  weapons, position, level, time) and returns to the title. CONTINUE resumes
  on the same frame. Continuing uses the saved run up, so a saved run can't be
  reloaded after a death in it. A run saved on an original Game Boy can be
  continued on a color console, and the other way around.
- **Color themes.** SELECT cycles 16 themes on any screen: the title, menus, the
  store and during a run. The pause menu shows "SELECT:" and the theme's name.
  The choice is saved and survives ERASE SAVE. Color hardware only. The themes:
  - the original Game Boy screens: DMG (the default), POCKET and LIGHT;
  - the twelve palettes a Game Boy Color offers for an old game when a direction
    is held at power-on, with or without A or B, under their usual names:
    DK GREEN (Right+A, "dark green", which is also what a Game Boy Color picks
    for this game on its own), GREEN, REVERSE, BROWN, RED, DK BROWN, BLUE,
    DK BLUE, GRAY, PASTEL, ORANGE and YELLOW. These have separate colors for the
    background and the two sprite palettes, as on the console;
  - OLIVE, a gray-green background with orange sprites, one of the Game Boy
    Color's palettes for specific games.
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
- **Hit flash.** On a hit the game switched the player to the second
  sprite palette for a single frame. Each hit now shows 2 frames on that palette
  and 2 frames normal, so being hit reads as a clear blink (and still does with
  frame blending). The damage and hit timing are the game's own.
- **Rumble.** On a cartridge or emulator with a rumble motor, the motor runs
  solid for 6 frames from each hit, long enough for a motor to spin up, and for a
  third of a second when a boss comes in. It stands in for sound effects, which the game has none of, so it
  marks events in play and not the ones that open a screen. It is off in menus,
  after a hit's last kick and through SAVE & QUIT, and a continued run with a
  boss already in play does not rumble for it again.
- **No flashing between screens.** The menus draw with the LCD on, the way the
  game draws its own screens (a Game Boy Color shows an LCD-off frame as white):
  each video memory access waits until the LCD is not drawing a line, only the
  tiles that change are rewritten, and a page goes on screen in one frame with
  its cursor. CONTINUE and NEW RUN start a run through the game's own start-up,
  which shows the title and its wipe first; the screen stays in its darkest
  shade from the menu until the restored run or the store is ready. SAVE & QUIT
  keeps the run hidden while it is saved, then restarts with the LCD off and
  video memory cleared, so the title comes up as at power-on.
- **Double speed.** On a Game Boy Color or Chromatic the game switches the CPU
  to double speed, so the logic uses at most about 60% of a frame at the worst
  moments (stock: about 99%).

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
| Patched, original Game Boy (single speed) | 53% | 70% | 86% |
| Patched, Game Boy Color or Chromatic (double speed) | 35% | 42% | 60% |

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
- the title comes up when the mapper powers up with bank 0, 2 or 3 at `$4000`
  instead of bank 1, on both consoles;
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
  never interrupted, on both consoles: the same game memory, sprites and video
  memory for 900 frames, and the same screens apart from, on some frames, one or
  two lines that the game draws a scanline earlier or later (its camera writes
  the background while the picture is drawn, and the music, which keeps playing
  behind the menu, shifts that write by a line);
- a snapshot with a damaged byte is not offered;
- a run saved on one kind of console and continued on the other draws its
  sprites from the game's table and comes back to a visible title after the next
  SAVE & QUIT, on the console it is running on;
- one run saved and continued twice, through each of Game Boy > color > Game
  Boy, color > Game Boy > color, Game Boy > Game Boy > color and color > color >
  Game Boy, comes back each time with the same upgrades, weapons, run money and
  maximum HP, with the color flag, sprite page, DMA wait and CPU speed this
  console needs, keeps playing with the player drawn, and quits to a visible
  title;
- the stock game drops part of the player on crowded lines and the patched game
  never does (40000 frames);
- stock shows the hit palette for one frame per hit, and the patched game shows
  2 frames on and 2 off per hit, on both consoles, and the rumble motor runs
  solid for the first 6 frames of each hit and at no other time in play;
- the motor is off in the pause menu, after a death's last hit kick and through SAVE
  & QUIT, even right after a hit, on both consoles;
- a boss's entrance (found by playing until one comes in) runs the motor for 20
  frames, and continuing a run with a boss in play does not rumble, on both
  consoles;
- the stock game writes the scroll registers on visible lines and the patched
  game's registers never change between VBlanks;
- no menu, page or CONTINUE change turns the LCD off (the stock game never does
  either), and SAVE & QUIT turns it off once, for the restart;
- NEW RUN and CONTINUE go from the menu to the store or the run through one
  flat shade, on both consoles;
- every menu page goes on screen in one step with its cursor, and SAVE & QUIT
  shows one flat shade until its restart, which ends on the title a power-on
  shows, on both consoles;
- every video memory and palette access the patch makes happens while the LCD
  is not drawing a line, at single and at double speed. PyBoy does not block
  these accesses the way the hardware does, so this is checked separately, at
  each access instruction;
- the six punctuation tiles are in video memory, the game's text routine maps each
  character to the right tile, and the erase and pause pages use them;
- the color palettes in palette RAM are the theme's colors through the game's
  own shades, the game-over, store and difficulty screens have the same shades
  in color and in gray, SELECT changes and saves the theme in a run, in the
  pause menu (which names it) and in the store, and an original Game Boy (the
  header's color flag cleared) stays at single speed with the game's palettes.

What this does not show:

- **Real hardware.** Nothing here ran on a console, a Chromatic or a flash cart.
  Double speed, the color palettes, the save on a real battery cartridge, the
  soft reset after SAVE & QUIT and the menus drawn with the LCD on are emulator
  results only. The access-timing check follows the hardware's rule, but only a
  console shows whether a menu comes out clean.
- **Sound.** The music keeps playing behind the menus, and CONTINUE restores the
  music player's state, but the hardware sound registers are not restored. The
  song may be quiet until its next note after CONTINUE. Sound was not compared.
- **How it feels.** The frame budget is PyBoy's count of scanlines, not a
  measurement of the game on a console.

## How it works

The stock cartridge has no mapper, but the game already writes bank numbers to
`$2000` (its music player selects a bank). Stock asks for bank 2, which a plain
ROM ignores; the patch points all seven calls at bank 1 and uses bank 2 for new
code. It declares an MBC5 cartridge, which takes those bank numbers the same
way and has a rumble motor on bit 3 of its RAM bank register.

| Where | What |
|---|---|
| Header | `$143` = `$80` (color compatible), `$147` = `$1E` (MBC5+RUMBLE+RAM+BATTERY), `$148` = `$01` (64 KB), `$149` = `$02` (8 KB RAM); both checksums repaired |
| Bank 0 stubs (`$0048`, `$00CE`, `$01E1`) | Small routines in bytes the game never reads that switch to bank 2, run a hook and switch back |
| Entry (`$0100`) | Jumps to a stub that maps bank 1 and then starts the game. The start-up calls `$7B08` and `$7FEB` before it writes a bank number, which a plain ROM always has mapped, but a mapper's power-on bank is not guaranteed to be 1 |
| Bank 2 (`$4000`) | The save, menus, pause, snapshot, sprite order, palette and theme code (about 3.3 KB) |
| HRAM `$FF99` | The VBlank hook; copied from bank 2 at boot |
| Hooks | boot, the joypad read on the title and in the run loop, the store's buy routine, the game-over screen, the non-fatal hit at `$4ACC`, and the frame wait at `$7AF8` |

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
menu as if it had never left.

**Scroll and palettes.** The game's scroll writes (ten places) and palette
writes (six) now go to five HRAM bytes (`$FF94` to `$FF98`). The VBlank hook
copies them to the hardware and, on a color console, loads palette RAM when a
theme or shade changed. The game only sets its palettes once, at the title,
and uses only bits 4 and 5 of the sprite attributes, which is what makes the
color conversion safe.

**Menus with the LCD on.** A page is drawn into a 20 x 18 buffer in WRAM
(`$D500`), and `page_flush` sends the tiles that differ from what the window map
holds (a mirror at `$D700`), each one after the same wait for STAT mode 0 or 1
the game's tile routine uses at `$7A9A`. Opening backs up the window map the
same way. Only rows 0-1 of the window map can be on screen before the page
moves up (the HUD in a run; the title has no window), so rows 2-17 are written
first and rows 0-1 in the VBlank that moves the window to the top. Closing
puts the window back in VBlank and restores rows 0-1 before the LCD reaches
them.

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
python3 patch.py "Legion of Evil (Rev 1).gb" -o "Legion of Evil (Rev 1) [Save, color & rumble patch by thisJUSTin816 v1.2].gbc" --ips LegionOfEvil-save.ips
```

`patch.py` refuses any ROM whose md5 it doesn't know, checks every byte it
replaces, and confirms nothing else jumps into the middle of a replaced
instruction. The code is `loe.asm`, assembled by `asm.py`. The tests need
`pip install pyboy pillow`:

```
python3 verify.py "Legion of Evil (Rev 1).gb" "Legion of Evil (Rev 1) [Save, color & rumble patch by thisJUSTin816 v1.2].gbc"
```
