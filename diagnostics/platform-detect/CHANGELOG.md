# Changelog

## v1.3

- Fix the FF72/FF73 probe, which reported `CGB-LIKE` on every host: SDCC
  replaced each read-back with the value just written. Writes and read-backs
  now run in asm.
- Add eleven more emulator tells and a `MATCH` line naming binjgb, mGBA, PyBoy,
  Gearboy, VBA-M, Gambatte or GameBoy-Online from their signatures.
- RP reading 02, as on the MiSTer-derived FPGA core in the ModRetro Chromatic,
  shows `MATCH MISTER FPGA` and is not counted as an emulator.
- New screen: a title bar, sections under labeled rules, aligned fields, and
  green or red verdicts on CGB.
- Load the CGB palettes before the display is on. Writes while a line is drawn
  are lost on hardware.
- The smoke test reads the screen text back and checks the verdict.

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
