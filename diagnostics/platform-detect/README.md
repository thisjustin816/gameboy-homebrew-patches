# Platform Detect

A Game Boy Color diagnostic that reports the hardware class, then looks for
behavior a Nintendo Game Boy Color never shows. When it finds some, it says the
host is likely an emulator and, where the pattern is known, names it.

It is meant for feature gating and debugging. A game can run the same checks at
startup and hide features that make no sense in a web emulator, such as beaming
over the infrared port.

## Screen

This is the screen in mGBA:

```text
 PLATFORM DETECT

 EMU    LIKELY
 NAME   MGBA

-- SYSTEM ----------
 HW     CGB
 HOST   OTHER
 SGB    NO

-- FF72 FF73 -------
 72 5A>00 A5>00  NO
 73 3C>00 C3>00  NO

-- TELLS -----------
 5 OF 12 FAILED
 72 74 75 6C 56
               V1.4
```

`EMU` is `LIKELY` when any tell fails or a known emulator's signature matches,
and `NO TELLS` otherwise. `NAME` names the signature, or reads `UNKNOWN` (tells
failed, no known signature), `MISTER FPGA` or `NONE`. On CGB the verdicts are
also colored: green for what a Game Boy Color does, red for what it doesn't.

`HW` is DMG, MGB, SGB1, SGB2, CGB or GBA/CGB. A CGB CPU wins over the SGB packet
probe, because a real Super Game Boy never reports one. In DMG mode the screen
shows `HW` and `SGB` only, with `HOST N/A` and `TELLS CGB ONLY`.

`NO TELLS` is not proof of hardware. SameBoy passes every check, because it
behaves like a CGB-E on all of them.

## Host probe

FF72 and FF73 are undocumented CGB registers whose eight bits are readable and
writable. The ROM writes two patterns to each, reads them back, and restores the
original value. `HOST` reads:

- `CGB-LIKE`: both registers return both patterns.
- `BINJGB-LIKE`: both return FF, as binjgb does, which leaves them out of its
  register table.
- `OTHER`: anything else. mGBA ignores the writes and returns 00.

## Tells

Each tell is a register read where SameBoy and Gambatte, the two cores here
most tested against hardware, agree on the Game Boy Color value. The table lists
the emulators that differ, measured with each one's default CGB setup.

| Code | Check | Game Boy Color | Differs in |
|---|---|---|---|
| 72 | FF72 and FF73 round-trip | written value | mGBA, binjgb |
| 74 | FF74 round-trips | written value | mGBA, binjgb |
| 75 | FF75 bits 4-6 round-trip | 8F, then FF | mGBA, binjgb |
| 6C | OPRI after writing 00 | FE | mGBA, binjgb, VBA-M |
| 76 | PCM12 and PCM34 with the APU idle | 00 | binjgb |
| 56 | RP after writing 00 | 2E or 3E | mGBA, binjgb, VBA-M, Gearboy, PyBoy |
| 4F | VBK after writing 00 | FE | GameBoy-Online (from its source) |
| 4D | KEY1 bits 1-6 | set | PyBoy |
| 4C | KEY0 after boot | FF | PyBoy |
| 01 | SB after writing 00 | 00 | PyBoy |
| UN | FF4E and FF57 after writing 00 | FF | VBA-M, Gearboy |
| SGB | SGB packet probe on a CGB | no answer | none by default |

RP reads 02 on the MiSTer Game Boy core, which the ModRetro Chromatic's FPGA
core is built from. That value counts as hardware, so it passes the 56 tell and
shows `NAME MISTER FPGA` when every other check passes. It comes from the
published FPGA source and has not been run here.

The ROM leaves OPRI at 00 after its check, not at the value read first. VBA-M
reads OPRI as FF, and writing that back sets bit 0, which VBA-M takes as a
switch to the DMG palette.

## Signatures

`NAME` checks these in order:

| Match | Signature |
|---|---|
| BINJGB | FF72/FF73 and PCM12/PCM34 read FF |
| MGBA | FF72 keeps its old value after both writes, FF75 reads 8F after writing FF |
| PYBOY | KEY0 reads FB |
| GEARBOY | FF57 keeps a written value |
| VBA-M | FF4E keeps a written value |
| GAMBATTE | FEA0-FEA3 read 08 01 EF DE, from the fixed OAM dump its no-BIOS start loads |
| GB ONLINE | VBK reads 00 after writing 00 (from its source) |

## Build

Requires GBDK-2020 4.5.0.

```sh
make GBDK_HOME=/path/to/gbdk
```

The output is `platform-detect.gbc`.

SDCC drops a volatile read that follows a write to the same address and reuses
the written value, so each write and read-back runs in a small asm routine.
Builds before 1.3 compiled the FF72/FF73 probe that way and reported `CGB-LIKE`
on every host.

## Checks

With PyBoy installed:

```sh
python3 tests/smoke.py
```

The smoke test cold-boots the ROM in forced CGB and DMG modes, renders 240
frames in each, checks the text contrasts with the background, and reads the
screen back from the tile map. In CGB mode it expects `EMU LIKELY`,
`NAME PYBOY` and both FF72/FF73 rows `OK`, and the 1.2 ROM fails it. In DMG
mode it expects `HW DMG` and `CGB ONLY`.

The tells and signatures were measured by running a register dump ROM and this
build headless in SameBoy 26a56bd, Gambatte-Speedrun core 5a41a68, mGBA 143adf5,
binjgb 1662111, VBA-M f95b39e and Gearboy 4975fa5 through their libretro cores
or C APIs, and in PyBoy 2.8.1. GameBoy-Online values come from reading its
source. None of this has run on a Game Boy Color or a Chromatic.

Verified build v1.4:

- Size: 32 KiB
- Header title: `PLATDETECT`
- CGB flag: CGB compatible (`80`)
- MD5: `517a8dbdbf48d0a45dcc262e9913a959`
- SHA-256: `c9541fa74a1b9a38a7f93cfbf6bbeb6a68235797359e1c823519cee483531b19`

## References

- Pan Docs, undocumented CGB registers: https://gbdev.io/pandocs/CGB_Registers.html
- SameBoy: https://github.com/LIJI32/SameBoy
- binjgb emulator core: https://github.com/binji/binjgb/blob/main/src/emulator.c
- ModRetro Chromatic FPGA core: https://github.com/ModRetro/oss-chromatic-console-fpga/blob/main/esp32t/src/rtl/EMU/CORE/gb.v
