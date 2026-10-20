# Debugging evidence

`build-identities.json` identifies each reconstructed or candidate ROM. ROMs and
emulator states remain outside Git. The `*-build.txt` and `*-kll1.txt` files record
build and regression output, including expected failures on the old variants.

The four `*-core-trace.txt` control traces capture successive failures: the
unrelocated VBlank entry, the object table, the enemy table, and the undiscovered
banked handler. `kll1-clean-core-trace.txt` lists remaining fixed-ROM reads after
the control-flow corrections.

The capture logs show the original probe failing against live RAM and the
corrected probe passing. The regression logs cover title, menu, save isolation,
power cycling, and password prefill. PNGs compare native, control-flow, and
graphics-experiment output at frame 2600 of the same KLL1 input sequence.

## Emulator trace

The installed Stable-Retro 1.0.1 Gambatte core reproduces the frame-2094 failure.
The tracing core was built from `libretro/gambatte-libretro` commit
`d9d6cd06382d1ced30de34d56d3609452323dab1`. It reproduces the same marker, frame,
stack, and round state without changing the diagnostic ROM.

Apply `gambatte-trace.patch` with `git apply --unidiff-zero` to that source and
build with `make`. The patch
records an instruction ring after `$FFF9=$5A`, dumps it on a `$4150` entry with
physical bank `$40`, and logs fixed-code reads from low ROM addresses. Its reads
are limited to ROM, WRAM, and HRAM; it adds no emulated CPU cycles.

To use that core, copy its `gambatte_libretro.so` and the installed `gambatte.json`
into a separate directory and set `_retro.core_path` to that directory before
creating the replay emulator. Preserve the installed core for comparison.
The trace distinguishes physical banks because `$4150` is also a valid address
inside other guest banks.

## Active gameplay and death transitions

`graphics-v2-*` records the graphics candidate with banked enemy records,
background reads, queue copies, and the cooperative task entry corrected.
The `old-*-parity` logs show the new regression failing on the preceding
`3ce8f90` graphics build. Idle and active parity logs pass through frame 3600;
extended logs preserve failures through frames 4000 and 6000. The four
`graphics-v2-test_*` logs cover the inherited regressions.

`graphics-fixed-frame2600.png` and `graphics-fixed-active-frame3243.png` show
the corrected candidate. Earlier `graphics-experiment-*` files refer to the
preceding build, retained as `graphics-experiment-3ce8f90` in the identity file.
`graphics-v2-trace-excerpts.txt` records the banked-task and background/queue
investigation. `death-render-trace-excerpts.txt` records blocked text writes,
different sprite sources, and a divergent score-format buffer before the
death-pointer correction. The full trace runs use the same KLL1 entry and active buttons as
`test_gameplay_parity.py`, with no changes to the ROM under test.

The death-pointer checkpoint at `cb14a55` is identified separately from the preceding
`graphics-experiment-before-death-pointers` ROM. `death-pointers-build.txt` records
its incremental assembly; `death-streams-old.txt` fails on 185 frames and
`death-streams-new.txt` passes all 3701 compared frames. Default idle and active
runs pass, and `death-final-extended.txt` preserves the remaining map failure.
The `death-test_*` logs cover KLL1 and the inherited regressions.
`death-fixed-frame4000.png` and `death-native-frame4000.png` show the corrected
sprite and the original DMG reference with the same active input.

`gambatte-death-render-trace.patch` adds only the write logging used by this
investigation. Apply it to the clean Gambatte revision above with
`git apply --unidiff-zero`, build, and
select the separate core directory before cold boot. After the KLL1 entry,
set `$FFF9=$5A` and replay the active buttons through frame 6100. The logger
reports PC, source/destination registers, mapping, STAT, LY, and attempted value.
It preserves the original write and adds no emulated CPU cycles. This patch is
an alternative to the earlier ring-trace patch, not an addition to it.

## Text, objects, and full reconstruction

`rendering-build.txt` records the current full build from the restored Classic
input and the recovered BB1/BB2 inputs. The earlier full death-pointer build
matches its incremental checkpoint byte for byte. The incremental helper was
removed after restoring full builds; its source remains at commit `cb14a55`.

`rendering-active-6000.txt` and `rendering-idle-12000.txt` pass with the expanded
object/score comparison. `rendering-old-active.txt` fails on the preceding ROM.
`rendering-lcd-off-maps.txt` retains three raw-map mismatches, all during LCD-off
clears; visible maps and the other compared fields agree through frame 6000.
`rendering-fixed-frame3892.png` shows the restored ROUND text, and the frame-6000
capture shows the corrected HUD. `rendering-fixed-trace.txt` records safe text
writes and score clearing.

`rendering-active-12000.txt` fails at frame 6037, first in player animation/state.
The preceding checkpoint's focused actor comparison has the same first failure
in `rendering-old-long-actors.txt`. `rendering-without-guard-long.txt` shows that
removing the queue guard leaves that failure in place. This is an unpromoted
checkpoint; the longer active divergence still needs investigation.
