# Full-round and ending review

Reviewed against fetched upstream `2488645`: 38 added or changed files
and no new commits at review time. No pull request is open. Earlier checkpoint
reviews remain in this directory; the original handoff is unchanged.

The correctness pass follows bonus-room table reads, `RST $38` return frames,
reverse-row and multirow queue sources, special-object calls, ending jump
tables, and fixed graphics descriptors. The fixed data copy is allocated only
after checking an entire free bank. Its bytes match the exact input's fixed
bank; executable relocation remains separate. Descriptor and pixel readers
restore logical pointers and the executable mapping on exit. The 64-byte copy
still waits for LY 145, with enough VBlank time for its transfer and restore.

Inline dispatch discovery accepts an exact instruction pattern, an adjacent
word table, an even bounded extent ending at the first handler, and targets
inside the same bank's code range. The five observed tables are recorded in
`research/deep-summary.json`. This extends recursive discovery to their real
callers without decoding their pointer bytes as instructions.

The ending fixture identifies eight divider-read instructions before replacing
them in private copies and repairs the global checksum. Matching constants
make decorative RNG inputs comparable. The fixture uses the original bonus
completion and ending routines after controlled goal placement and prior-win
flags. It verifies ending completion or return to retry, not natural victories.
The changed instruction timing prevents claims of exact audio or cycle parity.

| Check | Ran | Found | Fixed | Left, and why |
|---|---|---|---|---|
| Correctness and failure controls | Yes | Bonus tables, row and queue data read through the wrong bank; real RST continuation discarded; undiscovered object, ending, and retry entries | Checked table bases and wrappers, preserved RST frame, bounded dispatch discovery, explicit entries; old controls fail | Further natural input sequences remain outside this checkpoint |
| Fixed data and register contracts | Yes | Graphics consume descriptor and instruction bytes changed by relocation | Untouched data bank `$58`, guarded allocation, independent source classes, logical-pointer and mapping restore | Only the exact supported patched inputs are accepted |
| Coding standards and coherence | Yes | Shared native encoder harness and replay entry needed reuse; strict tile reporting omitted LCD-off metadata | Reused encoder harness, preserved KLL1 wrapper, added general password entry; strict report and active BB1 comments corrected; touched modules and patch sites reviewed | Historical variants remain intact |
| Measurement controls | Yes | Divider-driven decorations differ with relocation timing; partial clears differ while displays are off | Private deterministic DIV fixtures, ordered sample checks, explicit omissions, strict raw-VRAM option; strict control fails at the known clear | Intermediate LCD-off VRAM and unobserved ticks are reported, not claimed equal |
| Regressions | Yes | Old round-25, round-37, graphics, retry, and strict-clear controls fail | All 100 round openings, both 6000-tick ending paths, inherited KLL1/title/menu/SRAM/prefill/gameplay/combo/clear suites pass | Opening play does not prove whole levels or a complete natural playthrough |
| Descriptions and prose | Yes | Current scope and data-bank reservation needed documentation | README, status, identities, research index, commands, fixture provenance, and trace updated; prose and ASCII scan reviewed | Older logs retain their historical names and outputs |
| Repository hygiene | Partial | Other published games' original ROM inputs are absent | Repeat build, source/output identity, fixture regeneration, syntax, whitespace, handoff checksums, and staged file types checked | Unchanged published-game suites cannot rerun without their inputs |

BB1 v0.14 remains promoted, BB2 v0.22 remains frozen, and collection integration
remains unfinished. No game rules, player-facing UI, or release patches changed.
