# Combo and later-round review

Reviewed the checkpoint against fetched upstream `a76e5c8`: 28 added or changed
files and no new commits at review time. The prior feature-branch reviews remain
in this directory. No pull request is open.

The correctness pass follows a two-enemy pop into the mixed fixed/upper-ROM
source pair, round entry into the bank-1 pointer at `$5F51`, and later gameplay
into raw calls at bank-1 `$5D6F` and `$5696`. The tile helper maps each 32-byte
source separately, preserves final AF, restores logical HL for fixed sources,
and returns with V0 mapped. Both blocks fit within VBlank after the LY 145 wait.
The intro-pointer wrapper reproduces the original HL increment, DE result, and
AF. Dispatcher discovery uses the existing checked relocation machinery.

The new scene test checks the VBlank counter as well as accumulated tick labels,
rejects missing or reordered sample sets, and compares OAM from the FE00-FFFF
Gambatte chunk. Only known descriptor pointer aliases are normalized. Partial
maps may differ only while both displays are off. The original replay uses the
same state decoder, record normalization, and button schedule in `gameplay.py`.

| Check | Ran | Found | Fixed | Left, and why |
|---|---|---|---|---|
| Correctness and failure controls | Yes | Mixed tile sources, bank-1 intro pointer read with V0 mapped, two undiscovered dispatchers | Independent mapping, checked pointer wrapper, two bank-1 entry seeds; preceding combo and round-5 tests fail | Normal victories and rounds beyond 9 need further coverage |
| Coding standards and coherence | Yes | State decoding and input policy needed by two test modules; one helper comment misstated HL behavior | Shared helpers extracted unchanged; comment corrected; changed modules and repeated patch sites reviewed | Historical source variants preserved as checkpoints |
| Game Boy checks | Yes | Raw calls reach poisoned host ROM0; banked pointer reads wrong transfer data | Native register effects, mapping restore, exact patch bytes, build layout, and VBlank budget checked | Sampled state does not prove exact audio or wall-time equivalence |
| Regression suite | Yes | Old combo fails at tick 2; old round-5 scene differs from its first sample | Seven combos, six later-round scenes, active/idle through 12000, KLL1, title, menu, SRAM/power cycle, prefill, and forced progress pass | Round 6 has one shared omitted tick and one LCD-off map difference |
| Behavior descriptions and prose | Yes | Status still listed combo/later-round checks as future work; lifetime path name imprecise | README, status, identities, research index, and current terminology updated; ASCII detector validated on salted text | Historical logs retain original wording |
| Repository hygiene | Partial | Other published-game original ROM inputs absent | Syntax, whitespace, handoff checksums, staged file types, and source/output identity checked | Unchanged published-game suites cannot rerun without their inputs |

All available checkpoint checks pass. BB1 v0.14 remains promoted, BB2 v0.22
remains frozen, and collection integration remains unfinished. No release patch
or game rules changed.
