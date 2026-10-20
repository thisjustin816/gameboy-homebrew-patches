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

The unpromoted `graphics-experiment` variant fixes bank-3 enemy-record reads,
mixed fixed/banked background descriptors, and banked queue copies. The bank-1
cooperative task at `$4669` enters through a host wrapper with bank 1 mapped.
Executing relocated fixed `$0669` at that address ran the timer twice per frame.
The `control-fix` variant remains available for comparison.

The current graphics build has MD5 `823dad4303d4e83e20cd1fd2522688c2` and SHA-256
`b7987d9045e27dff30b2289ebf2163b730a8b88f9ff2a7c1dfa196f1e6945dbc`.
Title VRAM parity, menu transition, SRAM bank isolation/power cycle, and password
prefill regressions pass. Both idle and scripted movement/jump/fire runs match
the native CGB reference at every sampled frame from 2300 through 3600. The
comparison covers round index, timer, player and seven enemy records, sprite-stream pointers, collision
WRAM, bank-0 tile patterns, and both tile maps. Descriptor pointers in actor
records are normalized for their relocation; other compared bytes are exact.
The preceding graphics build fails both runs.

Extended runs still fail. Active input through frame 6000 produces 1381 frames
with differing maps, starting at frame 3730. Tile patterns and sprite-stream
pointers match every frame through 6000. The preceding candidate also had 185
frames with bad sprite pointers and tile patterns. Idle input on that preceding
candidate through 4000 finds one differing map byte at frame 3962. The compared round, timer,
actor, and collision fields remain equal in these runs. This does not establish
parity for all WRAM, scoring, audio, or all transitions. Keep the extended test
strict and leave the variant unpromoted.

## Remaining rendering investigation

Emulator-side tracing on October 20 separates timing failures from bad data:

- The ROUND text write to `$9967` has value `$18` in both ROMs. Native fixed
  `$0311` writes with STAT `$CD` (mode 1); relocated `$4311` writes with STAT
  `$CF` (mode 3). Both report LY 0 after LCD enable. The hosted write is blocked.
- The death-animation setup at fixed `$1B49` reads four pointer bytes from
  bank-1 `$5F5F` or `$5F63`. It must expose that logical bank while reading.
  `host_bb1_death_sprite_pointers` performs those reads in host ROM0 and restores
  V0. The focused sprite-stream regression fails on 185 frames before this fix
  and passes afterward. The frame-4000 sprite also matches the native capture.
- A later HUD redraw copies `$04` to `$9825` where native copies blank tile `$24`.
  The source buffer `$C2EB` already differs: host `$4A56` writes `$04`, while
  native `$0A41` writes `$24`. Trace the score formatter's input at `$C492` and
  its callers; the current actor comparison does not include that address.

The replay, frame captures, build identities, and compact traces are in
[research/](research/). The saved ROM and emulator states are outside Git.
The original uploads disappeared from `/tmp` after the environment restarted.
The exact patched BB1 input was recovered from the saved CGB reference by
restoring the DMG header and checksums. BB2 was recovered from its unchanged
embedded banks. Both MD5 hashes match the supported inputs. Full builds still
require reattaching the patched Classic v1.0 ROM.

The current ROM was rebuilt incrementally with
`rebuild_graphics_checkpoint.py`, from the exact saved preceding graphics ROM
and the recovered BB1 input. It checks the input hashes and existing host-service
bytes before adding the death-animation worker. Full reconstruction with
`build.py` remains unverified until the Classic input is restored.

BB1 v0.14 remains the promoted baseline; BB2 v0.22 remains frozen. No physical
hardware validation has been performed for these candidates.
