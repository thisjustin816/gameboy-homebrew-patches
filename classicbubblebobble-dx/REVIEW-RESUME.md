# Restart and save-resume review

Reviewed against fetched feature-branch checkpoint `ba6fda1`: 15 added or changed
files, with no new commits at review time. No pull request is open.

Fixed game-over jumps at `$07AF` and `$3A6A` enter bank-1 `$609A` without a host
continuation. Its main-loop exits at `01:61EB` and `01:61F1` map fixed code and
jump to `$05CB` and `$05BA`. Those paths never return. Each mapper call has a
balanced frame and preserves AF; BC, DE, and HL are untouched. The builder
checks the exact input instructions and discovered edges. Returning wrappers
retain their existing mapping and return contract.

The failure trace shows four retained bytes per restart. At the eighth observed
exit, task 0's SP is `$DF06`; the next round load saves `$DEFE`. The scheduler
reconstructs `$DFFE`, reads `$0041` as a return PC, and enters invalid code.
The preceding ROM reproduces the reset at tick 20487, emulator frame 20546.
The same input policy passes through tick 60000 on the corrected ROM: 57651
observed snapshots, 50 shared omitted labels, and no compared-state mismatches.
The run includes attract play. It does not establish normal victories.

The save test writes records through actual password/gameplay entry and reads
only battery bytes into a fresh process's pre-boot SRAM field. The checked
state format identifies a unique field with exactly the cartridge's capacity.
It transfers no CPU, mapper, WRAM, or VRAM state. Native and host workers must
prefill and accept the same password, select END, start a nonzero player, and
resume the expected round with zero prior-win flags. All unrelated battery
bytes must remain unchanged. Wrong-bank injection is an explicit failure
control, not a production option.

| Check | Ran | Found | Fixed | Left, and why |
|---|---|---|---|---|
| Correctness and old-build control | Yes | Nonreturning game-over paths retain host frames and eventually resume an invalid stack | Three map-and-jump wrappers, checked source edges; old fails and new passes with the same input | Other gameplay policies remain outside this replay |
| Registers, mapping, and stack | Yes | Generic returning wrappers cannot serve these nonreturning paths | Balanced mapper calls and AF save/restore; caller and exit edges traced | This does not qualify cartridge timing |
| Coding standards and coherence | Yes | Menu navigation needed reuse; reset diagnostics lacked tick and capture | Extracted identical menu input sequence, reused native font decoder, added failure state/frame capture; touched modules read together | Historical variants remain unchanged |
| Quick regressions | Yes | Longer run exposes the restart stack fault | 60000-tick comparison, five menu save/resume cases, both controlled endings, PyBoy SRAM and prefill checks pass; repeat build is identical | Full available suite runs after the code push |
| Sound evidence | Yes | Frame/graphics checks alone do not inspect sound data | Added stored sound-register and wave-RAM comparisons | PCM equality, audible output, and hardware audio remain unverified |
| Descriptions and prose | Yes | Current identity, replay extent, and save method needed documentation | README, status, identity ledger, evidence index, and limits agree; writing-style and remove-ai-tells passes complete | Existing logs retain their historical results |
| Hygiene | Yes | No new release artifact is intended | Syntax, whitespace, ASCII, original handoff checksums, and staged file types checked | Other published games lack their original ROM inputs here |

Applicable standards: gb-development, gb-rom-hacking, coding-standards,
writing-style, and remove-ai-tells. Source-build, design, and link-cable checks
are outside this ROM-hack change. There is no repository-local review skill.
The current candidate is MD5 `e62437d87db1c10032521ae8daa5b69b`.
BB1 v0.14 remains promoted; BB2 v0.22 remains frozen. Collection integration,
full natural playthroughs, and physical verification remain unfinished.
