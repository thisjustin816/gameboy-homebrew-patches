# Roguecraft GB: resume a run, honest chest counts, no vanishing enemies

A patch that lets you stop a Roguecraft GB run and pick it up later. It also
fixes two bugs in how the game counts chests, and one that makes enemies go
invisible after you look at the mini-map. The title screen shows `v1.000b` to
mark the patched build and its revision.

The stock cartridge already has battery-backed save RAM, and the game already
has almost everything a run save needs: a run slot, a `RESUME GAME` option on
the START GAME menu, and a resume that restarts the saved floor with your hero
carried over. It just never writes that slot, so the only thing that survives a
power cycle is the achievements. This patch adds the missing write.

## Supported release

| Release | md5 |
|---|---|
| Roguecraft GB v1.0000 (Rocketship Park) | `6de80f13b9ab562de2227ea5dd818275` |

`patch.py` refuses any other ROM.

## How it plays

- **You don't have to do anything to save.** Arriving on a new floor saves the
  run: the floor you just reached, with your hero as you arrived on it,
  hearts included.
- **To resume**, pick START GAME. When a run is saved it shows
  `RESUME GAME` / `NEW GAME` (the game's own menu, with the title's menu
  cleared away while it's up). Resume puts you at the start of the saved
  floor, with a freshly generated layout.
- **Switching off or quitting mid-floor** (START ×2) sends you back to the start
  of that floor next time. Anything picked up on that floor is lost with it.
  That's deliberate, because it means quitting can't re-roll a floor and keep
  the loot.
- **Dying ends the run.** The game-over screen already clears the run slot,
  and `RESUME GAME` disappears. The patch adds nothing here.
- **Nothing is saved on the first floor**, because there is nothing to resume
  there. Restarting The Wilderness is just a new game.
- **Your existing save file keeps working.** The patch doesn't change the save
  format, so achievements carry over, and there's no run to resume until you
  reach floor two. Most emulators and flash carts look for a save named after
  the ROM, so rename your old `.sav` to match the patched ROM's filename.
- **Starting a NEW GAME over a saved run** keeps the old run until the new one
  reaches floor two, and then replaces it. If you quit the new run on its first
  floor, the old run is still offered. If you die there, the game-over screen
  clears it, as it would any run.

## What the patch changes

The game is built with GB Studio. Its save system keeps whole-game-state slots:
slot 0 is the run (GB Studio variable 75 is the floor number) and slot 1 the
achievements. Each of the game's eleven floors has a script, and each script
opens with a native call to the floor setup in bank 2 at `$401B`. That setup
loads the hero back out of the game variables, the way the previous floor's
exit left them.

The patch repoints those eleven native calls at new code in ROM bank 27, which
is empty in the stock ROM:

- **`floor_start`** (floors 2-11) runs the stock setup exactly as the VM would
  have, then calls the game's own `data_save` for slot 0.
- **`run_start`** (floor 1, *The Wilderness*) first zeroes the floor counter,
  then runs the stock setup and saves nothing. The floors come in a fixed order
  and *The Wilderness* is only ever the first, so the counter has always been 0
  there. But START GAME's resume check loads the saved floor number into it,
  and choosing NEW GAME from that menu doesn't clear it. The stock game never
  noticed, because it never saved a later floor for the check to load. With a
  real run saved, a new game would have inherited the old run's floor number.
  Resetting it on the first floor restores the value the game always had there.

| ROM range | Bytes | What |
|---|---|---|
| `$014E`-`$014F` | 2 | global checksum |
| 11 floor scripts | 2 each | native-call target: bank 2 `$401B` → bank 27 |
| bank 27 `$4000`-`$414E` | 335 | `run_start`, `floor_start`, `count_chest`, `chest_opened`, `chest_spawn`, `map_open`, `map_hide`, `map_close`, and the GBVM script `resume_menu_hide` |
| bank 4 `$56CE`-`$56DA` | 13 | generator's `chests_total += 1` → call to `count_chest` |
| bank 2 `$644A`-`$6456` | 13 | open-chest `chests_found += 1` → call to `chest_opened` |
| bank 2 `$44F5`-`$4507` | 19 | room entry's `if chest bit: chest hp = 2` → call to `chest_spawn` |
| bank 25 `$6037`, `$609D` | 3 each | the map script's native calls: map-open → `map_open`, map-close → `map_close` |
| bank 2 `$58D6`-`$58DD` | 8 | the map-open's call to hide one entity → `map_hide` |
| bank 11 `$6978`-`$6987` | 16 | title background tile, row 17 column 19: the version's last `0` → `b` |
| bank 22 `$67DD`-`$67E0` | 4 | the resume menu's box move → a VM call to `resume_menu_hide` |

The fixes also use 23 bytes of work RAM, `$DD37`-`$DD4D`: a byte per entity
for the mini-map, then a bit per room for the chests. That's past the end of the
game's own variables, no instruction in the ROM refers to it, it isn't part of
any save, and in testing the stack never got closer than 106 bytes to it.
`patch.py` checks the ROM for references before using it.

The cartridge header is untouched. It already declares MBC5 + rumble + RAM +
battery, with 32 KB of RAM.

Saving costs 2 frames, during the fade into each floor's title card.

## Chest fixes

Each floor is a 5×5 grid of rooms, and each room has a word of item bits saying
what is still in it. Bit 1 is its chest. Taking an item clears its bit, so it
stays gone when you come back. The chest **total** is counted as each floor is
generated, one for every room whose chest bit is set; chests **found** goes up
as each one opens. The end screen shows `CHESTS: found-total`.

**Chests that could never be found.** The last floor, *It Waits Dreaming*, is a
single boss arena. The generator still lays out an ordinary floor behind it,
which nobody can ever walk into (the arena has no exits, and item spawning is
switched off on that floor anyway), and it counted that floor's chests. So
every run's total came up short by however many chests that hidden layout had.
In testing, entering the last floor added 7. That fits a clean run reading
79 of 87, and a run with one secret room missed reading 84 of 94, since secret
rooms carry chests. The patch doesn't count chests while the last floor is
generated, so a run where you find everything reads found = total.

**Chests that could be opened twice.** An opened chest turns into its gold, in
the same entity slot, and the room's chest bit stays set until that gold is
picked up. But entering a room spawns everything whose bit is set afresh, and
the stock game always spawned the chest shut. If you walked away without the
gold, the chest stood there shut again next time in, and opening it counted a
second time and paid out again.

The patch notes, for each room of the floor, whether its chest has been opened.
Coming back to a room whose chest you opened, you find **its gold still
waiting** instead of a shut chest. Pick it up whenever you like, and the chest
counts once. It's shown as the gold on its own, without the open chest, because
the open chest is drawn on the floor when the chest opens, not saved with the
room.

Each time you enter a room, the game lays its items out again on a fixed set of
spots, in a fixed order, so the gold usually comes back where the chest stood.
If you've taken one of the room's other items, such as its heart, the gold can
move up to an earlier spot, and coming in from a neighboring room can now and
then push it one spot along. That's the game's own rule for every item, and the
gold lands wherever the stock game would put the chest.

## Mini-map fix

**The bug.** Hold B for the mini-map, let go, and an enemy that was under the
map can stay invisible for a second or two. It's still there, and it can still
hit you. It comes back by itself, or on its next attack.

**Why.** The engine's own hiding of sprites under the window is switched off
in this game, so the game hides them itself. Opening the map gives every
living enemy, item and hero in the room cells it covers (the bottom-right 3×3)
an animation set whose only frame is empty. Closing the map asks the game's
animation refresh to give each one its normal set back.

That refresh skips every enemy for 60 game ticks after any attack, yours or
theirs, so that attack and hurt animations get to finish. That's about two
seconds, because the game is often too busy to run every frame. Close the map
inside that window and the enemies it covered keep the empty set until the
window runs out. The hero isn't held back like that, which is why you
reappear and the enemy next to you doesn't. The enemy can even walk out from
under the map while it's still invisible, because walking reuses its current
set.

**The fix.** The patch wraps the map's open, hide and close code. Opening
records which entities it hid and which empty frame each was given. Closing
first runs the stock close as before. Then, for each entity it hid that still
has its empty set, it runs the game's own refresh once more with the
post-attack lock lifted for that one call, and puts the lock back straight
after. That covers enemies and items. An enemy that got a new set while the
map was up, for example by attacking, is left as it is. So is everything
the map didn't hide. When there's been no attack in the last couple of
seconds, the patched game plays exactly as stock, frame for frame.

## Title screen

The title screen's version reads `v1.000b` instead of `v1.0000`, so you can
tell the patched build from stock at a glance. The letter is the patch's
revision, and each new revision takes the next one.

The version isn't text: it's drawn into the title's background image, in the
bottom-right corner. The patch redraws the one tile that holds the last digit,
keeping the artwork around it. GB Studio shares identical tiles across an
image, so `patch.py` checks that no other cell of the title uses that tile.
Nothing outside the title screen uses it.

## Resume menu

With a run saved, START GAME opens a `RESUME GAME` / `NEW GAME` menu in a box
along the bottom of the screen. On stock, the title's own menu stays up around
it: `START GAME`, `ACHIEVEMENTS` and `INSTRUCTIONS` above the box, and `HIGH
SCORES`, `CREDITS` and the chicken under it. The stock game never saves a run
to resume, so it never shows this menu.

The patch hides the title's menu (one sprite actor for all five entries) and
the chicken while the menu is up. Hidden, they can't show through the box on
any device. The box, its text and its cursor are as stock, and so are the
torches and the title art above it. The menu script's move of the box into
place becomes a call to a short GBVM script in bank 27, which hides the two
actors and then makes that move itself. Every way out of the menu loads another
scene, and B reloads the title with its menu back.

## Building and checking

```
python3 patch.py Roguecraft_GB.gbc -o Roguecraft_GB-save.gbc --ips Roguecraft-save.ips
python3 verify.py Roguecraft_GB.gbc Roguecraft_GB-save.gbc
```

`verify.py` (PyBoy) boots cold with scripted input and checks:

1. only the bytes above differ from stock, and the header is untouched;
2. floor 1 matches stock at every sampled frame, saves nothing, and reads floor 0;
3. arriving on floor 2 saves the run with the hero's real hearts; resuming
   after a power cycle restores the same floor and hearts (twice); nothing
   outside the run slot changes, so achievements are untouched;
4. quitting keeps the run; NEW GAME zeroes the counter, saves nothing on its
   first floor, and the older run is still offered after a power cycle;
5. dying on a resumed run clears it, and after a power cycle START GAME goes
   straight to hero select;
6. every one of floors 2-11 runs `floor_start` and saves its own number;
7. the last floor adds nothing to the chest total (stock adds its hidden
   layout's chests), and an ordinary floor adds exactly what stock does;
8. a chest opened and left with its gold on the floor: coming back, the gold is
   still there (stock shuts the chest again and counts it twice); it opened
   once and counts once, and walking over the gold picks it up and finishes
   the room's chest;
9. opening a chest and picking up its gold straight away works exactly as
   stock: the same room items and count;
10. an enemy the mini-map covered is drawn again as soon as the map shuts. The
    check walks into floor 1's room (2,1), where a tentacle monster stands
    under the map, and toggles the map twice. With no recent attack, patched
    and stock match frame for frame. With the post-attack lock running, stock
    leaves the monster invisible (the bug) and the patch doesn't, and the lock
    keeps running for everything else;
11. a save file made by the stock game loads exactly as on stock: the same game
    variables at the title, the same START GAME screen, and the cartridge left
    alone;
12. the title screen's corner reads `v1.000b`, drawn pixel by pixel in the
    version's own color on its own background, and every other pixel of the
    title matches stock;
13. with a run saved, START GAME's menu box is as stock's, with the cursor on
    each choice in turn; none of the title menu's or the chicken's sprites is
    in OAM while it's up, and no sprite reaches the box; the other sprites and
    the screen above the box match stock with those two actors hidden by hand;
    and B goes back to the full title menu, as on stock.

Checks 7-10 run against the stock ROM too, as a control: each one shows the
bug on stock and its absence on the patched ROM. Check 12 reads `v1.0000` from
the stock title the same way, to show it reads the corner correctly.

No scripted player gets through a floor. Runs on later floors come from the
game's own `data_save` called mid-run, and each floor is entered through the
game's own resume path. That exercises every floor script, but not the walk
from one floor into the next.

For check 10, the lock is set the way an attack sets it, which avoids scripting
a fight. Separately, random play with lots of map toggles in five rooms, one of
them next to a monster so real attacks happen, found 32 cases of an enemy left
invisible after the map closed on stock (up to 95 frames), and none on the
patched ROM.

### Known, not fixed

If an enemy under the map attacks while the map is up, its attack animation
replaces the empty set, and it draws over the map until the attack finishes.
This is stock behavior, left alone.
