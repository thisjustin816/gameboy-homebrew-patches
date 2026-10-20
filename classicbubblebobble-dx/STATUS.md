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

The unpromoted `graphics-experiment` variant includes the banked graphics,
background, object-coordinate, queue-upload, death-animation, and cooperative
task fixes. It also relocates the enemy-chain score table, bonus-graphics table,
and defeated-enemy lifetime/velocity tables. The round-clear VBlank entry `$1743`
is included in fixed-bank code discovery.

The full build has MD5 `c5c974dfe6bf0f2784a1aaec049b09a5` and SHA-256
`1f9c6912eee0dae937f3394bd71f482f6649fb83fb55f8e2f2869fd3e46efa93`. The three patched input hashes are listed in
[README.md](README.md); generated ROMs and states remain outside Git.

## Replay clocks

The emulator-frame replay first diverges at frame 6037, where native player
animation advances before the hosted animation. At emulator frame 6036, native
`$FF93` is 122 and hosted `$FF93` is 121. At frame 6037 they are 123 and 122.
LCD-off work and subsequent LCD enable shift the relation between emulator
frame returns and the game's VBlank counter. This difference predates the most
recent graphics fixes and remains visible in the original replay mode.

`test_gameplay_parity.py --clock game` drives input by the `$FF93` counter and
compares snapshots at matching accumulated ticks. Both workers must start at the
same counter value and sample the same tick labels. The latest snapshot is kept
when emulator stepping returns twice within one game tick. A step can also span
two game ticks; omitted labels are reported, and differing omissions fail the
test. Emulator-frame mode remains the default for the preserved replay.

The active game-clock replay through tick 12000 compares 9695 snapshots with
zero mismatches in LCD state, round index, timer, actors, objects, score,
sprite-stream pointers, collision data, tile patterns, and displayed maps.
Six tick labels are unobserved in both workers. Idle through tick 12000 compares
9700 snapshots with zero mismatches and one shared unobserved label. The active
run visits round indices 0, 1, and 2. This is sampled game-state parity, not a
proof of exact wall-time or audio equivalence.

## Enemy tables and round clears

The game-clock input schedule exposes real data faults in the preceding ROM:

- `$2AA4` computes the enemy-chain score-table address at `$2A7C`; its high byte
  must use the relocated `$6A` window. `$2AB3` similarly needs `$6FF6` for bonus
  graphics. The old replay loses a native score award of 100 points.
- Defeated-enemy initialization at `$2E0B` reads lifetime data at `$2FEF`, and
  `$2E36` reads velocity pairs at `$2DEA`. Both need the relocated fixed window.
  The old enemy record receives zero lifetime/velocity values where native
  writes `$15`, `$06`, and `$FE` in the traced case.
- Round completion selects VBlank entry `$1743` through `$FFAB`. Discovering
  this entry relocates its `CALL $1755` and `JP $0CB8`. Without that discovery,
  forcing a clear returns the hosted game to startup at `$41B1`, and the round
  index never advances from 2 to 3.

The game-clock regression fails on the preceding ROM from tick 4844 and passes
on the current build. The round-progress regression forces `$FFC3=0` and checks
that rounds 4-9 start and their indices persist for another 300 emulator frames.
Native and hosted builds pass; the build without `$1743` discovery fails to
start round 4. These forced clears verify loader progress, not normal victories
or frame-for-frame graphics in those later rounds.

## Combo and later-round coverage

Controlled combo scenes clone a naturally reached trapped enemy and let the
engine pop one through seven enemies. All seven cases match native across 181
observed ticks each, including the first awards of 100, 200, 400, 800, 1600,
3200, and 6400 points, bonus objects, OAM, tile patterns, and displayed maps.
The preceding build first differs in tile data two ticks after a two-enemy pop.
The VBlank tile-pair helper now maps each source independently: one pair combines
bank-1 `$652F` with fixed-ROM `$304A`. Fixed second pointers retain their logical
HL value on return.

Later-round scenes enter rounds 4-9 by forced clears, then apply ordinary
movement, jump, and bubble input for 1200 game ticks per round. They compare
7205 observed snapshots with zero gameplay or displayed-graphics mismatches.
Round 6 has one shared omitted tick and one partial-map difference while both
LCDs are off. The fixture verifies active play after controlled entry; it does
not establish normal victories.

These checks also exposed a bank-1 round-intro pointer read at `$134E` and
undiscovered bank-1 dispatchers `$5CCF` and `$55A0`. The pointer read runs with
bank 1 mapped, and recursive discovery rewrites the dispatchers' calls into
fixed ROM. Without these fixes, round 5 starts with incorrect transfer data,
and later special-object/projectile paths enter poisoned host ROM0 and reset.

## Current verification and next work

KLL1, title VRAM, menu transition, SRAM isolation/power cycle, password prefill,
and the original active emulator-frame replay through 6000 all pass. LCD-off
partial map clears are reported separately; strict raw-map mode remains
available with `--include-lcd-off-maps`.

The logs and compact traces are in [research/](research/), with the current
review in [REVIEW-COMBO.md](REVIEW-COMBO.md). Next work is sustained natural
play, later-round and ending coverage, and collection integration. Audio and physical hardware remain unverified. BB1 v0.14
stays promoted; BB2 v0.22 stays frozen. No selector or player-facing UI was added.
