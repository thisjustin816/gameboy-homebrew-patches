# Classic Bubble Bobble DX

The graphics candidate matches native in the sampled game-clock replay through
tick 12000, controlled combos, opening play in all 100 rounds, and controlled
ending paths. BB1 v0.14 stays promoted and BB2 v0.22 stays frozen. Read
[STATUS.md](STATUS.md) for fixture details and verification limits.

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
| `graphics-experiment` | `graphics_experiment.py` | Graphics/data fixes and round-clear entry; unpromoted |

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

The default preserves emulator-frame input timing and compares frames
2300-6000. LCD-off work shifts that clock relative to the game's `$FF93`
VBlank counter; the longer emulator-frame replay reports the preserved
frame-6037 difference. To drive inputs by game ticks and exercise round clears:

```sh
python3 test_gameplay_parity.py /tmp/graphics-experiment.gbc --source BB1.gb \
  --clock game --active --end 12000
python3 test_gameplay_parity.py /tmp/graphics-experiment.gbc --source BB1.gb \
  --clock game --end 12000
python3 test_round_progress.py /tmp/graphics-experiment.gbc --source BB1.gb
```

Game-clock mode compares matching observed ticks and reports labels missed
between emulator steps. Active and idle runs pass with 9695 and 9700 samples,
respectively. The round-progress test forces the enemy counter to zero, reaches
rounds 4-9, and checks that each index persists for 300 more frames. It does not
establish normal victories or later-round graphics parity.

Dedicated scene checks:

```sh
python3 test_scene_parity.py /tmp/graphics-experiment.gbc --source BB1.gb --scene combo
python3 test_scene_parity.py /tmp/graphics-experiment.gbc --source BB1.gb --scene later
```

Combos clone a naturally reached trapped-enemy record before ordinary engine
processing. Later scenes force round entry, then play 1200 ticks with movement,
jumps, and bubbles. All seven combos and rounds 4-9 pass native state, OAM, tile,
and displayed-map comparisons. These fixtures establish neither unassisted setup
nor normal victories. Use `--frames-dir /tmp/scenes` for sampled PNGs or `--cases`
for selected enemy counts (combo) or zero-based round indices (later).

Passwords allow direct checks of later rounds and bonus rooms:

```sh
python3 test_scene_parity.py /tmp/graphics-experiment.gbc --source BB1.gb --scene password
python3 test_scene_parity.py /tmp/graphics-experiment.gbc --source BB1.gb --scene password --all-rounds
python3 test_scene_parity.py /tmp/graphics-experiment.gbc --source BB1.gb --scene ending
```

Password mode defaults to rounds 10, 15, 20, 25, 50, 75, 99, and 100.
`--all-rounds` checks 1200 ticks after each of the 100 password entries.
Ending mode forces the final bonus-room goal with prior win flags zero and
seven, then compares 6000 ticks per path. It seeds divider reads only in temporary
ROM copies to compare decorative randomness; the build's random behavior is
unchanged. These checks do not establish natural victories, complete level
coverage, or audio equivalence. Ending mode reports intermediate LCD-off tile
and map clears separately; `--include-lcd-off-vram` requires their raw parity.

Regenerate the password fixtures with the original game's encoder:

```sh
python3 generate_password_fixtures.py BB1.gb /tmp/password-fixtures.json
```

Map bytes must match whenever either LCD is enabled. Add
`--include-lcd-off-maps` to compare partial clears while both LCDs are off.
The native reference normally changes only the CGB header and checksums;
ending fixtures also seed divider reads as described above. It provides a
memory/timing reference, and its palette output is not a visual reference.

The [research folder](research/) contains old/new evidence, native and candidate
frames, and the emulator tracing patch. The patched inputs, generated ROMs, saves,
and emulator states are excluded from Git.

To verify the original handoff bytes, run `sha256sum -c SHA256SUMS` here.
