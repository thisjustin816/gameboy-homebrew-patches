# Recovered technical notes

These addresses and identities come from the retained development record.
They have not been re-derived against a ROM in this checkout.

## HP script edits

| Bank:address | Original operand | Replacement | Purpose |
|---|---|---|---|
| `15:47BA` | `FD 0F 00` | `FE 00 00` | Battle damage global 15 becomes literal zero |
| `2F:6B51` | `FD 86 00` | `FE 00 00` | Capture damage global 134 becomes literal zero |

These are same-length GBVM RPN operand edits. Four script bytes change in total,
plus the global checksum. They allocate no free space, hooks, or WRAM. Damage
calculation and hit scripts remain present.

GBVM globals begin at `CBCF` and use 16-bit words. Party HP indices are
49, 60, and 71; opponent HP indices are 82, 102, and 113. Index 133 (`CCD9`)
holds the selected target's HP and may legitimately change as targets switch.
A future regression must distinguish target selection from damage.

Useful recorded trace points:

- `00:3A4C`: VM dispatch, A opcode, HL operand pointer, `FF90` script bank.
- `00:3257`: indirect RPN low-word store; HL destination, C/B proposed word.
- `00:32C1`: direct RPN low-word store.
- `0D:48C1`: VM_SET low-word store.
- `0D:48ED`: VM_CONST low-word store.

Hook only one store in adjacent low/high byte pairs. Adjacent one-byte PC hooks
can stall PyBoy.

## Pinball wall patch specification

The recorded WallRebound25 implementation replaces two existing 97-byte
routines at `0A:6DE9` and `0A:6E4A`. The exact replacement instruction bytes
and asserted original routine bodies are missing. Do not assemble a guessed
replacement and label it the recovered build.

The intended change applies when collision kind `D9E6 == 3` and the native
integer low byte at `C0DC >= 176`. In the collision-normal frame it retains
`floor(N / 4)` for incoming `N >= 0`. Separating contacts retain the prior
response. The downhill tangent assist remains limited to original normal
values 0 or 1 and `abs(T) <= 2`. Other collision contexts must match WallFeed1.

Recorded canonical cases:

| Contact | Incoming velocity | WallFeed1 | WallRebound25 |
|---|---|---|---|
| Right diagonal | `[16, 16]` | `[0, 0]` | `[-4, -4]` |
| Left diagonal | `[-16, 16]` | `[0, 0]` | `[4, -4]` |

Velocity bytes `D9D9/D9DA` are signed, with 16 units per pixel per tick.
Normal gravity remains +2 units every four ticks, or 0.03125 px/tick squared.
The original speed limiter at `0B:4BA9` and its table at `0B:4E00` must remain
unchanged. Native physics banks `06`, `0E`, `14`, `19`, and `7A` must match the
WallFeed1 predecessor. Pinball flipper controls are Left and A.

Pachinko retains the guarded D+ physics. Its frozen-HP output should differ
from the supported three-lane input only at the two HP operands and checksum.
The shared damping table at `19:5B80` also serves live-object collisions;
changing it globally cannot isolate passive rebound.

## Artifacts needed for complete recovery

The most useful missing artifact is
`PachiPals-WallRebound25-FrozenHP-Test-Pair.zip`, recorded SHA-256:

```text
c7e8445c492559dbc180023bbeab56c1a718639024b7c45840473a725cecfa50
```

Its recorded outputs are:

| Output | SHA-256 |
|---|---|
| Pinball WallRebound25 Frozen HP | `b56b069d3738b2565c3cf066e08ad654b27f4a87396885391de6dfc84be71293` |
| Pachinko Guarded D+ Three Lanes Frozen HP | `999aee093dbb4a36af0d8d1777995d0780d29548faa54c94f5d26265091190b6` |

These hashes identify missing artifacts; they are not evidence of a successful
rebuild in this checkout. The original complete development archive is also
missing. It was named `PachiPals-Codex-Complete-Handoff-2026-10-27.zip` and
contained the pristine ROM with SHA-256:

```text
f528d6757b314ecc40ab5195d167bf4c035b68c58cf8823f7c418a583722aca9
```

After restoring private inputs and source, rerun the native wall normal and
unaffected-state comparisons, natural wall-loop fixtures, powered-flipper,
gravity, settling, and long-replay checks. Rerun the original 13-position
pachinko sweep and later three-lane passive-versus-object traces. Verify the
three-lane layout visually and in state, then test HP damage writes in both
modes over extended encounters. Rebuild both outputs in a fresh directory and
verify forward and reverse patch recovery against the pristine ROM before
delivering another pair.
