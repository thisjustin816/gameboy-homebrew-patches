# Classic Bubble Bobble DX

BB1 active gameplay matches the native reference through frame 3600 in the
graphics candidate. Rendering after player death remains incomplete, so BB1
v0.14 stays the promoted baseline and BB2 v0.22 stays frozen. Read [STATUS.md](STATUS.md) for the current evidence and next work.

The complete original handoff is preserved byte for byte in [handoff/](handoff/).
Its [review](REVIEW.md) records historical inconsistencies. The source files in
[source/bb1-virtualization/](source/bb1-virtualization/) are editable working copies;
the older status notes describe the supplied checkpoint.

## Build

Use Python 3 and RGBDS 1.0.3. The builders accept only these patched inputs:

| Input | MD5 |
|---|---|
| Classic Bubble Bobble, physics + save v1.0 | `2c4c0b9cc0c106051fb195e4ed3365d9` |
| Bubble Bobble, save v1.0 | `b093fd9aa903453c1b30703738159a49` |
| Bubble Bobble Part 2, tearing fix + save v1.1 | `f2ef3b62b6859cc89bbb8494bb4057b2` |

```sh
python3 source/bb1-virtualization/build.py CLASSIC.gbc BB1.gb BB2.gb \
  --variant control-fix --rgbds /path/to/rgbds -o /tmp/control-fix.gbc
```

Pass one variant explicitly:

| Variant | Source | Purpose |
|---|---|---|
| `baseline-v0.14` | `baseline_v014.py` | Reconstructed baseline; matches the historical MD5 and SHA-256 exactly |
| `edgeprobe18b` | `edgeprobe18b.py` | Original diagnostic with corrected two-word stack capture |
| `control-fix` | `prototype.py` | Round-start relocation fixes with the diagnostic traps removed |
| `graphics-experiment` | `graphics_experiment.py` | Active-play graphics fixes; post-death rendering remains incomplete |

Generated ROMs, assembler outputs, and manifests go beside the output path.
Keep them outside the repository. The frozen BB2 virtualization source and
phase-0 layout source remain in the original archive.

## Verify

Install `pyboy`, `pillow`, `numpy`, and `stable-retro` into a Python environment.
Run the following from `source/bb1-virtualization/`:

```sh
python3 test_kll1.py /tmp/control-fix.gbc
python3 test_real_title_vram_parity.py /tmp/control-fix.gbc --source BB1.gb
python3 test_menu_transition.py /tmp/control-fix.gbc
python3 test_sram_bank1_powercycle.py /tmp/control-fix.gbc
python3 test_password_prefill_routines.py /tmp/control-fix.gbc
```

`test_kll1.py` uses the installed Gambatte core and checks round state through
frame 3243 plus scheduler progress. It does not establish graphics parity. The
baseline fails this regression at frame 2064; `control-fix` passes. Build
`edgeprobe18b` and run `test_probe_capture.py` to verify its stack capture, or
run `test_kll1.py --arm-probe` to reproduce the frame-2094 trap.

For the graphics candidate, build with `--variant graphics-experiment` and run
the same regressions plus the native gameplay comparison:

```sh
python3 test_gameplay_parity.py /tmp/graphics-experiment.gbc --source BB1.gb
python3 test_gameplay_parity.py /tmp/graphics-experiment.gbc --source BB1.gb --active
```

The default checks every frame from 2300 through 3600. Sprite-stream pointers
and tile patterns also match through frame 6000. Add `--end 6000` to
exercise later deaths and transitions; this extended active run currently fails.
The native reference changes only the CGB header and checksums, and provides a
memory/timing reference. Its palette output is not a visual reference.

The [research folder](research/) contains old/new evidence, native and candidate
frames, and the emulator tracing patch. The patched inputs, generated ROMs, saves,
and emulator states are excluded from Git.

To verify the original handoff bytes, run `sha256sum -c SHA256SUMS` here.

To reproduce the current candidate while the Classic input is unavailable, use
the exact saved preceding graphics ROM (MD5
`617beb54814b87dff60e7b95d0068c09`) with the recovered patched BB1 input:

```sh
python3 source/bb1-virtualization/rebuild_graphics_checkpoint.py PREVIOUS.gbc BB1.gb \
  --rgbds /path/to/rgbds -o /tmp/graphics-experiment.gbc
```

This incremental path checks the saved ROM and input hashes, verifies that the
existing host services assemble identically, and adds the death-animation
pointer worker. A full build from the original three inputs still needs to be
checked against it. To isolate the pointer regression, run the gameplay test
with `--active --end 6000 --fields sprite_streams`; the unrestricted extended
comparison continues to fail on map differences.
