# Disney Afternoon Collection for Game Boy

Builds one Game Boy ROM holding the four Capcom Disney Afternoon games that came out
on Game Boy: DuckTales, DuckTales 2, TaleSpin and Darkwing Duck. It boots to a splash
with the collection's logo, then a menu showing each game's logo.

| Where | Button | Does |
|---|---|---|
| Splash | A or START | Opens the menu |
| Menu | Up, down | Picks a game |
| Menu | A or START | Starts it |
| Anywhere in a game | A+B+SELECT+START | Back to the menu, on that game |

TaleSpin already had this combo as a soft reset. It now goes to the menu as well.

No ROMs or PC files are included. Bring your own:

| File | md5 |
|---|---|
| DuckTales (USA) | `785441d3d75913393807b10b3194dc48` |
| DuckTales 2 (USA) | `b4e5876c5acedd12b62e25a12973a4ae` |
| TaleSpin (USA) | `26c65da146faa09505c554447792e493` |
| Darkwing Duck (USA) | `7d776329212fa7cc2b00c5a46f06dd92` |
| `bundleMain.mbundle` from the PC Disney Afternoon Collection | `c20f738bd6e913e2b669cb15d87d697c` |

## Build

Needs Python 3 with Pillow and PyBoy (`pip install pyboy pillow`). PyBoy is used to
read DuckTales 2's font from its title screen.

```
python3 build.py DuckTales.gb DuckTales2.gb TaleSpin.gb DarkwingDuck.gb bundleMain.mbundle -o "Disney Afternoon Collection.gb"
```

The script refuses any input whose md5 isn't listed above, and checks every byte it
patches in a game before patching it.

## Where it runs

The result is a 2 MiB MBC1 cart with 8 KiB of RAM and no battery. It needs an emulator
or flash cart that handles MBC1's mode 1 on a large ROM: PyBoy, mGBA, SameBoy, BGB,
Gambatte and EverDrive-class carts do. Carts that only do MBC5 banking won't run it.

## How it works

- Each game sits at the start of its own 512 KiB quarter of the ROM. None of them has
  more than 8 banks, and all four switch banks only through the `$2000` register.
- DuckTales holds quarter 0. Its entry point now jumps to a 15-byte hook in the unused
  padding at `$0061`, which saves the registers the boot ROM left and runs the menu
  from DuckTales' empty bank 4. The menu copies them to cart RAM, along with the I/O
  registers a game may change, so a game started a second time gets the same start as
  the first.
- The splash and the four menu screens are pictures in banks 5 to 9, one per screen.
  Moving the cursor loads the next picture.
- To start a game, the menu puts the display, interrupt and I/O registers back the way
  the boot ROM left them and clears OAM and HRAM. A stub in HRAM then writes the game's
  quarter to the `$4000` register and sets mode 1, so the game's own bank 0 appears at
  `$0000`. It clears WRAM, restores the CPU registers the boot ROM left, and jumps to
  the game's entry point.
- For the combo, each game's joypad routine, which runs once a frame, gets a jump into
  code in the free padding of its bank 0:

  | Game | Patched at | How |
  |---|---|---|
  | DuckTales | `$3791` | the routine's last three instructions jump to a check of the held buttons |
  | DuckTales 2 | `$03C1` | the same |
  | TaleSpin | `$032F` | the game's own soft reset on the combo now jumps to the menu |
  | Darkwing Duck | `$0381` | the same as DuckTales |

  The check leaves A and the flags as the replaced instructions did. On the combo it
  copies a stub to HRAM that maps quarter 0 back in, and the menu takes over with that
  game highlighted, silences the sound and restores the saved registers.
- The header keeps Capcom's licensee code, so a Game Boy Color gives every game the
  same palette it gives the original cart.

## Testing

`verify.py` checks a built ROM in PyBoy:

```
python3 verify.py "Disney Afternoon Collection.gb" DuckTales.gb DuckTales2.gb TaleSpin.gb DarkwingDuck.gb bundleMain.mbundle
```

- The ROM is exactly what `build.py` makes, its header and checksums are valid, and each
  quarter holds its game byte for byte, apart from the combo patch, and in quarter 0
  the entry point, the hook and the header.
- The splash and the four menu screens appear pixel for pixel as built, the cursor
  wraps both ways, and other buttons do nothing.
- The combo on each title screen and in the middle of play brings back the menu screen
  for that game, pixel for pixel. The in-play checks fail on a build without the patch.
- Each game, launched from the menu, is played for about three minutes of scripted
  input next to the stock ROM with the same input. Every frame must match, on both DMG
  and Game Boy Color. The multicart starts a few frames later than the stock ROM (the
  launcher clears WRAM and waits for line 0), and the test measures that delay on the
  attract mode first. A game started again after the combo must match stock the same way. The script
  never presses SELECT, so it never makes the combo.

As a control, a build that launches Darkwing Duck without switching MBC1 to mode 1
hangs, and `verify.py` reports the hang as a failure.

A trace of about five minutes of play per stock game shows each one writing only to
the `$2000` bank register, with banks 0 to 7. A write to `$4000` or `$6000` would break
this layout. The stores to those ranges that a byte scan finds are graphics data, apart
from a sound routine in DuckTales 2 and Darkwing Duck that stores `$80`, `$00`, `$03`
and `$07` to `$0004`-`$0007`. That range is MBC1's RAM enable, and none of those values
enables it, so cart RAM stays off while a game runs.

The menu hasn't been tested on real hardware.
