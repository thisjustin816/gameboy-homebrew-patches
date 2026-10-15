# Changelog

## v1.1

- Fix a blank white screen on real CGB hardware and emulators that start with
  white palettes: the ROM now sets its own black-on-white text palette.
- The smoke test now checks that the text contrasts with the background.

## v1.0

- Add DMG, MGB, SGB, CGB, and GBA/CGB hardware reporting.
- Add reversible FF72 and FF73 CGB register probes.
- Report CGB-like, binjgb-like, or other/quirk host behavior.
- Add a PyBoy smoke test and reproducible GBDK-2020 4.5.0 build.
