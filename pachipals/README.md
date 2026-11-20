# PachiPals experimental patch source

This directory contains reconstructed HP-freeze source and patch safety tests.
The complete physics builder, direct-start bootstraps, emulator fixtures, and
previous verification receipts still need to be restored from the experiment
bundle. No release IPS or ROM is generated from this checkout alone.

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
or replace an old-fails/new-passes PyBoy regression. No ROMs or states were
available for emulator verification in this checkout.

Keep ROMs, save states, private reference material, and bundle archives outside
the repository. Experimental deliveries require both pinball and pachinko
direct-start ROMs, matching source, hashes, and fresh rebuild/recovery checks.

See [NOTES.md](NOTES.md) for the recovered addresses and missing artifacts.
