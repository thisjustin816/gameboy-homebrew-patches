# PachiPals experimental patch source

This directory contains recovered October 27 checkpoint source, its portable
regression tools, and reconstructed HP-freeze source. The later guarded D+,
three-lane bootstrap, flipper changes, and WallRebound25 source remain missing.
The checkpoint builds reproduce earlier experiments; they are not replacements
for those later builds.

## Recovered checkpoint

[`checkpoint/build.py`](checkpoint/build.py) rebuilds the archived pinball
TipFit and pachinko D/E/F profiles from the exact pristine ROM. Each profile
has complete original-byte assertions and expected output SHA-256 and MD5.
The builder uses existing code and tables and allocates no free space.
Its four profiles reproduce the archived ROMs byte-for-byte. It offers no
arbitrary restitution setting. Reverse reconstruction of each profile also
matches the pristine ROM exactly, and a fresh source copy rebuilds all four
recorded hashes.

```sh
python3 pachipals/checkpoint/build.py pinball-tipfit /private/PachiPals.gbc /private/pinball.gbc
python3 pachipals/checkpoint/build.py pachinko-d /private/PachiPals.gbc /private/pachinko.gbc
```

The private pristine input has MD5 `882473be633a60bffd2daaf32c99e89f`.
`checkpoint/profiles.json` records its SHA-256, output identities, exact byte
edits, control identities, and the two supported state hashes. ROMs and states
must be supplied privately.

To rerun the recovered suite in a Python virtual environment:

```sh
python3 -m pip install pyboy==2.8.1 pillow
python3 pachipals/checkpoint/verify.py /private/PachiPals.gbc \
  /private/pachipals-battle-phase78.state \
  /private/pachipals-capture-scene4E85.state --out /private/checkpoint-verification
```

The output directory must be new. It contains rebuilt ROMs, test controls,
logs, sampled frames, and a receipt. Every emulator instance uses a separate
temporary ROM copy. Unknown ROM and state identities are rejected.

The recovered suite checks direct pachinko boot and launch for D/E/F, 13 battle
launch schedules per candidate, an old-fails/new-passes flipper-tip comparison,
the capture stall check, and 80 capture pulse cases per ROM. Pulse inputs
include Left, A, and Left+A, with Right and Left+Right retained as legacy input
coverage. The tip comparison retains its original Left+Right replay to reproduce
the archived defect; that replay does not establish the game's flipper mapping.
The 13 battle schedules reach eight distinct marker positions; repeated edge
positions have different input timing.

The damping trace reproduces 48 passive and 41 object-associated hits across
the preserved sweep. The passive sites are `19:665F`, `19:7A82`, `19:7BC6`, and
`19:7C61`. This is the original, limited table-base-load inventory, not complete
coverage of passive collision paths or later boards.

Verification receipts and text logs are in [`verification/`](verification/).
These checks cover the recovered checkpoint only. They do not validate the
missing later physics patches, a three-lane battle, or hardware feel.

## Reconstructed HP freeze

`freeze_hp.py` replaces the damage operand with zero in the shared battle and
capture scripts. It preserves initialization, healing, and the native physics
code. Both teams' battle HP and the capture target's HP retain their current
values when those scripts apply damage. Other encounter rules remain active.

The script supports exactly two prior experimental inputs:

| Input | MD5 |
|---|---|
| Pinball WallFeed1 | `f377099af075fee47e5190a6d88026c6` |
| Pachinko Guarded D+ Three Lanes | `f52590b357cbd649ff0b13531cbad368` |

Full SHA-256 identities and original-byte contexts are in `profiles.json`.
Unknown inputs are rejected. The pinball input is a prerequisite for the wall
patch; applying HP freeze alone does not build WallRebound25.

With a supported input available privately:

```sh
python3 pachipals/freeze_hp.py /private/input.gbc /private/output.gbc
```

The output must be a new file. Every patched operand and its surrounding script
bytes are checked before any changes. The tool updates the global checksum and
prints the output hashes. For the pachinko input, it also checks the output
against the recorded Frozen HP SHA-256. That comparison still needs a rerun on
the actual ROM after recovery.

Run the source tests with Python 3; no packages are needed:

```sh
python3 -m unittest discover -s pachipals -v
```

The nine tests passed during reconstruction. They use synthetic buffers to
check byte assertions, allowed differences, checksum repair, unsupported-input
rejection, and failure without modifying the input. They do not verify gameplay
or replace an old-fails/new-passes PyBoy regression. The recovered HP operand
contexts also match the pristine ROM, but the two supported later experimental
inputs remain missing, so the HP-freeze outputs have not been rebuilt here.

Keep ROMs, save states, private reference material, and bundle archives outside
the repository. Experimental deliveries require both pinball and pachinko
direct-start ROMs, matching source, hashes, and fresh rebuild/recovery checks.

See [NOTES.md](NOTES.md) for the recovered addresses and missing artifacts.
