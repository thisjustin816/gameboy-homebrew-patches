# Rendering checkpoint review

Reviewed against feature-branch commit `cb14a55`: 25 added, changed, or removed
files and no new commits at review time. The original archive and published
patches are unchanged. No pull request is open.

The code review follows the queue consumer from the header's carry flag reset through
both upload paths, and the object loader from its selected layout bank through
the coordinate and fixed-description reads. The queue's fast path bounds the
copy at 64 bytes and starts only at LY 144-147. Its guarded path polls STAT;
both preserve the native register and flag results. ROM patch sites check their
original bytes before replacement.

The expanded gameplay comparison covers the 15 object records and score that
the earlier actor check omitted. LCD state is compared every frame. Map bytes
are compared while either LCD is on; differences during LCD-off clears are
reported separately, and strict raw-map mode retains them as failures. Captured
states confirm both LCDCs are `$67` at all three raw-map failures through 6000,
and every map byte agrees before display resumes.

| Check | Ran | Found | Fixed | Left, and why |
|---|---|---|---|---|
| Correctness and regression controls | Yes | Blocked ROUND upload; wrong object coordinates and description table; invalid score/HUD | Guarded queue upload and corrected data reads; preceding ROM fails expanded object/score comparison | Active replay still diverges at frame 6037; preceding checkpoint reproduces the same actor failure |
| Coding standards and consistency | Yes | Shared actor/object normalization needed one decoder; incremental helper depended on older source | Shared record decoder; removed incremental helper after restoring full builds | Snapshot variants remain independent for reproducibility |
| Behavior descriptions | Yes | Docs still requested the restored ROM and described missing text/HUD | Updated build identity, commands, status, test scope, and next target | Historical logs and reviews retain their original scope |
| Writing style and prose scan | Yes | EOF whitespace and stale current-checkpoint wording | Trimmed whitespace and corrected wording; ASCII and prose checks completed | Raw emulator output retained as evidence |
| Build and emulator regressions | Yes | Original full build was previously blocked | Full build reproduces prior incremental ROM; current full build passes KLL1, title VRAM, menu, SRAM/power cycle, password, active through 6000, and idle through 12000 | Active through 12000 fails; no promotion or hardware/audio claims |
| Repository checks and hygiene | Partial | Other games' original ROM inputs are absent | Python syntax, links, staged whitespace, allowed file types, and original handoff hashes pass | Unchanged published-game suites cannot rerun without their inputs; prior review records their available runs |

The longer active failure also occurs without the new queue guard. Its cause is
not established. BB1 v0.14 remains promoted and BB2 v0.22 remains frozen.
