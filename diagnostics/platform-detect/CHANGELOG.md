# Changelog

## v1.2

- A CGB CPU now wins over the SGB probe, so an emulator that answers the probe
  no longer reports `HW: SGB1`.
- On CGB, print `SGB PROBE:` and `EMU: LIKELY` or `EMU: NO TELLS`. LIKELY means
  the SGB probe answered on a CGB or FF72/FF73 are not CGB-like.

## v1.1

- Fix a blank white screen on real CGB hardware and emulators that start with
  white palettes: the ROM now sets its own black-on-white text palette.
- The smoke test now checks that the text contrasts with the background.

## v1.0

- Add DMG, MGB, SGB, CGB, and GBA/CGB hardware reporting.
- Add reversible FF72 and FF73 CGB register probes.
- Report CGB-like, binjgb-like, or other/quirk host behavior.
- Add a PyBoy smoke test and reproducible GBDK-2020 4.5.0 build.
