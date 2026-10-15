# Platform Detect Status Handoff

## Current promoted build

Version: 1.0
Date: 2026-10-15
ROM: `platform-detect.gbc`
Size: 32768 bytes
Header title: `PLATDETECT`
CGB flag: `80` (CGB compatible)
Cartridge type: `00` (ROM only)
MD5: `084ff7cc4c81deb2e7366acd1a1990c6`
SHA-256: `5466638a310f657060d9a0a7f6503fa7b62a36a50487f8d5ce3b42b5de69de90`
Toolchain: GBDK-2020 4.5.0

## What is proven

- The source builds cleanly with GBDK-2020 4.5.0.
- PyBoy 2.8.1 cold-boots and renders the ROM in forced CGB mode.
- PyBoy 2.8.1 cold-boots and renders the ROM in forced DMG mode.
- In CGB mode, the ROM probes FF72 and FF73 with two write/read patterns and
  restores the original values afterward.
- In DMG mode, the ROM skips the CGB-only host probe and reports `HOST: N/A`.
- Current binjgb source omits FF72/FF73 from its implemented I/O register list
  and returns FF for unrecognized I/O reads, which matches the diagnostic's
  `BINJGB-LIKE` classifier.
- The ModRetro Chromatic FPGA source compiled by its Gowin project implements
  FF72 and FF73 as CGB read/write registers, which matches the diagnostic's
  `CGB-LIKE` path.

## What is not yet proven

- This v1.0 ROM has not yet been executed in binjgb itself.
- This v1.0 ROM has not yet been executed on a physical ModRetro Chromatic or
  original Nintendo hardware.
- `BINJGB-LIKE` is an implementation fingerprint, not a universal web-emulator
  detector and not a cryptographic identity for binjgb.
- There is no supported cartridge-visible Chromatic identity API known from the
  public FPGA and boot-ROM sources reviewed for this diagnostic.

## Source map

- `src/main.c`: hardware reporting, FF72/FF73 probe, on-screen verdict.
- `Makefile`: reproducible GBDK-2020 build.
- `tests/smoke.py`: forced CGB/DMG PyBoy boot and render smoke checks.
- `README.md`: behavior, limitations, build instructions, references, hashes.
- `CHANGELOG.md`: diagnostic version history.

## Next frontier

Run `platform-detect.gbc` in the exact binjgb web build used by PictoCode and on
physical Chromatic hardware. Record the screen values. If PictoCode controls its
web wrapper, prefer adding an explicit wrapper signature later and keep this
FF72/FF73 fingerprint as a fallback for stock binjgb.
