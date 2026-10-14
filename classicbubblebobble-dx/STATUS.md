# Current checkpoint

Date: 2026-10-14. No pull request is open. BB1 v0.14 remains the promoted
baseline; BB2 v0.22 remains frozen. No selector or player-facing UI was added.

## Verified control-flow fixes

The supplied patched and unmodified ROMs match all six expected MD5 hashes.
The reconstructed v0.14 baseline matches MD5
`85ad58cbabcc52e53cb250b2abaddcd6` and SHA-256
`546d9ac6c56904e9690bc6acbe33ee0a1266e0e84367e8e93230e1e6c9731fb6`.

The corrected edgeprobe18b reproduces the trap at frame 2094 in the installed
Stable-Retro 1.0.1 Gambatte core: marker `$C4`, `SP=$DFFD`, stack word `$41B1`,
and round index `$C200=2`. The original probe reports `$00B1` for that first word;
the correction reports `$41B1`, matching live RAM. Its second-word destinations
were corrected too.

An emulator instruction trace identifies the first bad control edge:

1. VBlank dispatch reaches logical `$174C` through `$FFAB`.
2. That indirect entry was absent from fixed-bank discovery, leaving
   `CALL $1755` and `JP $0CB8` unrelocated.
3. The latter jump enters poisoned host ROM0. Gambatte proceeds through the
   undefined-opcode fill and reaches the launcher, which enters `$4150`.

After discovering `$174C`, later traces expose two additional failures: the
object dispatcher reads `$2C7F` from host ROM0, and the enemy dispatcher reads
`$29E3` from host ROM0. Their bases now refer to the relocated tables. The
builders also discover all 14 fixed object handlers and eight bank-1 enemy
handlers in those tables; otherwise a handler such as bank-1 `$5278` retains
its raw `CALL $14E9`.

The `control-fix` variant removes the diagnostic probes. It retains round index
2 through frame 3243 and advances the scheduler under the preserved KLL1 replay.
The exact v0.14 baseline fails the new round-state regression at frame 2064.
The armed edgeprobe reproduces its failure at frame 2094. Title VRAM parity for
every frame 400-600, the 715-frame menu hash, SRAM bank isolation/power cycle,
and VLL1 password-prefill routines all pass on `control-fix`.

## Graphics frontier

Round-state persistence is insufficient for promotion. The control-flow candidate
renders corrupted background and sprite graphics. Captured native and candidate
frames are in [research/](research/).

The separate `graphics-experiment` variant contains unpromoted work on fixed-ROM
layout/animation/background descriptor pointers and banked VBlank transfer
workers. Bub's sampled sprite improves, but the background map and enemy graphics
still disagree with native BB1. Do not promote or distribute this variant as a
finished patch.

At frame 2600, that experiment's VRAM bank-0 tile data agrees with native BB1
except for the 16-byte tile at `$97A0`, while its tile maps differ in 190 bytes.
Its sparse `$C112` table and enemy records also differ. The native `$97A0` tile
comes from bank-1 `$722F`. Inspect selected-bank data reads and code/data overlaps
before changing any tile bytes.

The next investigation should start with fixed routine `$2ECC`: it reads the
selected bank-3 pointer table at `$5FC0` and then consumes its stream through DE
while V0 is mapped. The trace records bogus low pointers at `$6EE7/$6EF4/$6EFA`.
Also trace the writers of `$C112` and the divergent background map cells. Keep
the passing control-flow candidate available as a comparison.

The original diagnostic probes change timing enough to disturb title parity and
stall the inherited password-prefill harness. Use the probe-free candidate for
regressions, and emulator-side tracing for the remaining failures.

Build identities, trace logs, and the final review are retained beside the sources.
No physical hardware validation has been performed for these candidates.
