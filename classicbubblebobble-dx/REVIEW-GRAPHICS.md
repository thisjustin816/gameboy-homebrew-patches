# Graphics checkpoint review

Reviewed against the saved feature-branch commit `3ce8f90`: 38 added or changed
files, with no new commits at review time. The earlier handoff and control-flow
reviews remain historical records. No pull request is open.

The correctness pass follows the banked task entry, enemy-record loader,
background descriptor reads, queue copy paths, and death-animation pointer
reads. The new worker preserves the original pointer arithmetic and register
postconditions while exposing the selected ROM bank. The incremental rebuilder
accepts one saved candidate hash and the exact patched BB1 input; it checks the
existing assembled services and vectors before adding the worker.

| Check | Ran | Found | Fixed | Left, and why |
|---|---|---|---|---|
| Correctness and regression controls | Yes | Wrong bank for records, descriptors, queue sources, task entry, and death pointers | Correct mappings and task entry; old gameplay build fails the regression; death pointers fail on 185 frames before the worker and pass afterward | Extended active replay still has 1381 map mismatch frames |
| Coding standards and consistency | Yes | Snapshot variants need distinct identities and bounded claims | Recorded each identity, explicit comparison fields, and exact-input incremental rebuild | Existing independent builder snapshots retained for reproducibility |
| Behavior descriptions | Yes | README and status still described the earlier graphics frontier | Updated root index, build/test instructions, status, and research index | Full reconstruction awaits the patched Classic input |
| Writing style and prose scan | Yes | Current evidence needed clearer limits | ASCII prose and comments reviewed in context; scan validated with seeded matches; resume notes name exact remaining traces | Raw logs retained as evidence |
| Build and emulator checks | Yes | Missing Classic input prevents full cartridge reconstruction | Incremental rebuild reproduces MD5 `823dad4303d4e83e20cd1fd2522688c2`; KLL1, title, menu, SRAM/power-cycle, password, idle and active default gameplay checks pass | Full three-input build and hardware behavior remain unverified |
| Repository tests and hygiene | Partial | Original uploads disappeared after restart | BB1 and BB2 recovered with matching hashes; syntax, links, whitespace, file types, and original handoff checksums pass | Other game suites cannot rerun without their ROM inputs; their sources and patches are unchanged, and the prior review records the available suites passing |

BB1 v0.14 remains promoted and BB2 v0.22 remains frozen. The current variant is
an experimental checkpoint with a corrected death animation; text/HUD rendering
still needs work. No game rule or visual design was changed.
