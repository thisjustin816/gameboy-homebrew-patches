# Current checkpoint

Date: 2026-10-20. No pull request is open. BB1 v0.14 remains the promoted
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

## Graphics checkpoint

The unpromoted `graphics-experiment` variant fixes banked enemy-record reads,
background descriptors, queue sources, death-animation pointers, and round-object
coordinates. It also relocates the fixed object-description table at `$31AA`.
The bank-1 cooperative task at `$4669` enters with its bank mapped; executing
relocated fixed `$0669` there ran the timer twice per frame. `control-fix` stays
available as the earlier control-flow comparison.

The current full build has MD5 `b230db90e4551f605c44e614eb685d89` and SHA-256
`620a735d6d0aba793f53d6a80d42681846760040c37a00f46f8d8f616ccf221c`.
The restored Classic input matches MD5 `2c4c0b9cc0c106051fb195e4ed3365d9`.
Before further changes, the full build reproduced the preceding incremental
candidate's MD5 `823dad4303d4e83e20cd1fd2522688c2` byte for byte. All three exact
patched inputs are available again outside Git.

## Text and HUD corrections

The queue uploader at fixed `$0310` can reach mode 3 after LCD enable. The host
worker waits for accessible VRAM before each byte in that case. For blocks of
at most 64 bytes at LY 144-147, six VBlank lines remain and the original copy
loop fits without per-byte polling. The worker retains the native carry and
register postconditions. Emulator tracing confirms the ROUND tile `$18` reaches
`$9967` in mode 0; the preceding candidate attempted the write in mode 3.

Round-object setup at `$1977` and `$198A` reads coordinates after the selected
bank's eight-byte layout header. Those reads execute in host ROM0 with the
logical bank visible. Reading V0 there placed the object at the wrong position;
a later pickup added an invalid `$40` score and changed the HUD. The object's
description at `$19C8` also needs the relocated fixed table at `$71AA`.

## Verification and limits

KLL1 round state, title VRAM, menu transition, SRAM isolation/power cycle, and
password prefill regressions pass on the current full build. The gameplay test
compares LCD state, round index, timer, player/enemy records, all 15 object
records, score, sprite-stream pointers, collision WRAM, bank-0 tile patterns,
and both tile maps. Known descriptor pointers are normalized for relocation.

Idle input matches native from frame 2300 through 12000. Scripted movement,
jumping, and firing match through frame 6000. The preceding checkpoint fails
this expanded comparison from frame 2300 because its object coordinates differ.

Maps are compared whenever either LCD is enabled. While both displays are off,
partial map clears can differ within a sampled frame. The strict
`--include-lcd-off-maps` active run through 6000 preserves three such failures,
at frames 3730, 3940, and 5876. Both LCDC values are `$67` at each failure; every
map byte matches again before the LCD is enabled. No actor, object, score,
timer, collision, or tile-pattern mismatch is suppressed.

The longer active run through 12000 still fails, first at frame 6037. Native
player animation advances from state 9 to 10 one frame before the hosted game;
its animation countdown then leads by one. Later repeated continue/death cycles
diverge further. The preceding checkpoint has the same first actor failure, and
removing the queue guard leaves it unchanged. Trace the player animation/state
update and its cooperative task around frames 6036-6038 before assuming a cause.
`test_gameplay_parity.py --active --end 6200 --frames-dir /tmp/replay` retains
those states and screenshots outside Git.

The logs, identities, screenshots, and current review are in
[research/](research/) and [REVIEW-RENDERING.md](REVIEW-RENDERING.md). BB1 v0.14
remains promoted; BB2 v0.22 remains frozen. Full audio, later rounds, and physical
hardware behavior remain unverified.
