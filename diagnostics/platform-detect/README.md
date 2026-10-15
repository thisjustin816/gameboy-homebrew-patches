# Platform Detect

A small Game Boy Color diagnostic for distinguishing current binjgb behavior
from CGB-compatible hardware and emulators that implement the undocumented CGB
registers at FF72 and FF73.

The ROM reports the normal Game Boy hardware class first, then runs a reversible
FF72/FF73 probe only in CGB mode. It is intended for feature gating and debugging,
not for identifying a ModRetro Chromatic by name.

## What the probe does

FF72 and FF73 are undocumented CGB registers whose eight bits are readable and
writable on Game Boy Color hardware. The diagnostic saves each original value,
writes two patterns, reads them back, and restores the original value.

The current binjgb source does not implement FF72 or FF73 in its I/O register
list. Its fallback for an unrecognized I/O read is FF. As a result, the two
round-trip tests fail with FF reads. The ModRetro Chromatic FPGA source used by
its compiled Game Boy core explicitly implements FF72 and FF73 as read/write
registers, so it follows the CGB-like path.

The result names are intentionally conservative:

- `BINJGB-LIKE`: both registers fail both patterns and return FF.
- `CGB-LIKE`: both registers round-trip both patterns.
- `OTHER/QUIRK`: the CGB probe produces some other combination.
- `N/A`: the ROM is not running in CGB mode, so the CGB-only probe is skipped.

`BINJGB-LIKE` means this fingerprint, not every browser emulator. Another web
emulator can implement the CGB registers correctly, and another emulator can
share binjgb's missing-register behavior. If a web wrapper is under application
control, an explicit wrapper-to-ROM signature is stronger than emulator
fingerprinting.

## Why this is useful

A game can use the same probe at startup and remember the host class. Features
that do not make sense in a binjgb web build can then be hidden or disabled. For
example, a game that can beam a puzzle over the Game Boy Color infrared port can
avoid offering that action when the host is `BINJGB-LIKE` while still offering
it on compatible physical hardware.

Do not use the probe to claim `Chromatic`. Public Chromatic FPGA and boot-ROM
sources do not expose a supported cartridge-visible Chromatic identity register,
and the boot ROM deliberately hands control to games with the standard CGB/GBA
register conventions.

## Screen

The ROM shows:

- detected hardware class: DMG, MGB, SGB1, SGB2, CGB, or GBA/CGB;
- host verdict;
- original FF72/FF73 values;
- the two write/read results for each register;
- `OK` or `FAIL` for each register.

Example on a CGB-like emulator:

```text
PLATFORM DETECT 1.1
HW: CGB
HOST: CGB-LIKE
72 00 5A>5A A5>A5 OK
73 00 3C>3C C3>C3 OK
```

## Build

Requires GBDK-2020 4.5.0.

```sh
make GBDK_HOME=/path/to/gbdk
```

The output is `platform-detect.gbc`.

## Checks

With PyBoy installed:

```sh
python3 tests/smoke.py
```

The smoke test cold-boots the ROM in forced CGB and DMG modes, renders 240 frames
in each, checks that neither screen is blank, and reports the FF72/FF73 values.
PyBoy 2.8.1 follows the CGB-like path in CGB mode and the ROM skips the probe in
DMG mode.

Verified build v1.1:

- Size: 32 KiB
- Header title: `PLATDETECT`
- CGB flag: CGB compatible (`80`)
- MD5: `eb82e2dbe3f89d5b3f422dd7d2a2da46`
- SHA-256: `99caa2b35d26dbbaee9dc453b9742f9155a5eff31df4a4cc71e511bb933e52d8`

The binjgb verdict is supported by source inspection of current binjgb's I/O
register table and default unknown-I/O read behavior. The ROM has not yet been
run in binjgb or on physical hardware in this build.

## References

- Pan Docs, undocumented CGB registers: https://gbdev.io/pandocs/CGB_Registers.html
- binjgb emulator core: https://github.com/binji/binjgb/blob/main/src/emulator.c
- ModRetro Chromatic FPGA core: https://github.com/ModRetro/oss-chromatic-console-fpga/blob/main/esp32t/src/rtl/EMU/CORE/gb.v
- ModRetro Chromatic CGB boot ROM: https://github.com/ModRetro/oss-chromatic-console-fpga/blob/main/esp32t/src/rtl/EMU/CORE/BootROMs/cgb_boot.asm
