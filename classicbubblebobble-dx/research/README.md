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
