# Disney Afternoon Collection for Game Boy

Builds one Game Boy ROM holding the four Capcom Disney Afternoon games that came out
on Game Boy: DuckTales, DuckTales 2, TaleSpin and Darkwing Duck. It boots to a splash
with the collection's logo and a blinking PRESS START, then a menu showing each game's
logo above a list of the four games.

| Where | Button | Does |
|---|---|---|
| Splash | A or START | Opens the menu |
| Menu | Up, down | Picks a game |
| Menu | A or START | Starts it |

To get back to the menu, power cycle.

No ROMs or PC files are included. Bring your own:

| File | md5 |
|---|---|
| DuckTales (USA) | `785441d3d75913393807b10b3194dc48` |
| DuckTales 2 (USA) | `b4e5876c5acedd12b62e25a12973a4ae` |
| TaleSpin (USA) | `26c65da146faa09505c554447792e493` |
| Darkwing Duck (USA) | `7d776329212fa7cc2b00c5a46f06dd92` |
| `bundleMain.mbundle` from the PC Disney Afternoon Collection | `c20f738bd6e913e2b669cb15d87d697c` |

## Build

Needs Python 3 with Pillow, NumPy and PyBoy (`pip install pyboy pillow numpy`). PyBoy
is used to read DuckTales 2's font from its title screen, and the menu's frame and
arrow from DuckTales' LAND SELECT screen.

```
python3 build.py DuckTales.gb DuckTales2.gb TaleSpin.gb DarkwingDuck.gb bundleMain.mbundle -o "Disney Afternoon Collection (GB).gb"
```

The script refuses any input whose md5 isn't listed above, and checks the font and
frame it reads from the games by md5 as well. `--screens DIR` also writes the five
screens as PNGs.

## Where it runs

The result is a 2 MiB MBC1 cart without RAM. It needs an emulator or flash cart that
handles MBC1's mode 1 on a large ROM: PyBoy, mGBA, SameBoy, BGB,
Gambatte and EverDrive-class carts do. Carts that only do MBC5 banking won't run it.

## How it works

- Each game sits at the start of its own 512 KiB quarter of the ROM. None of them has
  more than 8 banks, and all four switch banks only through the `$2000` register.
- DuckTales holds quarter 0. Its entry point now jumps to a 15-byte hook in the unused
  padding at `$0061`, which saves the registers the boot ROM left and runs the menu
  from DuckTales' empty bank 4.
- The splash and the four menu screens are pictures in banks 5 to 9, one per screen.
  Moving the cursor loads the next picture. On the splash, the menu blanks the
  PRESS START row every 30 frames and puts it back 30 frames later, writing the map
  during VBlank.
- `pictures.py` draws the screens from the PC logos in the Game Boy's four shades:
  - Each logo is sorted into color families before it is scaled down, so colors of
    the same brightness stay apart. A thin outline wins any pixel it covers a quarter
    of, so it stays unbroken.
  - The collection logo is rebuilt from its layers in the PC files. The triangle is
    drawn as a clean shape with a black and white edge, and the Mickey shape behind
    the letters comes from the triangle's own layer. Each word is the art's white
    or yellow letter fill, scaled down, with a black outline and drop shadow drawn
    at Game Boy size. THE, AFTERNOON and COLLECTION are drawn 25% bigger than in
    the original so they stay readable, with at least a pixel between letters.
  - The DuckTales logos keep their red-to-yellow fill as an ordered dither across
    three shades.
  - Every game logo gets the same "Disney's", taken from the DuckTales logo.
  - The menu's frame and arrow are DuckTales' own, from its LAND SELECT screen, and
    the text is DuckTales 2's font.
- To start a game, the menu puts the display and interrupt registers back the way the
  boot ROM leaves them. A stub in HRAM then writes the game's quarter to the `$4000`
  register and sets mode 1, so the game's own bank 0 appears at `$0000`. It clears
  WRAM, restores the CPU registers the boot ROM left, and jumps to the game's entry
  point.
- The header keeps Capcom's licensee code, so a Game Boy Color gives every game the
  same palette it gives the original cart.

## Testing

`verify.py` checks a built ROM in PyBoy:

```
python3 verify.py "Disney Afternoon Collection (GB).gb" DuckTales.gb DuckTales2.gb TaleSpin.gb DarkwingDuck.gb bundleMain.mbundle
```

- The ROM is exactly what `build.py` makes, its header and checksums are valid, and each
  quarter holds its game byte for byte, apart from the entry point, the hook and the
  header in quarter 0.
- The splash and the four menu screens appear pixel for pixel as built, PRESS START
  blinks every 30 frames, the cursor wraps both ways, and other buttons do nothing.
- Each game, launched from the menu, is played for about three minutes of scripted
  input next to the stock ROM with the same input. Every frame must match, on both DMG
  and Game Boy Color. The multicart starts a few frames later than the stock ROM (the
  launcher clears WRAM and waits for line 0), and the test measures that delay on the
  attract mode first.

As a control, a build that launches Darkwing Duck without switching MBC1 to mode 1
hangs, and `verify.py` reports the hang as a failure.

A trace of about five minutes of play per stock game shows each one writing only to
the `$2000` bank register, with banks 0 to 7. A write to `$4000` or `$6000` would break
this layout. The stores to those ranges that a byte scan finds are graphics data, apart
from a sound routine in DuckTales 2 and Darkwing Duck that stores to `$0004`-`$0007`.
That range is MBC1's RAM enable, which does nothing on a cart without RAM.

The menu hasn't been tested on real hardware.
