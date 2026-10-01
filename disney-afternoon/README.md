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

The result is a 2 MiB MBC1 cart without RAM. Starting any game but DuckTales needs
MBC1's mode 1 on a large ROM, where the upper bank bits also pick the bank at `$0000`.
Accurate emulators do this; the collection runs fully in PyBoy and SameBoy.

Most flash carts don't. On an EverDrive GB, DuckTales starts and the other three go
back to the splash: its MBC1 leaves bank 0 at `$0000` in mode 1, as its mapper
support doesn't cover MBC1 multicarts. Carts that only do MBC5 banking can't run it
either, since MBC5 always shows bank 0 at `$0000`.

## ChisFlash MAX build

For a ChisFlash MAX 16-in-1 cart, `chisflash.py` builds an 8 MiB flash image with the
same splash and menu:

```
python3 chisflash.py DuckTales.gb DuckTales2.gb TaleSpin.gb DarkwingDuck.gb bundleMain.mbundle -o "Disney Afternoon Collection (ChisFlash MAX).gb"
```

That cart only does MBC5 banking, but its CPLD can switch the whole cart to any of
its 16 slots, so it doesn't need MBC1's mode 1:

- The menu slot, at the start of the flash, holds a 256 KiB MBC5 ROM: its own boot
  code in bank 0, and the menu and screens in banks 4 to 9 as in the collection.
- The four games sit in slots 0 to 3, at 1, 2, 4 and 6 MiB, each converted to MBC5.
  The conversion changes the header's cartridge type, plus one patch in TaleSpin.
  All four write banks 1 to 7 to the `$2000` register, which MBC5 treats as MBC1
  does. TaleSpin also writes bank 0, which MBC1 turns into bank 1 and MBC5 doesn't.
  At `$0E97` it reads level data from the bank held in `$CD9C`, which can be 0, and
  banks 0 and 1 hold different bytes there. So its bank-switch routine at `$02C7` now
  jumps to a copy in bank 0's free padding at `$0070` that turns 0 into 1, leaving A
  and the flags as they were. On MBC1 the patch changes only timing.
- Every game, and the menu, writes a bank number before it first reads `$4000`-`$7FFF`,
  so none of them depends on the bank the mapper holds when it starts. The stub maps
  bank 1 anyway, but a CPLD that resets the console into the slot, or a power cycle,
  leaves whatever bank the cart's MBC5 mapper holds.
- Picking a game copies a stub to HRAM, as the cart's own menu does. It writes `$50`
  to `$4000` to arm the CPLD, the slot to `$B000`, maps bank 1, then writes 1 to
  `$A000`, which switches the cart to the slot, and 0 to `$4000` to disarm it. It then
  starts the game the way the boot ROM leaves it: WRAM cleared, the boot ROM's
  registers put back, and a jump to `$0100`, as the MBC1 collection's launcher does.
  The published MAX v1.22 CPLD arms on bit 6 of the `$4000` write, while the 8M CPLD,
  and the menu ChisFlash ships for the MAX cart, arm on bit 4, so the stub sets both.
  The sequence and the warm start follow that shipped menu, from
  [ChisFlash-MBC5](https://github.com/moribaka/ChisFlash-MBC5).

  The first version of this build armed on bit 6 alone and then waited for the CPLD
  to reset the console into the slot, as the
  [chisflash-max16-menu](https://github.com/dmcclung/chisflash-max16-menu) project
  does. On a GBMake 32 MiB ChisFlash cart the menu came up, but every game went to a
  white screen: the stub's wait loop, with no reset coming.

The image ends after slot 3. Write it from the start of the flash; slots 4 to 15 are
left as they were.

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
    at Game Boy size. THE and AFTERNOON are drawn 25% bigger than in the original
    so they stay readable, and COLLECTION's banner 10% bigger about its own center,
    with at least a pixel between letters.
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

`verify_chisflash.py` checks a ChisFlash image the same way:

```
python3 verify_chisflash.py "Disney Afternoon Collection (ChisFlash MAX).gb" DuckTales.gb DuckTales2.gb TaleSpin.gb DarkwingDuck.gb bundleMain.mbundle
```

PyBoy has no ChisFlash CPLD, so it checks the parts:

- the menu ROM's screens, blink and cursor as an MBC5 cart;
- that picking each game leaves the stub in HRAM with that game's slot;
- that each game, launched from the menu, matches its reference on every frame of the
  scripted play, after the start-up delay the warm start adds. PyBoy can't switch
  slots, so at the launch the check puts the game's ROM where the menu's was, which is
  what the stub's `$A000` write does on the cart. With the first version's stub, the
  screen stays white;
- that each converted game matches its stock ROM on every frame of the same scripted
  play, on DMG and Game Boy Color. TaleSpin is matched against the stock ROM with the
  same patch, as the patch shifts its timing a little;
- that TaleSpin's level-data read gets bank 1 when it asks for bank 0. PyBoy's
  scripted play never reaches that case, so the check sets `$CD9C` to 0 before one
  read. As a control, TaleSpin converted without its patch gets bank 0 there;
- that each game, padded to its slot as on the cart, and the menu come up the same
  with bank 0, 2, 3 or 4 to 9 mapped at power-on instead of bank 1. As a control, a
  copy of DuckTales 2 with its first bank write removed comes up differently.

The CPLD's switch itself, and which arm bit a given cart's CPLD takes, have only been
checked against the register sequence and the shipped menu, not on the cart.

A trace of about five minutes of play per stock game shows each one writing only to
the `$2000` bank register, with banks 0 to 7. A write to `$4000` or `$6000` would break
this layout. The stores to those ranges that a byte scan finds are graphics data, apart
from a sound routine in DuckTales 2 and Darkwing Duck that stores to `$0004`-`$0007`.
That range is MBC1's RAM enable, which does nothing on a cart without RAM.

The menu hasn't been tested on real hardware.
