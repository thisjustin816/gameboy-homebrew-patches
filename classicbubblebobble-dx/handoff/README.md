# Classic Bubble Bobble DX — source snapshot v0.19

Recoverable source/research checkpoint for:

- **BB2 virtualization diagnostic v0.22** — frozen known-good baseline from the prior checkpoint.
- **BB1 virtualization diagnostic v0.14** — current work; title/menu parity is retained, BB1 saves only to MBC5 SRAM bank 1 and survives a real PyBoy power cycle, and persisted-save password prefill routines produce the expected VLL1/END state. End-to-end password acceptance/round-start gameplay still needs Gambatte/stable-retro.

Start with `STATUS-HANDOFF.md`.

This source archive intentionally contains **no Game Boy ROMs, cartridge RAM files, battery saves, or emulator save states**. Rebuilding requires the three exact patched user-supplied ROMs identified by MD5 in the handoff plus RGBDS/PyBoy.
The original `reference/gameboy-homebrew-patches-main.zip` is excluded from this checkpoint because it embeds a compiled diagnostic `.gbc`; a ROM-free source extraction is retained under `reference/gameboy-homebrew-patches-main-src/`.

